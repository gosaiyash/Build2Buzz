"""Pytest test configuration and fixtures."""

import os
import pytest
from fastapi.testclient import TestClient

# Set test environment
os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from src.publisher.main import app


@pytest.fixture(scope="session")
def client():
    """TestClient fixture with host header set to testserver."""
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client
