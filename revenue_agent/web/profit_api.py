"""HTTP API for profit investigations. Tenant comes from the authenticated principal (web/auth.py)."""

from __future__ import annotations

import io
import json
import csv

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

from .. import db
from ..ledger.csv_import import csv_safe
import time

from ..profit import (advisor, diagnosis, ingest, memory, orders as orders_mod, outreach, quotes, simulator, store,
                      tracking)

router = APIRouter(prefix="/api")
MAX_FILES = 10


def _tenant(request: Request) -> str:
    p = getattr(request.state, "principal", None)
    return p.tenant if p else "default"


def _actor(request: Request) -> str:
    return "human:" + ((request.headers.get("x-tahsila-user") or "owner").strip()[:40] or "owner")


def _inv(conn, request: Request, iid: str) -> dict:
    try:
        return store.get(conn, iid, _tenant(request))
    except store.NotFound as exc:
        raise HTTPException(404, "investigation_not_found") from exc


@router.get("/profit/templates/{rtype}.csv", response_class=PlainTextResponse)
def template(rtype: str):
    if rtype not in ingest.TYPES:
        raise HTTPException(404, "unknown template")
    out = io.StringIO()
    csv.writer(out).writerow(list(ingest.TYPES[rtype]))
    return PlainTextResponse(out.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=ribhiya_{rtype}_template.csv"})


@router.get("/investigations")
def list_investigations(request: Request):
    return store.list_all(db.connect(), _tenant(request))


@router.post("/investigations")
def create(request: Request, body: dict = Body(default={})):
    cur = str(body.get("currency", "EGP")).upper()[:3]
    return store.create(db.connect(), tenant=_tenant(request), title=str(body.get("title", ""))[:120], currency=cur,
                        actor=_actor(request))


@router.get("/investigations/{iid}")
def get_state(iid: str, request: Request, lang: str = "ar", base: str | None = None, current: str | None = None):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        return diagnosis.state(conn, iid, _tenant(request), "en" if lang == "en" else "ar", base, current)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/investigations/{iid}")
def delete(iid: str, request: Request):
    conn = db.connect()
    _inv(conn, request, iid)
    store.delete(conn, iid, _tenant(request), _actor(request))
    return {"deleted": iid}


@router.post("/investigations/{iid}/files")
async def upload(iid: str, request: Request, files: list[UploadFile] = File(...), overrides: str | None = Form(None),
                 confirm: bool = Form(False), replace_file_id: int | None = Form(None), date_format: str = Form("auto")):
    conn = db.connect()
    _inv(conn, request, iid)
    if len(files) > MAX_FILES:
        raise HTTPException(413, f"at most {MAX_FILES} files per upload")
    if date_format not in ("auto", "DMY", "MDY", "YMD"):
        raise HTTPException(422, "invalid date_format")
    try:
        ov = json.loads(overrides) if overrides else None
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "overrides must be JSON") from exc
    if ov is not None and not isinstance(ov, dict):
        raise HTTPException(422, "overrides must be an object")
    if replace_file_id:
        try:
            store.remove_file(conn, iid, replace_file_id, tenant=_tenant(request), actor=_actor(request))
        except store.NotFound as exc:
            raise HTTPException(404, "file_not_found") from exc
    out = []
    for f in files:
        raw = await f.read(ingest.MAX_BYTES + 1)
        out.append(store.add_file(conn, iid, f.filename or "upload", raw, tenant=_tenant(request),
                                  actor=_actor(request), date_format=date_format, overrides=ov, confirm=confirm))
    return {"results": out}


@router.delete("/investigations/{iid}/files/{file_id}")
def remove_file(iid: str, file_id: int, request: Request):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        store.remove_file(conn, iid, file_id, tenant=_tenant(request), actor=_actor(request))
    except store.NotFound as exc:
        raise HTTPException(404, "file_not_found") from exc
    return {"removed": file_id}


def _answer_value(v) -> str | None:
    """Answers are stored as text; a multi-choice answer may arrive as a list (joined with commas, like the UI)."""
    if v is None:
        return None
    if isinstance(v, list):
        return ",".join(str(x) for x in v)
    return str(v)


@router.post("/investigations/{iid}/answers")
def answer(iid: str, request: Request, body: dict = Body(...)):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        diagnosis.answer(conn, iid, str(body.get("qid", ""))[:80], tenant=_tenant(request),
                         status=str(body.get("status", "answered")), value=_answer_value(body.get("value")),
                         actor=_actor(request))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.get("remember") and str(body.get("qid", "")).startswith("p_") and body.get("value"):
        memory.remember(conn, _tenant(request), "fact", str(body["qid"])[2:], str(body["value"])[:300],
                        "owner_confirmed")
    return {"ok": True}


