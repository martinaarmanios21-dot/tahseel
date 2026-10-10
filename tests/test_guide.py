"""In-app guide (chat with Ribhiya): content matching, privacy of the AI fallback, solutions and feedback.
Fictional TEST-ONLY data in per-test temp databases."""

from types import SimpleNamespace

import pytest

from profit_fixtures import costs_csv, expenses_csv, sales_csv
from revenue_agent import guide
from revenue_agent.guide import content as C
from revenue_agent.profit import store


def ask(conn, msg, lang="ar", **kw):
    return guide.ask(conn, message=msg, lang=lang, tenant="default", actor="human:owner", **kw)


@pytest.mark.parametrize("msg,lang,topic", [
    ("إزاي أرفع البيانات؟", "ar", "upload"),
    ("How do I load my data?", "en", "upload"),
    ("How do I try a what-if?", "en", "whatif"),
    ("إزاي أطلب أسعار من موردين؟", "ar", "suppliers"),
    ("يعني إيه هامش المساهمة؟", "ar", "contribution"),
    ("What is contribution margin?", "en", "contribution"),
    ("أبدأ منين؟", "ar", "start"),
    ("اقترح عليّا حلول", "ar", "solutions"),
    ("I have an idea for a new feature", "en", "feedback"),
    ("فين الكورسات؟", "ar", "learn"),
])
def test_questions_are_answered_from_the_written_content(conn, msg, lang, topic):
    r = ask(conn, msg, lang)
    assert r["topic"] == topic and r["mode"] == "guide"


def test_every_quick_question_has_a_real_answer(conn):
    for lang in ("ar", "en"):
        for q in C.QUICK[lang]:
            assert ask(conn, q, lang)["topic"] not in (None, "menu"), q


def test_feature_answers_carry_a_show_me_action_and_concepts_carry_search_links_only(conn):
    r = ask(conn, "How do I try a what-if?", "en")
    assert r["actions"][0]["go"] == {"tab": "whatif"}
    r = ask(conn, "What is gross margin?", "en")
    assert r["links"] and all(link["url"].startswith(("https://www.youtube.com/results?search_query=",
                                                      "https://www.coursera.org/search?query=")) for link in r["links"])
    for c in C.public("ar")["concepts"]:
        assert all("/results?" in link["url"] or "/search?" in link["url"] for link in c["links"])


def test_no_answer_points_to_the_removed_collections_pages(conn):
    from revenue_agent.guide import content as C
    routes = [f["go"].get("route") for f in C.FEATURES if f["go"]]
    assert all(r in (None, "/") for r in routes)
    assert ask(conn, "تبويب التحصيل بيعمل إيه؟")["topic"] != "collections"


def test_unknown_question_without_ai_shows_the_menu(conn):
    r = ask(conn, "qwzx plorb", "en")
    assert r["topic"] == "menu" and r["mode"] == "guide" and r["actions"]


def test_input_limits(conn):
    with pytest.raises(guide.GuideRejected):
        ask(conn, "   ")
    with pytest.raises(guide.GuideRejected):
        ask(conn, "x" * 50_000)


