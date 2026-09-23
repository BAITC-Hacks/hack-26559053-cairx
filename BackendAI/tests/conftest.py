import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.main import create_app
from app.services.loader import DataStore


@pytest.fixture
def config():
    return Settings(OPENAI_API_KEY="", NVIDIA_API_KEY="", DEBUG=False)


@pytest.fixture
def store(config):
    result = DataStore(config.data_path, config.SNAPSHOT_DATE)
    result.reset()
    return result


@pytest.fixture
def client(config):
    with TestClient(create_app(config), raise_server_exceptions=False) as result:
        yield result
