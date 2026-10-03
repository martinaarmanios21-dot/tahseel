"""API brain against a fake OpenAI-compatible provider: retries, JSON repair, fallback."""

import json

import httpx
import pytest

from revenue_agent import llm
from revenue_agent.brains.base import BrainContext
from revenue_agent.brains.offline import OfflineBrain
from revenue_agent.engine import Engine


def _ok(text):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}],
                                     "usage": {"prompt_tokens": 100, "completion_tokens": 50}},
                          request=httpx.Request("POST", "http://x"))


@pytest.fixture
def api_env(monkeypatch):
    monkeypatch.setenv("ENGINE", "api")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDERS", "gemini")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setattr(llm, "_wait_for_slot", lambda p, r: None)


def _offline_answer(payload_json):
    views = json.loads(payload_json)["invoices"]
    from revenue_agent import skills, db
    content = skills.active(db.connect())["content"]
    return json.dumps(OfflineBrain().decide(views, content, BrainContext("x", 1, "t")).__dict__["decisions"])


def test_retry_on_429_then_success(conn, api_env, monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "1"}, request=httpx.Request("POST", url))
        return _ok('{"decisions": ' + _offline_answer(json["messages"][1]["content"]) + "}")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    run = Engine(conn).run_episode(kind="eval", seed=5, size=10)
    assert run["status"] == "completed"
    assert run["metrics"]["llm_calls"] >= 4  # 1 retry + 3 rounds
    assert conn.execute("SELECT COUNT(*) FROM events WHERE kind='llm_retry'").fetchone()[0] >= 1


def test_bad_json_is_repaired(conn, api_env, monkeypatch):
    state = {"n": 0}

    def fake_post(url, headers, json, timeout):
        state["n"] += 1
        if json["messages"][-1]["content"].startswith("That was not valid JSON"):
            return _ok('```json\n{"decisions": ' + _offline_answer(json["messages"][1]["content"]) + "}\n```")
        return _ok("Sure! Here are my decisions: (oops, no json)")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    run = Engine(conn).run_episode(kind="eval", seed=5, size=10, rounds=1)
    assert run["status"] == "completed"
    assert conn.execute("SELECT COUNT(*) FROM events WHERE kind='degraded_mode'").fetchone()[0] == 0


def test_provider_down_degrades_to_offline(conn, api_env, monkeypatch):
    def fake_post(url, headers, json, timeout):
        raise httpx.ConnectTimeout("down")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    run = Engine(conn).run_episode(kind="eval", seed=5, size=10, rounds=1)
    assert run["status"] == "completed"
    assert conn.execute("SELECT COUNT(*) FROM events WHERE kind='degraded_mode'").fetchone()[0] == 1


def test_budget_exhaustion_halts_run(conn, api_env, monkeypatch):
    monkeypatch.setenv("RUN_LLM_CALL_CAP", "1")

    def fake_post(url, headers, json, timeout):
        return _ok('{"decisions": ' + _offline_answer(json["messages"][1]["content"]) + "}")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    run = Engine(conn).run_episode(kind="eval", seed=5, size=10)
    assert run["status"] == "halted_budget"
