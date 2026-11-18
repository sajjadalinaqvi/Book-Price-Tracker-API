from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from app.models import Book


def get_book(db: Session, book_id: int) -> Optional[Book]:
    """Retrieve a single book by its primary key ID."""
    return db.query(Book).filter(Book.id == book_id).first()


def get_book_by_title(db: Session, title: str) -> Optional[Book]:
    """Retrieve a single book by its unique title."""
    return db.query(Book).filter(Book.title == title).first()


def get_books(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None
) -> List[Book]:
    """
    Retrieve books with optional filtering by category, min_price, max_price,
    and pagination with skip and limit.
    """
    query = db.query(Book)

    if category:
        query = query.filter(Book.category.ilike(category.strip()))
    if min_price is not None:
        query = query.filter(Book.price >= min_price)
    if max_price is not None:
        query = query.filter(Book.price <= max_price)

    return query.order_by(Book.id.asc()).offset(skip).limit(limit).all()


def upsert_book(db: Session, book_data: dict) -> Tuple[Book, bool]:
    """
    Insert a new book or update existing record if title already exists.
    Returns (book_instance, is_created).
    """
    title = book_data["title"]
    existing = get_book_by_title(db, title)

    now = datetime.now(timezone.utc)
    if existing:
        existing.price = book_data["price"]
        existing.rating = book_data.get("rating")
        existing.availability = book_data.get("availability")
        existing.category = book_data.get("category")
        existing.scraped_at = now
        return existing, False
    else:
        new_book = Book(
            title=title,
            price=book_data["price"],
            rating=book_data.get("rating"),
            availability=book_data.get("availability"),
            category=book_data.get("category"),
            scraped_at=now,
        )
        db.add(new_book)
        return new_book, True
