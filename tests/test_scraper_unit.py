import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Book
from app.database import Base
from app.scraper import (
    create_scraper_session,
    scrape_page,
    scrape_all_books,
    parse_price,
    parse_rating,
    parse_availability,
)


class TestScraper(unittest.TestCase):

    def setUp(self):
        self.session = create_scraper_session()
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.session.close()
        self.db.close()

    def test_parser_helpers(self):
        self.assertEqual(parse_price("£51.77"), 51.77)
        self.assertEqual(parse_price("Â£10.00"), 10.00)
        self.assertEqual(parse_price(None), 0.0)
        self.assertEqual(parse_availability("  In stock   (22 available)  "), "In stock (22 available)")

    def test_scrape_page_and_fields(self):
        # Scrape 1 page without pre-set category -> verifies detail page visit for category
        books, next_url = scrape_page(
            "https://books.toscrape.com/catalogue/page-1.html",
            self.session
        )
        self.assertGreater(len(books), 0)
        self.assertEqual(next_url, "https://books.toscrape.com/catalogue/page-2.html")

        first = books[0]
        self.assertTrue(bool(first["title"]))
        self.assertIsInstance(first["price"], float)
        self.assertGreater(first["price"], 0)
        self.assertIsInstance(first["rating"], int)
        self.assertTrue(1 <= first["rating"] <= 5)
        self.assertTrue(bool(first["availability"]))
        self.assertTrue(bool(first["category"]))
        self.assertNotEqual(first["category"], "Unknown")
        print(f"Sample scraped book: {first}")

    def test_store_and_deduplicate(self):
        # First run: scrape 1 page and store in DB
        res1 = scrape_all_books(self.db, max_pages=1, mode="category")
        self.assertEqual(res1["status"], "success")
        self.assertGreater(res1["total_processed"], 0)
        self.assertEqual(res1["inserted"], res1["total_processed"])
        self.assertEqual(res1["updated"], 0)

        initial_count = self.db.query(Book).count()
        self.assertEqual(initial_count, res1["inserted"])
        print(f"Initial run stored {initial_count} books.")

        # Second run: scrape same page again and ensure NO duplicates are created
        res2 = scrape_all_books(self.db, max_pages=1, mode="category")
        self.assertEqual(res2["status"], "success")
        self.assertEqual(res2["inserted"], 0)
        self.assertEqual(res2["updated"], res2["total_processed"])

        after_count = self.db.query(Book).count()
        self.assertEqual(after_count, initial_count)
        print(f"Second run verified: count remains {after_count}, 0 duplicates inserted!")


if __name__ == "__main__":
    unittest.main()
