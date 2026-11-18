from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime
from app.database import Base


class Book(Base):
    """SQLAlchemy model representing a scraped book."""

    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(512), nullable=False, unique=True, index=True)
    price = Column(Numeric(10, 2), nullable=False)
    rating = Column(Integer, nullable=True)
    availability = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True, index=True)
    scraped_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<Book(id={self.id}, title='{self.title[:30]}', price={self.price})>"
