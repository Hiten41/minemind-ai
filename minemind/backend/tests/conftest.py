import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Set configuration before application imports. Tests never load real credentials.
os.environ.update(APP_ENV='development', DATABASE_URL='', AUTH_SECRET='test-only-not-a-production-secret', MINEMIND_DISABLE_WORKER='true', COGNEE_BASE_URL='', COGNEE_API_KEY='', GROQ_API_KEY='')
import tempfile
os.environ['MINEMIND_STORAGE_DIR'] = tempfile.mkdtemp(prefix='minemind-tests-')
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False

from services import auth_service as auth


@pytest.fixture
def store(tmp_path):
    with patch.object(auth, 'LOCAL_DATABASE_PATH', tmp_path/'test.sqlite'):
        auth.init_auth_store()
        yield tmp_path


@pytest.fixture
def user(store):
    return auth.create_user('Test User', 'test@example.com', '+919999999999', 'a-long-password')
