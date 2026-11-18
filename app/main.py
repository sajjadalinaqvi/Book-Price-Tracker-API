import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db
from app.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown events."""
    logger.info("Initializing database on startup...")
    try:
        init_db()
    except Exception as exc:
        logger.error("Database initialization failed during application startup: %s", exc)
    yield
    logger.info("Application shutdown.")


app = FastAPI(
    title="Book Price Tracker API",
    description="A lightweight REST API to scrape, store, and query book prices from books.toscrape.com",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(router)


@app.get("/", tags=["Health"])
def root():
    """Root health-check endpoint."""
    return {
        "status": "ok",
        "service": "Book Price Tracker API",
        "docs_url": "/docs"
    }
