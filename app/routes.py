import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import BookResponse, ScrapeResponse
from app import crud
from app.scraper import scrape_all_books

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/books", response_model=List[BookResponse], summary="List books with pagination and filtering")
def list_books(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of items to return"),
    category: Optional[str] = Query(None, description="Filter by category name (case-insensitive)"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    db: Session = Depends(get_db)
):
    """
    Retrieve all books with optional pagination and filters.
    Supports filtering by category, minimum price, and maximum price.
    Filters can be combined arbitrarily.
    """
    books = crud.get_books(
        db,
        skip=skip,
        limit=limit,
        category=category,
        min_price=min_price,
        max_price=max_price
    )
    return books


@router.get("/books/{id}", response_model=BookResponse, summary="Get details of a specific book")
def get_book_by_id(id: int, db: Session = Depends(get_db)):
    """Retrieve details of a single book by its ID. Returns 404 if not found."""
    book = crud.get_book(db, book_id=id)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with ID {id} not found."
        )
    return book


@router.post("/scrape", response_model=ScrapeResponse, status_code=status.HTTP_200_OK, summary="Trigger web scraper")
def trigger_scrape(
    mode: str = Query("category", description="Scraper mode: 'category' or 'catalogue'"),
    max_pages: Optional[int] = Query(None, ge=1, description="Optional page limit"),
    db: Session = Depends(get_db)
):
    """
    Trigger the scraper to fetch books from books.toscrape.com and store/update in the database.
    Returns the count of processed, inserted, and updated records.
    """
    result = scrape_all_books(db, max_pages=max_pages, mode=mode)
    if result["status"] == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"]
        )
    return result
