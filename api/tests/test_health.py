"""门面活着吗。"""
from __future__ import annotations


def test_health_reports_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "creation-platform-api"}


def test_unknown_route_is_404(client):
    assert client.get("/api/nope").status_code == 404
