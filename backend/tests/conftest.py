import pytest
import os
import sqlite3
import tempfile
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

@pytest.fixture
def test_client():
    temp_dir = tempfile.mkdtemp()
    settings.DATA_DIR = temp_dir
    with TestClient(app) as client:
        yield client
