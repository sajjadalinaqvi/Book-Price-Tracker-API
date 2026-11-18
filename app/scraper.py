import argparse
import logging
import re
import sys
from typing import Optional, List, Tuple, Dict, Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.crud import upsert_book

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

BASE_URL = "https://books.toscrape.com/"
REQUEST_TIMEOUT = 15

RATING_MAP = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}


def create_scraper_session() -> requests.Session:
    """Create a configured requests Session with connection pooling."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36 BookTracker/1.0"
        )
    })
    return session


def parse_price(price_text: Optional[str]) -> float:
    """Extract numeric price from text like '£51.77' or 'Â£51.77'."""
    if not price_text:
        return 0.0
    match = re.search(r"[\d.]+", price_text)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return 0.0
    return 0.0


def parse_rating(star_elem: Optional[Tag]) -> Optional[int]:
    """Convert CSS star-rating classes into an integer rating (1-5)."""
    if not star_elem:
        return None
    classes = [c.lower() for c in star_elem.get("class", [])]
    for word, val in RATING_MAP.items():
        if word in classes:
            return val
    return None


def parse_availability(avail_text: Optional[str]) -> Optional[str]:
    """Normalize availability string by stripping excess whitespace."""
    if not avail_text:
        return None
    return " ".join(avail_text.split())


def fetch_book_category(detail_url: str, session: requests.Session) -> Optional[str]:
    """
    Visit an individual book page to extract its category from breadcrumbs.
    Used when the category is not already determined from context.
    """
    try:
        resp = session.get(detail_url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        breadcrumb_links = soup.select("ul.breadcrumb li a")
        if len(breadcrumb_links) >= 3:
            return breadcrumb_links[2].text.strip()
    except (requests.RequestException, Exception) as exc:
        logger.warning("Failed to fetch category from %s: %s", detail_url, exc)
    return None


def parse_book_card(
    card: Tag,
    current_page_url: str,
    session: requests.Session,
    default_category: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Parse an individual book <article class='product_pod'> element."""
    try:
        # Title
        title_tag = card.select_one("h3 a")
        if not title_tag:
            return None
        title = title_tag.get("title") or title_tag.text.strip()
        if not title:
            return None

        # Price
        price_elem = card.select_one(".price_color")
        price = parse_price(price_elem.text if price_elem else None)

        # Rating
        star_elem = card.select_one(".star-rating")
        rating = parse_rating(star_elem)

        # Availability
        avail_elem = card.select_one(".availability")
        availability = parse_availability(avail_elem.text if avail_elem else None)

        # Category
        category = default_category
        if not category:
            href = title_tag.get("href", "")
            detail_url = urljoin(current_page_url, href)
            category = fetch_book_category(detail_url, session)

        return {
            "title": title,
            "price": price,
            "rating": rating,
            "availability": availability,
            "category": category or "General",
        }
    except Exception as exc:
        logger.warning("Error parsing book card: %s", exc)
        return None


