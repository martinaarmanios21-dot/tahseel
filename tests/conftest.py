import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test gets its own database and never touches ~/.hermes or real API keys."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ENGINE", "offline")
    monkeypatch.setenv("HERMES_SKILL_SYNC", "0")
    for key in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def conn():
    from revenue_agent import db
    c = db.connect()
    yield c
    c.close()
