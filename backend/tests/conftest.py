import pytest
import os
import sqlite3
import tempfile
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

@pytest.fixture(autouse=True)
def setup_test_env():
    temp_dir = tempfile.mkdtemp()
    original_data_dir = settings.DATA_DIR
    original_mock = settings.MOCK_PROVIDER_ENABLED
    settings.DATA_DIR = temp_dir
    settings.MOCK_PROVIDER_ENABLED = True
    yield
    settings.DATA_DIR = original_data_dir
    settings.MOCK_PROVIDER_ENABLED = original_mock
    # Cleanup temp_dir if needed
    import shutil
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except:
        pass

@pytest.fixture
def test_client():
    from app.main import create_app
    app = create_app()
    with TestClient(app) as client:
        yield client