def scrape_page(
    page_url: str,
    session: requests.Session,
    default_category: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Scrape a single listing page.
    Returns (list of parsed book dicts, next_page_absolute_url or None).
    """
    books: List[Dict[str, Any]] = []
    try:
        resp = session.get(page_url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch page %s: %s", page_url, exc)
        return books, None

    soup = BeautifulSoup(resp.text, "html.parser")
    category = default_category
    if not category:
        header = soup.select_one("div.page-header h1")
        if header and header.text.strip() not in ("All products", ""):
            category = header.text.strip()

    cards = soup.select("article.product_pod")
    for card in cards:
        book_data = parse_book_card(card, page_url, session, default_category=category)
        if book_data:
            books.append(book_data)

    next_btn = soup.select_one("li.next a")
    next_url = urljoin(page_url, next_btn["href"]) if next_btn and "href" in next_btn.attrs else None

    return books, next_url


def scrape_catalogue_mode(
    db: Session,
    session: requests.Session,
    start_url: str = "https://books.toscrape.com/catalogue/page-1.html",
    max_pages: Optional[int] = None
) -> Tuple[int, int, int]:
    """
    Scrape catalogue by traversing page-by-page through the main pagination.
    Visits individual book pages when necessary to obtain the actual category.
    """
    current_url: Optional[str] = start_url
    processed = 0
    inserted = 0
    updated = 0
    pages_done = 0

    while current_url:
        logger.info("Scraping catalogue page: %s", current_url)
        books, next_url = scrape_page(current_url, session, default_category=None)

        for b in books:
            _, is_new = upsert_book(db, b)
            processed += 1
            if is_new:
                inserted += 1
            else:
                updated += 1

        db.commit()
        pages_done += 1
        if max_pages and pages_done >= max_pages:
            logger.info("Reached max_pages limit (%d).", max_pages)
            break
        current_url = next_url

    return processed, inserted, updated


def scrape_category_mode(
    db: Session,
    session: requests.Session,
    max_pages: Optional[int] = None
) -> Tuple[int, int, int]:
    """
    Scrape books category by category, handling pagination within each category.
    Avoids redundant individual page requests since category is known from context.
    """
    try:
        resp = session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to load base URL %s: %s", BASE_URL, exc)
        return 0, 0, 0

    soup = BeautifulSoup(resp.text, "html.parser")
    cat_links = soup.select(".side_categories ul li ul li a")

    processed = 0
    inserted = 0
    updated = 0
    pages_done = 0

    for link in cat_links:
        cat_name = link.text.strip()
        cat_url: Optional[str] = urljoin(BASE_URL, link["href"])

        while cat_url:
            logger.info("Scraping category '%s' at %s", cat_name, cat_url)
            books, next_url = scrape_page(cat_url, session, default_category=cat_name)

            for b in books:
                _, is_new = upsert_book(db, b)
                processed += 1
                if is_new:
                    inserted += 1
                else:
                    updated += 1

            db.commit()
            pages_done += 1
            if max_pages and pages_done >= max_pages:
                return processed, inserted, updated
            cat_url = next_url

    return processed, inserted, updated


def scrape_all_books(
    db: Session,
    max_pages: Optional[int] = None,
    mode: str = "category"
) -> Dict[str, Any]:
    """
    Main entry point for scraping books.
    Called both from CLI and FastAPI /scrape endpoint.
    """
    session = create_scraper_session()
    try:
        if mode == "catalogue":
            processed, inserted, updated = scrape_catalogue_mode(
                db, session, max_pages=max_pages
            )
        else:
            processed, inserted, updated = scrape_category_mode(
                db, session, max_pages=max_pages
            )

        return {
            "status": "success",
            "total_processed": processed,
            "inserted": inserted,
            "updated": updated,
            "message": f"Successfully processed {processed} books ({inserted} inserted, {updated} updated)."
        }
    except Exception as exc:
        db.rollback()
        logger.error("Scraper encountered an unhandled error: %s", exc)
        return {
            "status": "error",
            "total_processed": 0,
            "inserted": 0,
            "updated": 0,
            "message": f"Scraper error: {exc}"
        }
    finally:
        session.close()


def main():
    """CLI runner for independent execution."""
    parser = argparse.ArgumentParser(description="Scrape books from books.toscrape.com")
    parser.add_argument(
        "--mode",
        choices=["category", "catalogue"],
        default="category",
        help="Scraping mode: 'category' (fast, avoids unnecessary requests) or 'catalogue' (traverses page-1..50)."
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional limit on number of pages to scrape (useful for testing)."
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        logger.info("Starting scraper (mode=%s, max_pages=%s)...", args.mode, args.max_pages)
        result = scrape_all_books(db, max_pages=args.max_pages, mode=args.mode)
        logger.info("Scraper completed: %s", result["message"])
    finally:
        db.close()


if __name__ == "__main__":
    main()
