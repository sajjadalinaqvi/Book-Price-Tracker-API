import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Book


class TestFastAPIEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create an in-memory test database with StaticPool so all sessions share the in-memory db
        from sqlalchemy.pool import StaticPool
        cls.test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(bind=cls.test_engine)
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=cls.test_engine
        )

        # Seed sample data for fast deterministic testing
        db = cls.TestingSessionLocal()
        sample_books = [
            Book(title="Travel Guide to Paris", price=15.50, rating=4, availability="In stock", category="Travel"),
            Book(title="Travel Guide to Tokyo", price=45.00, rating=5, availability="In stock", category="Travel"),
            Book(title="Mystery in London", price=25.00, rating=3, availability="In stock", category="Mystery"),
            Book(title="History of Science", price=35.00, rating=4, availability="In stock", category="History"),
            Book(title="Fiction Fantasy World", price=10.00, rating=2, availability="In stock", category="Fiction"),
            Book(title="Poetry Anthology", price=50.00, rating=5, availability="In stock", category="Poetry"),
        ]
        db.add_all(sample_books)
        db.commit()
        db.close()

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def test_01_root_health_check(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "ok")

    def test_02_list_books(self):
        resp = self.client.get("/books")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 6)

        # Check serialization fields
        first = data[0]
        self.assertIn("id", first)
        self.assertIn("title", first)
        self.assertIn("price", first)
        self.assertIn("rating", first)
        self.assertIn("availability", first)
        self.assertIn("category", first)
        self.assertIn("scraped_at", first)

    def test_03_pagination(self):
        # Limit test
        resp = self.client.get("/books?skip=0&limit=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 2)
        first_page_titles = [b["title"] for b in data]

        # Skip test
        resp2 = self.client.get("/books?skip=2&limit=2")
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(len(data2), 2)
        second_page_titles = [b["title"] for b in data2]

        # Ensure no overlap
        self.assertTrue(set(first_page_titles).isdisjoint(set(second_page_titles)))

    def test_04_category_filter(self):
        resp = self.client.get("/books?category=Travel")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 2)
        for b in data:
            self.assertEqual(b["category"].lower(), "travel")

    def test_05_min_price_filter(self):
        resp = self.client.get("/books?min_price=30")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for b in data:
            self.assertGreaterEqual(b["price"], 30.0)

    def test_06_max_price_filter(self):
        resp = self.client.get("/books?max_price=20")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for b in data:
            self.assertLessEqual(b["price"], 20.0)

    def test_07_combined_filters(self):
        resp = self.client.get("/books?category=Travel&min_price=10&max_price=20")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Travel Guide to Paris")

    def test_08_get_single_book_success(self):
        resp = self.client.get("/books/1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["title"], "Travel Guide to Paris")

    def test_09_get_single_book_not_found(self):
        resp = self.client.get("/books/99999")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.json())

    def test_10_post_scrape_trigger(self):
        # Trigger scraper for 1 page
        resp = self.client.post("/scrape?max_pages=1&mode=category")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("total_processed", data)
        self.assertIn("inserted", data)
        self.assertIn("updated", data)
        self.assertGreater(data["total_processed"], 0)


if __name__ == "__main__":
    unittest.main()
