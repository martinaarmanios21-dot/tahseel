import { useSyncExternalStore } from "react";
import type { Customer, Decision, Insights, Status, Summary } from "./types";
import { STATUSES } from "./types";
import { mockBusinesses, mockCustomers, mockDecisions, mockInsights } from "@/mocks/data";

// ---- mock mode flag (shown as "بيانات تجريبية" badge) ----
let mockMode = false;
const listeners = new Set<() => void>();
function setMock(v: boolean) {
  if (mockMode !== v) { mockMode = v; listeners.forEach((l) => l()); }
}
export function useMockMode() {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, () => mockMode, () => false);
}

// ---- in-memory mock state ----
const db = {
  customers: structuredClone(mockCustomers),
  decisions: structuredClone(mockDecisions),
  insights: structuredClone(mockInsights),
  paused: false,
  workspace: { run_id: "demo-1", round: 1, status: "running" } as Summary["workspace"],
  learning: { first_collection_rate: 48, current_collection_rate: 61, first_complaints: 7, current_complaints: 4 },
};

export class ApiError extends Error {}

/**
 * Live API when the Tahseel server answers with JSON; demo data only when there is no server at all
 * (network failure, or an HTML page such as the Lovable preview). Real server errors are surfaced, never hidden.
 */
async function request<T>(path: string, init: RequestInit | undefined, fallback: () => T): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  } catch {
    return useFallback(fallback);
  }
  const type = res.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) return useFallback(fallback);
  const data = await res.json();
  setMock(false);
  if (!res.ok) throw new ApiError(typeof data?.detail === "string" ? data.detail : res.statusText);
  return data as T;
}
async function useFallback<T>(fallback: () => T): Promise<T> {
  setMock(true);
  await new Promise((r) => setTimeout(r, 150));
  return fallback();
}

