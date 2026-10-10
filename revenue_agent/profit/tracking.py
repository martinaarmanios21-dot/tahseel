"""Improvement tracking: baseline -> intervention -> verification against updated records.

Statuses: suggested, awaiting_decision, planned, in_progress, awaiting_data, verified_improvement,
no_measurable_improvement, inconclusive, rejected.

Vocabulary kept strictly apart:
- projected saving   : an estimate from stated assumptions (stored in `projection`, never moved into results)
- observed reduction : per-order cost measured lower in orders AFTER the owner-reported implementation date
- verified improvement: an observed reduction with enough comparable orders (≥ MIN_ORDERS), no large shift in order
  value or product mix, and no rise in return rate. Even then: "observed after the change; causation not proven".
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import date

from .. import db
from ..ledger.store import audit
from . import memory, metrics, store

STATUSES = ("suggested", "awaiting_decision", "planned", "in_progress", "awaiting_data", "verified_improvement",
            "no_measurable_improvement", "inconclusive", "rejected")
MIN_ORDERS = 30
MIN_IMPROVEMENT = 0.05      # ≥5% lower per-order cost counts as a measurable improvement
MAX_AOV_SHIFT = 0.15        # bigger changes in average order value make the comparison not like-for-like
MAX_MIX_SHIFT = 0.15        # change in the top product's share of units
FIELD = {"product_costs": "cogs", "price_and_mix": "gross_sales"}


def _field(driver: str) -> str:
    return FIELD.get(driver, driver)


def _mix(records: list[dict], cur: str, start: str, end: str | None) -> dict[str, float]:
    units: dict[str, float] = {}
    for r in records:
        if r["type"] == "sales" and r["currency"] == cur and r["status"] != "cancelled" and start <= r["date"] and \
                (end is None or r["date"] <= end):
            units[r.get("product") or "(unnamed)"] = units.get(r.get("product") or "(unnamed)", 0) + r["quantity"]
    tot = sum(units.values()) or 1
    return {k: round(v / tot, 4) for k, v in units.items()}


def create(conn: sqlite3.Connection, iid: str, *, tenant: str, actor: str, finding: dict, option_key: str,
           diagnosis: dict) -> dict:
    """Owner accepts a recommendation: save the baseline (the current period of the diagnosis) and the projection."""
    store.get(conn, iid, tenant)
    cur, c = diagnosis["currency"], diagnosis["current"]
    recs = store.records(conn, iid)
    p_start = c["period"] + "-01"
    baseline = {"period": c["period"], "per_order": c["per_order"][_field(finding["driver"])], "orders": c["orders"],
                "aov": c["aov"], "return_rate": c["return_rate"], "mix": _mix(recs, cur, p_start, c["period"] + "-31"),
                "compared_with": diagnosis["base"]["period"]}
    projection = finding["recommendation"]["projection"]
    now = time.time()
    with db.tx(conn):
        cur_ = conn.execute(
            "INSERT INTO interventions(investigation_id, driver, title, option_key, currency, baseline, projection, "
            "status, created_at, updated_at) VALUES(?,?,?,?,?,?,?, 'planned', ?, ?)",
            (iid, finding["driver"], finding.get("label", finding["driver"])[:120], option_key[:60], cur,
             json.dumps(baseline), json.dumps(projection, ensure_ascii=False), now, now))
        audit(conn, actor, "intervention_planned", tenant=tenant, investigation=iid, intervention=cur_.lastrowid,
              driver=finding["driver"], option=option_key)
    return get(conn, iid, cur_.lastrowid)


SCENARIO_DRIVER = {"packaging_per_order": "packaging", "shipping_per_order": "shipping",
                   "price_change_pct": "price_and_mix", "discount_pct": "discounts", "product_unit_cost": "product_costs",
                   "return_rate_pct": "refunds", "free_shipping": "shipping_income"}


def create_from_scenario(conn: sqlite3.Connection, iid: str, *, tenant: str, actor: str, scenario_id: int) -> dict:
    """Turn a saved what-if scenario into a tracked experiment: baseline = the scenario's month (actual metrics),
    projection = the scenario result (labelled). Verification then uses the normal before/after rules."""
    store.get(conn, iid, tenant)
    row = db.one(conn.execute("SELECT * FROM scenarios WHERE id=? AND investigation_id=?", (scenario_id, iid)))
    if row is None:
        raise store.NotFound(str(scenario_id))
    if row["intervention_id"]:
        raise ValueError("this scenario is already being tracked")
    params, res = json.loads(row["params"]), json.loads(row["result"])
    levers = [k for k in params if k in SCENARIO_DRIVER]
    if not levers:
        raise ValueError("a volume-only scenario has no cost or price lever to verify")
    driver = SCENARIO_DRIVER[levers[0]]
    recs = store.records(conn, iid)
    m = next((p for p in metrics.compute(recs)["periods"] if p["period"] == res["period"]
              and p["currency"] == res["currency"]), None)
    if m is None:
        raise ValueError("the scenario month has no data any more")
    baseline = {"period": m["period"], "per_order": m["per_order"].get(_field(driver)) or 0, "orders": m["orders"],
                "aov": m["aov"], "return_rate": m["return_rate"],
                "mix": _mix(recs, res["currency"], m["period"] + "-01", m["period"] + "-31"), "compared_with": None,
                "scenario_id": scenario_id}
    projection = {"type": "projection", "monthly": res["delta"]["contribution"], "currency": res["currency"],
                  "text": res["summary"], "assumptions": res["assumptions"], "scenario": params}
    now = time.time()
    with db.tx(conn):
        cur = conn.execute(
            "INSERT INTO interventions(investigation_id, driver, title, option_key, currency, baseline, projection, "
            "status, created_at, updated_at) VALUES(?,?,?,?,?,?,?, 'planned', ?, ?)",
            (iid, driver, row["name"][:120], "scenario", res["currency"], json.dumps(baseline),
             json.dumps(projection, ensure_ascii=False), now, now))
        conn.execute("UPDATE scenarios SET intervention_id=? WHERE id=?", (cur.lastrowid, scenario_id))
        audit(conn, actor, "scenario_to_experiment", tenant=tenant, investigation=iid, scenario=scenario_id,
              intervention=cur.lastrowid, driver=driver)
    return get(conn, iid, cur.lastrowid)


def get(conn: sqlite3.Connection, iid: str, xid: int) -> dict:
    r = db.one(conn.execute("SELECT * FROM interventions WHERE id=? AND investigation_id=?", (xid, iid)))
    if r is None:
        raise store.NotFound(str(xid))
    for k in ("baseline", "projection", "result"):
        r[k] = json.loads(r[k]) if r[k] else None
    return r


def list_for(conn: sqlite3.Connection, iid: str) -> list[dict]:
    return [get(conn, iid, r[0]) for r in conn.execute("SELECT id FROM interventions WHERE investigation_id=? "
                                                       "ORDER BY id DESC", (iid,))]


def set_status(conn: sqlite3.Connection, iid: str, xid: int, *, tenant: str, actor: str, status: str,
               implemented_on: str | None = None, note: str | None = None) -> dict:
    store.get(conn, iid, tenant)
    x = get(conn, iid, xid)
    if status not in ("planned", "in_progress", "rejected", "awaiting_decision"):
        raise ValueError("owners can set planned, in_progress (with the date it started), awaiting_decision or rejected;"
                         " verification statuses are computed from data")
    if status == "in_progress":
        try:
            d = date.fromisoformat(implemented_on or "")
        except ValueError as exc:
            raise ValueError("implemented_on (YYYY-MM-DD) is required when marking a change as started") from exc
        if d.isoformat()[:7] < x["baseline"]["period"]:
            raise ValueError("the change cannot start before its baseline period")
        implemented_on = d.isoformat()
    with db.tx(conn):
        conn.execute("UPDATE interventions SET status=?, implemented_on=COALESCE(?, implemented_on), "
                     "implementation_note=COALESCE(?, implementation_note), updated_at=? WHERE id=?",
                     (status, implemented_on, (note or "")[:300] or None, time.time(), xid))
        audit(conn, actor, "intervention_status", tenant=tenant, investigation=iid, intervention=xid, status=status,
              implemented_on=implemented_on, evidence="owner_reported")
    return get(conn, iid, xid)


def verify(conn: sqlite3.Connection, iid: str, xid: int, *, tenant: str, actor: str) -> dict:
    """Compare per-order cost in orders after the implementation date against the saved baseline."""
    store.get(conn, iid, tenant)
    x = get(conn, iid, xid)
    if not x["implemented_on"]:
        raise ValueError("mark the change as started (with its date) before verifying")
    recs = store.records(conn, iid)
    after = [r for r in recs if r.get("date") and r["date"] >= x["implemented_on"]]
    window = metrics.compute(after)
    rows = [p for p in window["periods"] if p["currency"] == x["currency"] and p["orders"]]
    reasons, notes = [], []
    if not rows:
        result = {"status": "awaiting_data", "reasons": ["no orders dated on/after the implementation date yet"]}
    else:
        # Aggregate the post-change window into one comparable figure (orders-weighted).
        orders = sum(p["orders"] for p in rows)
        f = _field(x["driver"])
        val_total = sum(p["per_order"][f] * p["orders"] for p in rows)
        post = val_total / orders
        net = sum(p["net_sales"] for p in rows)
        aov = net / orders
        rr = [p["return_rate"] for p in rows if p["return_rate"] is not None]
        post_rr = sum(rr) / len(rr) if rr else None
        base = x["baseline"]
        change = metrics._ratio(post - base["per_order"], base["per_order"]) if base["per_order"] else None
        cost_like = x["driver"] not in ("price_and_mix", "shipping_income")
        improved = change is not None and ((change <= -MIN_IMPROVEMENT) if cost_like else (change >= MIN_IMPROVEMENT))
        mix_after = _mix(recs, x["currency"], x["implemented_on"], None)
        top = max(base["mix"], key=base["mix"].get) if base["mix"] else None
        mix_shift = abs(mix_after.get(top, 0) - base["mix"].get(top, 0)) if top else 0
        aov_shift = abs(aov - base["aov"]) / base["aov"] if base.get("aov") else 0
        if orders < MIN_ORDERS:
            reasons.append(f"only {orders} orders since the change (need {MIN_ORDERS})")
        if aov_shift > MAX_AOV_SHIFT:
            reasons.append(f"average order value moved {aov_shift:.0%}: orders are not like-for-like")
        if mix_shift > MAX_MIX_SHIFT:
            reasons.append(f"product mix changed (top product share moved {mix_shift:.0%})")
        if post_rr is not None and base.get("return_rate") is not None and post_rr > base["return_rate"] + 0.02:
            notes.append(f"return rate rose from {base['return_rate']:.1%} to {post_rr:.1%}: check quality impact")
        if window["periods"] and any("packaging" in p["missing"] or "shipping" in p["missing"] for p in rows) and \
                x["driver"] in ("packaging", "shipping"):
            reasons.append(f"{x['driver']} records are missing for part of the period after the change")
        if reasons:
            status = "inconclusive" if orders >= 1 else "awaiting_data"
            if orders < MIN_ORDERS and len(reasons) == 1:
                status = "awaiting_data"
        elif improved and not notes:
            status = "verified_improvement"
        elif improved:
            status = "inconclusive"
            reasons.append("cost improved but a quality signal worsened")
        else:
            status = "no_measurable_improvement"
        observed = (base["per_order"] - post) * orders if cost_like else (post - base["per_order"]) * orders
        result = {"status": status, "orders_after": orders, "post_per_order": round(post, 2),
                  "baseline_per_order": base["per_order"], "change_pct": change, "aov_shift": round(aov_shift, 4),
                  "mix_shift": round(mix_shift, 4), "post_return_rate": post_rr, "reasons": reasons, "notes": notes,
                  "observed_difference_total": round(observed),
                  "statement": ("Observed after the change; this does not prove the change caused it."
                                if status == "verified_improvement" else None),
                  "window": {"from": x["implemented_on"], "periods": [p["period"] for p in rows]}}
    result["checked_at"] = time.time()
    with db.tx(conn):
        conn.execute("UPDATE interventions SET status=?, result=?, updated_at=? WHERE id=?",
                     (result["status"], json.dumps(result), time.time(), xid))
        audit(conn, actor, "intervention_verified", tenant=tenant, investigation=iid, intervention=xid,
              status=result["status"])
    if result["status"] in ("verified_improvement", "no_measurable_improvement"):  # outcome memory: verified only
        memory.remember(conn, tenant, "outcome", f"{x['driver']}:{x['option_key']}:{xid}",
                        {"driver": x["driver"], "option": x["option_key"], "status": result["status"],
                         "change_pct": result.get("change_pct"), "orders_after": result.get("orders_after")},
                        "verified_outcome")
    return get(conn, iid, xid)
