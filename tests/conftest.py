import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# main/database import edilmeden ÖNCE ayarlanmalı.
# Her test oturumu için benzersiz bir dosya adı kullanıyoruz ki önceki
# (özellikle Windows'ta hâlâ kilitli olabilen) bir dosyayla çakışmasın.
_DB_FILE = f"./_test_pipeline_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"

import pytest
from fastapi.testclient import TestClient

import database
import main as main_module


@pytest.fixture(scope="session", autouse=True)
def _clean_db():
    yield
    # Silmeden önce tüm bağlantı havuzunu kapat - Windows'ta açık bir
    # bağlantı varken dosya silinemez (PermissionError: WinError 32).
    database.engine.dispose()
    try:
        if os.path.exists(_DB_FILE):
            os.remove(_DB_FILE)
    except PermissionError:
        # Windows bazen dosyayı hemen serbest bırakmayabilir - dosya adı
        # zaten benzersiz olduğu için bir sonraki çalıştırmayı etkilemez,
        # elle silinebilir ama zorunlu değil.
        pass


@pytest.fixture
def client():
    return TestClient(main_module.app)