// ---- adapt the real API to the UI's shapes (rates as %, versions as "vN", ids as strings) ----
const pct = (x: number | null | undefined) => (x == null ? null : Math.round(x * 1000) / 10);
const ver = (v: number | string) => (typeof v === "number" ? `v${v}` : v);
/* eslint-disable @typescript-eslint/no-explicit-any */
function adaptSummary(s: any): Summary {
  if (mockMode) return s;
  return {
    ...s,
    assistant: { ...s.assistant, skill_version: ver(s.assistant.skill_version) },
    learning: { ...s.learning, first_collection_rate: pct(s.learning.first_collection_rate),
                current_collection_rate: pct(s.learning.current_collection_rate),
                candidate_collection_rate: pct(s.learning.candidate_collection_rate) },
  };
}
function adaptMetrics(m: any) {
  return { ...m, collection_rate: pct(m.collection_rate) };
}
function adaptInsights(i: any): Insights {
  if (mockMode) return i;
  const w = i.waiting_for_approval;
  return {
    active: { version: ver(i.active.version), rules: i.active.rules },
    waiting_for_approval: w && w.test_results ? {
      version: ver(w.version), status: w.status, rules: w.rules,
      test_results: { passed: w.test_results.passed, reasons: w.reason_codes ?? [],
                      before: adaptMetrics(w.test_results.before), after: adaptMetrics(w.test_results.after) },
    } : null,
    history: i.history.map((h: any) => ({ ...h, version: ver(h.version) })),
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */
const by = () => ({ by: (typeof localStorage !== "undefined" && localStorage.getItem("tahseel.role")) || "dashboard" });

const post = (body?: unknown): RequestInit => (body ? { method: "POST", body: JSON.stringify(body) } : { method: "POST" });

function mockSummary(business?: string): Summary {
  const cs = db.customers.filter((c) => !business || c.business === business);
  const by = Object.fromEntries(STATUSES.map((s) => [s, 0])) as Record<Status, number>;
  cs.forEach((c) => by[c.status]++);
  const sum = (f: (c: Customer) => boolean) => cs.filter(f).reduce((a, c) => a + c.amount_egp, 0);
  const collected = sum((c) => c.status === "paid" || c.status === "paid_by_plan");
  const withTeam = sum((c) => c.status === "with_team");
  const total = sum(() => true);
  const pending = db.insights.waiting_for_approval;
  return {
    workspace: db.workspace,
    assistant: { paused: db.paused, skill_version: db.insights.active.version, busy: false },
    money: { collected_egp: collected, outstanding_egp: total - collected - withTeam, with_team_egp: withTeam, total_egp: total },
    customers_by_status: by,
    needs_your_decision: db.decisions.filter((d) => !business || d.business === business).length,
    businesses: mockBusinesses.map((b) => {
      const bc = db.customers.filter((c) => c.business === b.id);
      const col = bc.filter((c) => c.status === "paid" || c.status === "paid_by_plan").reduce((a, c) => a + c.amount_egp, 0);
      return { ...b, customers: bc.length, collected_egp: col, outstanding_egp: bc.reduce((a, c) => a + c.amount_egp, 0) - col };
    }),
    learning: { ...db.learning, update_waiting_for_approval: pending && pending.test_results.passed ? Number(pending.version.replace("v", "")) : null },
  };
}

// ---- jobs ----
type Job = { status: "idle" | "running" | "done" | "error"; error?: string | null };
let mockJobDone = 0;
function startMockJob(effect: () => void) {
  mockJobDone = Date.now() + 2500;
  setTimeout(effect, 2400);
  return { job_id: "mock" };
}

export const api = {
  summary: (business?: string) =>
    request<Summary>(`/api/summary${business ? `?business=${encodeURIComponent(business)}` : ""}`, undefined, () => mockSummary(business)).then(adaptSummary),
  decisions: () => request<Decision[]>("/api/decisions", undefined, () => db.decisions)
    .then((ds) => ds.map((d) => ({ ...d, decision_id: String(d.decision_id) }))),
  approve: (id: string) => request<{ result?: string; ok?: boolean }>(`/api/approvals/${id}/approve`, post(by()), () => resolveDecision(id, "in_progress")),
  reject: (id: string) => request(`/api/approvals/${id}/reject`, post(by()), () => resolveDecision(id, "with_team")),
  customers: () => request<Customer[]>("/api/customers", undefined, () => db.customers),
  customer: (id: string) => request<Customer>(`/api/customers/${id}`, undefined, () => db.customers.find((c) => c.invoice_id === id)!),
  insights: () => request<Insights>("/api/insights", undefined, () => db.insights).then(adaptInsights),
  promote: (v: string) => request(`/api/skills/${v.replace(/^v/, "")}/promote`, post(), () => {
    const w = db.insights.waiting_for_approval;
    if (w) {
      db.insights.history = db.insights.history.map((h) => (h.status === "active" ? { ...h, status: "retired" } : h));
      db.insights.history.push({ version: w.version, status: "active" });
      db.insights.active = { version: w.version, rules: w.rules };
      db.learning.current_collection_rate = w.test_results.after.collection_rate;
      db.learning.current_complaints = w.test_results.after.complaints;
      db.insights.waiting_for_approval = null;
    }
    return { ok: true };
  }),
  kill: (on: boolean) => request("/api/kill", post({ on }), () => { db.paused = on; return { ok: true }; }),
  newWorkspace: () => request("/api/workspace/new", post(), () => startMockJob(() => { db.workspace = { run_id: "demo-2", round: 1, status: "running" }; })),
  nextRound: () => request("/api/workspace/next-round", post(), () => startMockJob(() => {
    const w = db.customers.find((c) => c.status === "waiting");
    if (w) w.status = "in_progress";
    if (db.workspace) db.workspace.round++;
  })),
  train: () => request("/api/train", post({ episodes: 2 }), () => startMockJob(() => {})),
  learn: () => request("/api/learn", post(), () => startMockJob(() => {
    if (!db.insights.waiting_for_approval) db.insights.waiting_for_approval = structuredClone(mockInsights.waiting_for_approval);
  })),
  job: () => request<Job>("/api/job", undefined, () => ({ status: Date.now() >= mockJobDone ? "done" : "running" })),
  rollback: () => request("/api/skills/rollback", post(), () => ({ ok: true })),
};

function resolveDecision(id: string, status: Status) {
  const d = db.decisions.find((x) => x.decision_id === id);
  db.decisions = db.decisions.filter((x) => x.decision_id !== id);
  const c = d && db.customers.find((x) => x.invoice_id === d.invoice_id);
  if (c && d) {
    c.status = status;
    c.timeline = [...(c.timeline ?? []), { action: status === "with_team" ? "escalate_to_human" : d.action, status: "sent", tone: d.tone, message: status === "with_team" ? "لم تُرسل الرسالة، وأحلت العميل لفريقك." : d.message }];
  }
  return { ok: true };
}

/** Polls /api/job every 1.5s until done or error. */
export async function waitForJob(): Promise<"done" | "error"> {
  for (let i = 0; i < 200; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    const j = await api.job();
    if (j.status === "done" || j.status === "idle") return "done";
    if (j.status === "error") return "error";
  }
  return "error";
}
