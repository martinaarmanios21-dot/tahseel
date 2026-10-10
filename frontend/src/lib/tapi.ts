/* Ribhiya API client. Talks only to the real backend: there is no mock/demo fallback. */
/* eslint-disable @typescript-eslint/no-explicit-any */

export class ApiError extends Error {
  code: string;
  blocks: { code: string; reason: string }[];
  status: number;
  detail: any;
  constructor(status: number, detail: any) {
    const d = typeof detail === "object" && detail ? detail : { message: String(detail ?? "") };
    super(d.message || d.code || `HTTP ${status}`);
    this.status = status;
    this.code = d.code || (typeof detail === "string" ? detail : `http_${status}`);
    this.blocks = d.blocks || [];
    this.detail = d;
  }
}

function headers(json = true): Record<string, string> {
  const h: Record<string, string> = {};
  if (json) h["Content-Type"] = "application/json";
  const token = typeof localStorage !== "undefined" ? localStorage.getItem("tahsila.token") : null;
  if (token) h["X-Tahsila-Token"] = token;
  if (typeof sessionStorage !== "undefined") {
    let sid = sessionStorage.getItem("tahsila.session");
    if (!sid) { sid = crypto.randomUUID().replace(/-/g, ""); sessionStorage.setItem("tahsila.session", sid); }
    h["X-Tahsila-Session"] = sid; // per-tab chat session: the server enforces a token budget per session
  }
  return h;
}

async function req<T>(path: string, init?: RequestInit, json = true): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers: { ...headers(json), ...(init?.headers ?? {}) } });
  } catch {
    throw new ApiError(0, { code: "network", message: "server unreachable" });
  }
  const type = res.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) {
    if (!res.ok) throw new ApiError(res.status, { code: `http_${res.status}` });
    throw new ApiError(res.status, { code: "not_json", message: "the Ribhiya server is not running behind this page" });
  }
  const data = await res.json();
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data);
  return data as T;
}

const post = (body?: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body ?? {}) });

export interface Status { kill_switch: boolean; llm_configured: boolean; email_configured: boolean }

/* App-wide: emergency stop state and the stop button. */
export const tapi = {
  status: () => req<Status>("/api/status"),
  kill: (on: boolean) => req("/api/kill", post({ on })),
};

export interface InvSummary { id: string; title: string; stage: string; default_currency: string; created_at: number; updated_at: number; file_count: number; profile: Record<string, string> }
export interface Question { id: string; kind: "profile" | "document" | "evidence" | "gap"; options: string[]; multi: boolean; upload: string | null; category: string | null; text: { en: string; ar: string }; why: { en: string; ar: string } }

