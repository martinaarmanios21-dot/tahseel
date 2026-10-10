"""HTTP API for the in-app guide (chat with Ribhiya): help content, questions, solutions and feedback."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .. import db, guide
from ..ledger.csv_import import csv_safe
from ..guide import content as guide_content
from .profit_api import _actor, _tenant

router = APIRouter(prefix="/api/guide")


def _lang(v) -> str:
    return "en" if v == "en" else "ar"


def _reject(exc: guide.GuideRejected):
    raise HTTPException(413 if exc.code == "too_long" else 422, {"code": exc.code, "message": str(exc)}) from exc


@router.get("/content")
def get_content(lang: str = "ar"):
    return guide_content.public(_lang(lang))


@router.post("/ask")
def ask(request: Request, body: dict = Body(...)):
    session = str(request.headers.get("x-tahsila-session") or "")[:64]
    session = session if session and all(ch.isalnum() or ch in "-_" for ch in session) else None
    history = body.get("history") if isinstance(body.get("history"), list) else []
    try:
        return guide.ask(db.connect(), message=str(body.get("message", "")), lang=_lang(body.get("lang")),
                         tenant=_tenant(request), actor=_actor(request), history=history[-6:],
                         session_id=f"{_tenant(request)}:guide:{session}" if session else None,
                         investigation=str(body.get("investigation") or "")[:64] or None)
    except guide.GuideRejected as exc:
        _reject(exc)


@router.get("/solutions")
def solutions(request: Request, lang: str = "ar", investigation: str | None = None):
    """Used by the investigation page only for the labelled general-ideas fallback (items of kind "general")."""
    return guide.solutions(db.connect(), tenant=_tenant(request), lang=_lang(lang), iid=investigation or None)


@router.post("/feedback")
def add_feedback(request: Request, body: dict = Body(...)):
    try:
        return guide.add_feedback(db.connect(), tenant=_tenant(request), actor=_actor(request),
                                  kind=str(body.get("kind", "other")), rating=body.get("rating"),
                                  text=str(body.get("text", "")), page=str(body.get("page", "") or ""),
                                  lang=_lang(body.get("lang")))
    except guide.GuideRejected as exc:
        _reject(exc)


@router.get("/feedback")
def list_feedback(request: Request):
    return guide.list_feedback(db.connect(), tenant=_tenant(request))


@router.get("/feedback.csv", response_class=PlainTextResponse)
def export_feedback(request: Request):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "date", "kind", "rating", "text", "page", "lang"])
    for r in guide.list_feedback(db.connect(), tenant=_tenant(request), limit=10_000):
        w.writerow([r["id"], datetime.fromtimestamp(r["created_at"], timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    r["kind"], r["rating"] or "", csv_safe(r["text"]), csv_safe(r["page"] or ""), r["lang"]])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=ribhiya_feedback.csv"})