@router.post("/investigations/{iid}/manual")
def manual(iid: str, request: Request, body: dict = Body(...)):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        return store.add_manual_expense(conn, iid, tenant=_tenant(request), actor=_actor(request),
                                        category=str(body.get("category", "")), month=str(body.get("month", "")),
                                        amount=str(body.get("amount", "")), note=str(body.get("note", "")))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/investigations/{iid}/interventions")
def plan(iid: str, request: Request, body: dict = Body(...)):
    conn = db.connect()
    _inv(conn, request, iid)
    s = diagnosis.state(conn, iid, _tenant(request), "en", body.get("base"), body.get("current"))
    d = s["diagnosis"]
    f = next((x for x in (d or {}).get("findings", []) if x["driver"] == body.get("driver")), None)
    if f is None:
        raise HTTPException(409, "no current finding for that driver: recommendations need evidence first")
    if body.get("option_key") not in diagnosis.OPTIONS.get(f["driver"], []):
        raise HTTPException(422, "unknown option for this finding")
    return tracking.create(conn, iid, tenant=_tenant(request), actor=_actor(request), finding=f,
                           option_key=body["option_key"], diagnosis=d)


@router.post("/investigations/{iid}/interventions/{xid}/status")
def set_status(iid: str, xid: int, request: Request, body: dict = Body(...)):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        return tracking.set_status(conn, iid, xid, tenant=_tenant(request), actor=_actor(request),
                                   status=str(body.get("status", "")), implemented_on=body.get("implemented_on"),
                                   note=body.get("note"))
    except store.NotFound as exc:
        raise HTTPException(404, "intervention_not_found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/investigations/{iid}/interventions/{xid}/verify")
def verify(iid: str, xid: int, request: Request):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        return tracking.verify(conn, iid, xid, tenant=_tenant(request), actor=_actor(request))
    except store.NotFound as exc:
        raise HTTPException(404, "intervention_not_found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/investigations/{iid}/advisor")
def ask_advisor(iid: str, request: Request, body: dict = Body(...)):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        return advisor.ask(conn, iid, tenant=_tenant(request), question=str(body.get("question", "")),
                           lang="en" if body.get("lang") == "en" else "ar", actor=_actor(request))
    except advisor.AdvisorRejected as exc:
        raise HTTPException(413 if exc.code == "too_long" else 422, {"code": exc.code, "message": str(exc)}) from exc


