from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class BookBase(BaseModel):
    """Base schema for book attributes."""
    title: str
    price: float = Field(..., ge=0, description="Book price in GBP")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Star rating from 1 to 5")
    availability: Optional[str] = Field(None, description="Stock availability status")
    category: Optional[str] = Field(None, description="Book category")


class BookCreate(BookBase):
    """Schema for creating or updating a book."""
    pass


class BookResponse(BookBase):
    """Schema for book API responses."""
    id: int
    scraped_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScrapeResponse(BaseModel):
    """Schema for scrape endpoint response."""
    status: str
    total_processed: int
    inserted: int
    updated: int
    message: str
