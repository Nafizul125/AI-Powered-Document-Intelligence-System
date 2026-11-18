import pytest
from fastapi.testclient import TestClient
from main import app
import io

# This fixture keeps the event loop active until all tests are finished
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_read_root(client):
    response = client.get("/")
    assert response.status_code == 200

def test_upload_document(client):
    fake_file = io.BytesIO(b"Dummy PDF content")
    response = client.post(
        "/upload", 
        files={"file": ("test.pdf", fake_file, "application/pdf")}
    )
    assert response.status_code == 200
    assert "job_id" in response.json()

def test_get_status_invalid_id(client):
    response = client.get("/status/invalid_id")
    assert response.status_code == 400

def test_get_status_not_found(client):
    response = client.get("/status/5f8c04b9c84e1b43a8c1f9a1")
    assert response.status_code == 404, f"Server error: {response.json()}"

def test_search_keyword(client):
    response = client.get("/search?query=test&search_type=keyword")
    assert response.status_code == 200, f"Server error: {response.json()}"