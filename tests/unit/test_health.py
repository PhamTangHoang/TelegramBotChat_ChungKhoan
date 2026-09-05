from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_returns_ok_for_platform_probes() -> None:
    client = TestClient(app)
    response = client.get("/")
    head_response = client.head("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert head_response.status_code == 200