@router.get("/investigations/{iid}/export.csv", response_class=PlainTextResponse)
def export(iid: str, request: Request):
    """Monthly metrics as CSV (formula-injection safe)."""
    conn = db.connect()
    _inv(conn, request, iid)
    s = diagnosis.state(conn, iid, _tenant(request), "en")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["period", "currency", "orders", "net_sales", "cogs", "packaging", "shipping", "payment_fees",
                "marketplace_fees", "contribution", "contribution_margin", "estimated", "missing"])
    for p in s["metrics"]["periods"]:
        w.writerow([p["period"], p["currency"], p["orders"], p["net_sales"] / 100, p["cogs"] / 100,
                    *[p["variable"][k] / 100 for k in ("packaging", "shipping", "payment_fees", "marketplace_fees")],
                    p["contribution"] / 100, p["contribution_margin"], p["estimated"],
                    csv_safe(";".join(p["missing"]))])
    return PlainTextResponse(out.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=ribhiya_metrics.csv"})


@router.put("/investigations/{iid}/currency")
def set_currency(iid: str, request: Request, body: dict = Body(...)):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        return store.set_currency(conn, iid, tenant=_tenant(request), actor=_actor(request),
                                  currency=str(body.get("currency", "")))
    except store.CurrencyLocked as exc:
        raise HTTPException(409, {"code": "currency_locked", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(422, {"code": "invalid_currency", "message": str(exc)}) from exc


@router.put("/investigations/{iid}/allocation")
def set_allocation(iid: str, request: Request, body: dict = Body(...)):
    """Owner chooses how monthly invoices are shared across orders (or switches allocation off per category)."""
    conn = db.connect()
    inv = _inv(conn, request, iid)
    try:
        alloc = orders_mod.validate_allocation(body.get("allocation") if isinstance(body.get("allocation"), dict) else {})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    from ..ledger.store import audit
    with db.tx(conn):
        store.touch(conn, iid, settings=(inv.get("settings") or {}) | {"allocation": alloc})
        audit(conn, _actor(request), "allocation_changed", tenant=_tenant(request), investigation=iid, allocation=alloc)
    return {"allocation": alloc}


@router.get("/investigations/{iid}/orders")
def list_orders(iid: str, request: Request, filter: str = "all", product: str | None = None, offset: int = 0,
                limit: int = 50):
    """Order-level profit rows (paged). filter: all | loss | incomplete | allocated."""
    conn = db.connect()
    inv = _inv(conn, request, iid)
    s = diagnosis.state(conn, iid, _tenant(request), "en")
    cur = s["main_currency"]
    if not cur:
        return {"total": 0, "orders": []}
    o = orders_mod.compute(store.records(conn, iid), cur, (inv.get("settings") or {}).get("allocation"))
    rows = o["orders"]
    if filter == "loss":
        rows = [x for x in rows if x["contribution"] is not None and x["contribution"] < 0]
    elif filter == "incomplete":
        rows = [x for x in rows if not x["complete"]]
    elif filter == "allocated":
        rows = [x for x in rows if x["has_allocated"]]
    if product:
        rows = [x for x in rows if any(l["product"] == product for l in x["lines"])]
    limit = max(1, min(limit, 200))
    page = rows[max(0, offset): max(0, offset) + limit]
    return {"total": len(rows), "currency": cur, "orders": [orders_mod._brief(x) | {"lines": x["lines"],
            "missing": x["missing"], "complete": x["complete"], "refund_source": x["refund_source"]} for x in page]}


@router.post("/investigations/{iid}/simulate")
def simulate(iid: str, request: Request, body: dict = Body(...)):
    conn = db.connect()
    inv = _inv(conn, request, iid)
    s = diagnosis.state(conn, iid, _tenant(request), "en")
    if not s["main_currency"]:
        raise HTTPException(409, "upload sales first")
    try:
        return simulator.run(store.records(conn, iid), s["main_currency"], body.get("scenario") or {},
                             period=body.get("period"), allocation=(inv.get("settings") or {}).get("allocation"),
                             lang="en" if body.get("lang") == "en" else "ar")
    except simulator.ScenarioError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/investigations/{iid}/scenarios")
def save_scenario(iid: str, request: Request, body: dict = Body(...)):
    """Save a scenario (recomputed server-side, never trusted from the client); optionally track it as an experiment."""
    conn = db.connect()
    inv = _inv(conn, request, iid)
    s = diagnosis.state(conn, iid, _tenant(request), "en")
    try:
        res = simulator.run(store.records(conn, iid), s["main_currency"], body.get("scenario") or {},
                            period=body.get("period"), allocation=(inv.get("settings") or {}).get("allocation"),
                            lang="en" if body.get("lang") == "en" else "ar")
    except simulator.ScenarioError as exc:
        raise HTTPException(422, str(exc)) from exc
    from ..ledger.store import audit
    name = str(body.get("name") or "Scenario")[:120]
    with db.tx(conn):
        cur = conn.execute("INSERT INTO scenarios(investigation_id, name, params, result, created_at) VALUES(?,?,?,?,?)",
                           (iid, name, json.dumps(res["scenario"], ensure_ascii=False),
                            json.dumps({k: res[k] for k in ("period", "currency", "baseline", "projected", "delta",
                                                            "assumptions", "summary")}, ensure_ascii=False), time.time()))
        audit(conn, _actor(request), "scenario_saved", tenant=_tenant(request), investigation=iid, scenario=cur.lastrowid)
    out = {"scenario_id": cur.lastrowid, "result": res}
    if body.get("track"):
        try:
            out["intervention"] = tracking.create_from_scenario(conn, iid, tenant=_tenant(request), actor=_actor(request),
                                                                scenario_id=cur.lastrowid)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    return out


@router.post("/investigations/{iid}/scenarios/{sid}/track")
def track_scenario(iid: str, sid: int, request: Request):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        return tracking.create_from_scenario(conn, iid, tenant=_tenant(request), actor=_actor(request), scenario_id=sid)
    except store.NotFound as exc:
        raise HTTPException(404, "scenario_not_found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/investigations/{iid}/quotes")
def list_quotes(iid: str, request: Request):
    conn = db.connect()
    _inv(conn, request, iid)
    return quotes.list_for(conn, iid)


@router.post("/investigations/{iid}/quotes")
def add_quote(iid: str, request: Request, body: dict = Body(...)):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        return quotes.add(conn, iid, tenant=_tenant(request), actor=_actor(request), data=body)
    except quotes.QuoteError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/investigations/{iid}/quotes/{qid}/confirm")
def confirm_quote(iid: str, qid: int, request: Request, body: dict = Body(...)):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        return quotes.update_flags(conn, iid, qid, tenant=_tenant(request), actor=_actor(request),
                                   owner_confirmed_quote=body.get("owner_confirmed_quote"),
                                   spec_confirmed=body.get("spec_confirmed"))
    except store.NotFound as exc:
        raise HTTPException(404, "quote_not_found") from exc


@router.delete("/investigations/{iid}/quotes/{qid}")
def delete_quote(iid: str, qid: int, request: Request):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        quotes.delete(conn, iid, qid, tenant=_tenant(request), actor=_actor(request))
    except store.NotFound as exc:
        raise HTTPException(404, "quote_not_found") from exc
    return {"deleted": qid}


@router.get("/investigations/{iid}/quotes/compare")
def compare_quotes(iid: str, request: Request, item_key: str, quantity: float | None = None):
    conn = db.connect()
    _inv(conn, request, iid)
    try:
        return quotes.compare(conn, iid, tenant=_tenant(request), item_key=item_key, quantity=quantity)
    except quotes.QuoteError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/investigations/{iid}/quotes/extract")
async def extract_quote(iid: str, request: Request, file: UploadFile = File(...)):
    """Suggest quote fields from a text-based quote document. Nothing is stored; the owner checks every value."""
    conn = db.connect()
    _inv(conn, request, iid)
    raw = await file.read(ingest.MAX_BYTES + 1)
    return quotes.extract(file.filename or "quote", raw)


def _outreach_call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except store.NotFound as exc:
        raise HTTPException(404, "outreach_not_found") from exc
    except outreach.OutreachError as exc:
        status = 502 if exc.code == "send_failed" else 409
        raise HTTPException(status, {"code": exc.code, "message": str(exc)}) from exc


@router.post("/investigations/{iid}/outreach")
def create_outreach(iid: str, request: Request, body: dict = Body(...)):
    conn = db.connect()
    _inv(conn, request, iid)
    return _outreach_call(outreach.create, conn, iid, tenant=_tenant(request), actor=_actor(request),
                          purpose=str(body.get("purpose", "")), driver=body.get("driver"), quote_id=body.get("quote_id"),
                          lang="en" if body.get("lang") == "en" else "ar")


@router.put("/investigations/{iid}/outreach/{oid}")
def edit_outreach(iid: str, oid: int, request: Request, body: dict = Body(...)):
    conn = db.connect()
    _inv(conn, request, iid)
    return _outreach_call(outreach.update, conn, iid, oid, tenant=_tenant(request), actor=_actor(request),
                          brief=body.get("brief") if isinstance(body.get("brief"), dict) else None,
                          supplier_name=body.get("supplier_name"), supplier_email=body.get("supplier_email"),
                          subject=body.get("subject"), body=body.get("body"), regenerate=bool(body.get("regenerate")),
                          language=body.get("language"))


@router.post("/investigations/{iid}/outreach/{oid}/{verb}")
def outreach_action(iid: str, oid: int, verb: str, request: Request, body: dict = Body(default={})):
    conn = db.connect()
    _inv(conn, request, iid)
    kw = {"tenant": _tenant(request), "actor": _actor(request)}
    if verb == "approve":
        return _outreach_call(outreach.approve, conn, iid, oid, **kw)
    if verb == "send":
        return _outreach_call(outreach.send, conn, iid, oid, approval=str(body.get("approval", "")), **kw)
    if verb == "copied":
        return _outreach_call(outreach.mark_copied, conn, iid, oid, **kw)
    if verb == "cancel":
        return _outreach_call(outreach.cancel, conn, iid, oid, **kw)
    raise HTTPException(404, "unknown action")


@router.get("/memory")
def get_memory(request: Request):
    conn = db.connect()
    return {"entries": memory.entries(conn, _tenant(request), include_retired=True),
            "mapping_reliability": memory.mapping_reliability(conn, _tenant(request))}


@router.post("/memory/{entry_id}/retire")
def retire(entry_id: int, request: Request):
    try:
        memory.retire(db.connect(), _tenant(request), entry_id, _actor(request))
    except LookupError as exc:
        raise HTTPException(404, "memory_not_found") from exc
    return {"retired": entry_id}