def test_ai_fallback_gets_no_business_data_and_its_links_are_removed(conn, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    iid = store.create(conn, title="t")["id"]
    store.add_file(conn, iid, "s.csv", sales_csv(), tenant="default", actor="o")
    seen = {}

    class FakeClient:
        def __init__(self, *a, **k):
            self.tokens = 10

        def chat(self, messages, **k):
            seen["messages"] = messages
            return SimpleNamespace(text="Try the What if tab. See https://evil.example/x and www.spam.example")

    monkeypatch.setattr(guide, "LLMClient", FakeClient)
    r = ask(conn, "qwzx plorb how should a florist plan seasons", "en")
    assert r["mode"] == "api"
    assert "http" not in r["answer"] and "www." not in r["answer"]
    sent = " ".join(m["content"] for m in seen["messages"])
    assert "s.csv" not in sent and "500" not in sent.replace("500 ", "")  # no file names or sales figures
    assert "You do NOT have the owner's data" in seen["messages"][0]["content"]


def test_audit_never_stores_the_message_text(conn):
    ask(conn, "How do I load my data? my supplier is Acme Secret Co", "en")
    row = conn.execute("SELECT detail FROM audit_log WHERE action='guide_ask' ORDER BY id DESC").fetchone()
    assert "Acme" not in row[0]


def test_solutions_without_data_are_labelled_general(conn):
    r = guide.solutions(conn, tenant="default", lang="en")
    assert r["based_on_data"] is False and r["items"][0]["title"] == "General ideas"


def test_solutions_with_data_come_from_the_findings(conn):
    iid = store.create(conn, title="t")["id"]
    for name, raw in [("s.csv", sales_csv()), ("c.csv", costs_csv()), ("e.csv", expenses_csv())]:
        store.add_file(conn, iid, name, raw, tenant="default", actor="o")
    r = guide.solutions(conn, tenant="default", lang="en", iid=iid)
    assert r["based_on_data"] is True
    assert any(i["title"].lower().startswith("packaging") and i["options"] for i in r["items"])
    # another tenant can't read this investigation through the guide
    assert guide.solutions(conn, tenant="other", lang="en", iid=iid)["based_on_data"] is False


def test_feedback_is_validated_stored_per_tenant_and_exported_safely(conn):
    with pytest.raises(guide.GuideRejected):
        guide.add_feedback(conn, tenant="default", actor="o", kind="review", rating=9, text="", page="/", lang="en")
    with pytest.raises(guide.GuideRejected):
        guide.add_feedback(conn, tenant="default", actor="o", kind="idea", rating=None, text="  ", page="/", lang="en")
    guide.add_feedback(conn, tenant="default", actor="o", kind="idea", rating=None, text="=HYPERLINK(1)", page="/", lang="en")
    guide.add_feedback(conn, tenant="default", actor="o", kind="review", rating=5, text="مفيد جداً", page="/", lang="ar")
    guide.add_feedback(conn, tenant="other", actor="o", kind="bug", rating=None, text="other tenant", page="/", lang="en")
    mine = guide.list_feedback(conn, tenant="default")
    assert [f["kind"] for f in mine] == ["review", "idea"] and all(f["text"] != "other tenant" for f in mine)

    from fastapi.testclient import TestClient
    from revenue_agent.web.app import app
    c = TestClient(app)
    csv_text = c.get("/api/guide/feedback.csv").text
    assert "'=HYPERLINK(1)" in csv_text and "other tenant" not in csv_text
    assert c.post("/api/guide/feedback", json={"kind": "bug", "text": "upload button hidden"}).status_code == 200
    assert c.post("/api/guide/feedback", json={"kind": "bug", "text": "x" * 5000}).status_code == 413
    assert c.get("/api/guide/content?lang=en").json()["features"][0]["id"] == "start"
    assert c.post("/api/guide/ask", json={"message": "How do I load my data?", "lang": "en"}).json()["topic"] == "upload"


# ------------------------------------------------------------------ inside an investigation: context-aware answers

def _inv(conn, with_data=True):
    iid = store.create(conn, title="t")["id"]
    if with_data:
        for name, raw in [("s.csv", sales_csv()), ("c.csv", costs_csv()), ("e.csv", expenses_csv())]:
            store.add_file(conn, iid, name, raw, tenant="default", actor="o")
    return iid


def test_next_step_matches_the_do_this_now_card(conn):
    from revenue_agent.profit import diagnosis
    iid = _inv(conn, with_data=False)
    r = ask(conn, "What should I do now?", "en", investigation=iid)
    first = diagnosis.state(conn, iid, "default", "en")["questions"][0]
    assert r["source"] == "state" and first["text"]["en"] in r["answer"] and r["actions"][0]["go"] == {"anchor": "do-now"}
    assert "sales" in ask(conn, "What files are missing?", "en", investigation=iid)["answer"].lower()


def test_numbers_questions_go_to_the_advisor_and_are_grounded(conn, monkeypatch):
    monkeypatch.setenv("PROFIT_ADVISOR_ENGINE", "rules")
    iid = _inv(conn)
    r = ask(conn, "Why is my profit down?", "en", investigation=iid)
    assert r["source"] == "your_numbers" and r["engine"] == "rules" and "EGP 15.00" in r["answer"]
    assert ask(conn, "ليه ربحي قلّ؟", "ar", investigation=iid)["source"] == "your_numbers"


def test_fix_questions_list_the_findings_own_options(conn):
    from revenue_agent.profit import diagnosis
    iid = _inv(conn)
    r = ask(conn, "What can I do about it?", "en", investigation=iid)
    f = diagnosis.state(conn, iid, "default", "en")["diagnosis"]["findings"][0]
    assert r["source"] == "state" and r["topic"] == "solutions" and "General ideas" not in r["answer"]
    assert all(o["title"] in r["answer"] for o in f["recommendation"]["options"])
    assert ask(conn, "أعمل إيه عشان أصلّحها؟", "ar", investigation=iid)["topic"] == "solutions"


def test_missing_and_why_answers_come_from_the_evidence_register(conn):
    iid = _inv(conn)
    r = ask(conn, "What files are missing?", "en", investigation=iid)
    assert r["topic"] == "missing" and r["actions"][0]["go"] == {"tab": "files"}
    assert ask(conn, "Why do you need this?", "en", investigation=iid)["topic"] in ("why_needed", "next")


def test_how_to_and_concepts_still_use_the_help_inside_an_investigation(conn):
    iid = _inv(conn)
    assert ask(conn, "How do I try a what-if?", "en", investigation=iid)["topic"] == "whatif"
    assert ask(conn, "What is contribution margin?", "en", investigation=iid)["topic"] == "contribution"


def test_another_business_investigation_id_is_ignored(conn):
    iid = _inv(conn)
    r = guide.ask(conn, message="Why is my profit down?", lang="en", tenant="other", actor="o", investigation=iid)
    assert r["source"] in ("help", "help_ai") and "15.00" not in r["answer"]


def test_general_ideas_are_labelled_and_only_without_comparable_data(conn):
    one_month = store.create(conn, title="t")["id"]
    store.add_file(conn, one_month, "s.csv", sales_csv(months=("2026-09",), orders=(72,)), tenant="default", actor="o")
    kinds = [i["kind"] for i in guide.solutions(conn, tenant="default", lang="en", iid=one_month)["items"]]
    assert "general" in kinds and "finding" not in kinds
    assert "General ideas" in ask(conn, "What can I do about it?", "en", investigation=one_month)["answer"]
    full = _inv(conn)
    assert "general" not in [i["kind"] for i in guide.solutions(conn, tenant="default", lang="en", iid=full)["items"]]


def test_investigation_list_counts_files_so_same_names_can_be_told_apart(conn):
    a, b = store.create(conn, title="Nour")["id"], store.create(conn, title="nour")["id"]
    store.add_file(conn, a, "s.csv", sales_csv(), tenant="default", actor="o")
    counts = {i["id"]: i["file_count"] for i in store.list_all(conn)}
    assert counts[a] == 1 and counts[b] == 0
