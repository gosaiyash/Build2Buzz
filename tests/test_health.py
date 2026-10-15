"""Unit tests for the health endpoint."""


def test_health_endpoint_returns_200_and_healthy(client):
    """Verify /api/health returns 200 with healthy status and metadata."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "127.0.0.1" in data["host_binding"] or "localhost" in data["host_binding"]
    assert "uptime_seconds" in data
    assert data["database_connected"] is True


def test_dashboard_page_loads(client):
    """Verify root / loads the dashboard HTML correctly."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Build2Buzz" in response.text
    assert "Dashboard" in response.text
