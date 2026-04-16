from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
def test_health_live() -> None:
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}
