import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest  # noqa: E402

from app import auth, detection, ml, main  # noqa: E402
from app.db import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def base_propre(tmp_path, monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(ml, "MODEL_DIR", tmp_path / "models")
    ml._cache.clear()
    detection._active.clear()
    auth._echecs.clear()
    # Les tests fonctionnels passent pour un utilisateur connecté ; test_auth.py
    # retire ce raccourci pour tester la vraie authentification.
    main.app.dependency_overrides[auth.exiger_auth] = lambda: "test"
    yield
    main.app.dependency_overrides.clear()