export const papi = {
  list: () => req<InvSummary[]>("/api/investigations"),
  create: (title: string, currency: string) => req<InvSummary>("/api/investigations", post({ title, currency })),
  state: (id: string, lang: string, base?: string, current?: string) =>
    req<any>(`/api/investigations/${encodeURIComponent(id)}?${new URLSearchParams({ lang, ...(base ? { base } : {}), ...(current ? { current } : {}) })}`),
  remove: (id: string) => req(`/api/investigations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  upload: (id: string, files: File[], extra?: { overrides?: unknown; confirm?: boolean; replace_file_id?: number }) => {
    const f = new FormData();
    files.forEach((x) => f.append("files", x));
    if (extra?.overrides) f.append("overrides", JSON.stringify(extra.overrides));
    if (extra?.confirm) f.append("confirm", "true");
    if (extra?.replace_file_id) f.append("replace_file_id", String(extra.replace_file_id));
    return req<{ results: { file_id: number; status: string; summary: any }[] }>(`/api/investigations/${encodeURIComponent(id)}/files`, { method: "POST", body: f }, false);
  },
  removeFile: (id: string, fid: number) => req(`/api/investigations/${encodeURIComponent(id)}/files/${fid}`, { method: "DELETE" }),
  answer: (id: string, qid: string, status: string, value?: string, remember?: boolean) =>
    req(`/api/investigations/${encodeURIComponent(id)}/answers`, post({ qid, status, value, remember })),
  manual: (id: string, body: { category: string; month: string; amount: string; note?: string }) =>
    req(`/api/investigations/${encodeURIComponent(id)}/manual`, post(body)),
  plan: (id: string, driver: string, option_key: string) => req<any>(`/api/investigations/${encodeURIComponent(id)}/interventions`, post({ driver, option_key })),
  setStatus: (id: string, xid: number, status: string, implemented_on?: string, note?: string) =>
    req<any>(`/api/investigations/${encodeURIComponent(id)}/interventions/${xid}/status`, post({ status, implemented_on, note })),
  verify: (id: string, xid: number) => req<any>(`/api/investigations/${encodeURIComponent(id)}/interventions/${xid}/verify`, post()),
  ask: (id: string, question: string, lang: string) => req<any>(`/api/investigations/${encodeURIComponent(id)}/advisor`, post({ question, lang })),
  memory: () => req<any>("/api/memory"),
  retire: (entry: number) => req(`/api/memory/${entry}/retire`, post()),
};

export const papi2 = {
  orders: (id: string, filter = "all", offset = 0) => req<any>(`/api/investigations/${encodeURIComponent(id)}/orders?filter=${filter}&offset=${offset}&limit=50`),
  setCurrency: (id: string, currency: string) => req<any>(`/api/investigations/${encodeURIComponent(id)}/currency`, { method: "PUT", body: JSON.stringify({ currency }) }),
  setAllocation: (id: string, allocation: Record<string, string>) => req<any>(`/api/investigations/${encodeURIComponent(id)}/allocation`, { method: "PUT", body: JSON.stringify({ allocation }) }),
  simulate: (id: string, scenario: Record<string, unknown>, period: string | undefined, lang: string) => req<any>(`/api/investigations/${encodeURIComponent(id)}/simulate`, post({ scenario, period, lang })),
  saveScenario: (id: string, scenario: Record<string, unknown>, period: string | undefined, name: string, track: boolean, lang: string) =>
    req<any>(`/api/investigations/${encodeURIComponent(id)}/scenarios`, post({ scenario, period, name, track, lang })),
};

export const qapi = {
  list: (id: string) => req<any[]>(`/api/investigations/${encodeURIComponent(id)}/quotes`),
  add: (id: string, body: Record<string, unknown>) => req<any>(`/api/investigations/${encodeURIComponent(id)}/quotes`, post(body)),
  confirm: (id: string, qid: number, body: Record<string, boolean>) => req<any>(`/api/investigations/${encodeURIComponent(id)}/quotes/${qid}/confirm`, post(body)),
  remove: (id: string, qid: number) => req(`/api/investigations/${encodeURIComponent(id)}/quotes/${qid}`, { method: "DELETE" }),
  compare: (id: string, item_key: string, quantity?: string) =>
    req<any>(`/api/investigations/${encodeURIComponent(id)}/quotes/compare?${new URLSearchParams({ item_key, ...(quantity ? { quantity } : {}) })}`),
};

export const oapi = {
  create: (id: string, body: Record<string, unknown>) => req<any>(`/api/investigations/${encodeURIComponent(id)}/outreach`, post(body)),
  edit: (id: string, oid: number, body: Record<string, unknown>) => req<any>(`/api/investigations/${encodeURIComponent(id)}/outreach/${oid}`, { method: "PUT", body: JSON.stringify(body) }),
  act: (id: string, oid: number, verb: string, body?: Record<string, unknown>) => req<any>(`/api/investigations/${encodeURIComponent(id)}/outreach/${oid}/${verb}`, post(body)),
  trackScenario: (id: string, sid: number) => req<any>(`/api/investigations/${encodeURIComponent(id)}/scenarios/${sid}/track`, post()),
  extractQuote: (id: string, file: File) => { const f = new FormData(); f.append("file", file); return req<any>(`/api/investigations/${encodeURIComponent(id)}/quotes/extract`, { method: "POST", body: f }, false); },
};

/* In-app guide (chat with Ribhiya). */
export type GuideGo = { route?: string; tab?: string; anchor?: string } | null;
export type GuideAction = { type: "go"; go: GuideGo; label: string } | { type: "panel"; panel: string; label: string };
export type GuideReply = {
  answer: string; topic: string | null; mode: string; actions: GuideAction[]; links: { kind: string; label: string; url: string }[];
  /** help = written help content · help_ai = AI without your data · state = this investigation's state · your_numbers = the profit advisor */
  source?: "help" | "help_ai" | "state" | "your_numbers"; engine?: "rules" | "api" | "hermes"; ungrounded_figures?: string[];
};
export const gapi = {
  content: (lang: string) => req<any>(`/api/guide/content?lang=${lang}`),
  ask: (message: string, lang: string, history: { role: string; text: string }[], investigation?: string) =>
    req<GuideReply>("/api/guide/ask", post({ message, lang, history, investigation })),
  solutions: (lang: string, investigation?: string) => req<any>(`/api/guide/solutions?lang=${lang}${investigation ? `&investigation=${encodeURIComponent(investigation)}` : ""}`),
  feedback: (body: { kind: string; rating: number | null; text: string; page: string; lang: string }) => req<any>("/api/guide/feedback", post(body)),
  myFeedback: () => req<any[]>("/api/guide/feedback"),
};
