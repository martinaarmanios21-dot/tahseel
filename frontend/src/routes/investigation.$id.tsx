import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, Download, FileUp, HelpCircle, Lightbulb, MessageCircle, Trash2, AlertTriangle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { AppShell } from "@/components/AppShell";
import { Md } from "@/components/Md";
import { Card, Confirm, ErrorNote, Loading, Pill, Spinner, useErrorToast } from "@/components/bits";
import { BridgeChart, CostPerOrderChart, ProductsChart, TrendChart, major, useIT } from "@/components/charts";
import { OrderProfit, Quotes, Simulator } from "@/components/profit-tools";
import { EvidenceList, Outreach } from "@/components/evidence-outreach";
import { PENDING_GO } from "@/components/GuideChat";
import { useApp } from "@/lib/app-context";
import { gapi, oapi, papi, papi2, type Question } from "@/lib/tapi";
import { cn } from "@/lib/utils";
import { needsGeneralIdeas, nextStep, steps } from "@/lib/investigation-state";

/* eslint-disable @typescript-eslint/no-explicit-any */
export const Route = createFileRoute("/investigation/$id")({
  head: () => ({ meta: [{ title: "التحقيق · Ribhiya" }] }),
  component: () => <AppShell><Investigation /></AppShell>,
});

const FIELDS: Record<string, string[]> = {
  sales: ["order_id", "date", "product", "quantity", "unit_price", "revenue", "discount", "channel", "status", "currency"],
  product_costs: ["product", "unit_cost", "currency"],
  expenses: ["date", "amount", "category", "description", "supplier", "quantity", "invoice_id", "paid", "due_date", "currency"],
  returns: ["order_id", "date", "product", "quantity", "refund_amount", "reason", "currency"],
};

type Tab = "files" | "products" | "whatif" | "suppliers" | "results";
const TABS: Tab[] = ["files", "products", "whatif", "suppliers", "results"];

/** The five steps an owner goes through. Each is "done" from real data, never from clicks alone. */
/** "Show me" from the guide: a tab or a card on this page (also replays a request made from another page). */
function GuideListener({ onGo }: { onGo: (g: { tab?: string; anchor?: string }) => void }) {
  const ref = useRef(onGo);
  ref.current = onGo;
  useEffect(() => {
    const h = (e: Event) => ref.current((e as CustomEvent).detail ?? {});
    window.addEventListener("ribhiya:go", h);
    const pending = sessionStorage.getItem(PENDING_GO);
    if (pending) { sessionStorage.removeItem(PENDING_GO); setTimeout(() => { try { ref.current(JSON.parse(pending)); } catch { /* ignore */ } }, 300); }
    return () => window.removeEventListener("ribhiya:go", h);
  }, []);
  return null;
}

function Investigation() {
  const { id } = Route.useParams();
  const { lang } = useApp();
  const it = useIT();
  const q = useQuery({ queryKey: ["inv", id, lang], queryFn: () => papi.state(id, lang), retry: false });
  const [openOutreachId, setOpenOutreach] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab | null>(null);
  if (q.isError) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Loading />;
  const s = q.data;
  const st = steps(s);
  const active: Tab = tab ?? (s.record_counts?.sales ? "products" : "files");
  const go = (t: Tab) => { setTab(t); setTimeout(() => document.getElementById("tabs")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50); };
  const guideGo = (g: { tab?: string; anchor?: string }) => {
    if (g.tab) go(g.tab as Tab);
    const el = document.getElementById(g.anchor ?? "tabs");
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.add("guide-flash");
    setTimeout(() => el.classList.remove("guide-flash"), 1800);
  };
  return (
    <div className="mx-auto grid max-w-4xl gap-5">
      <header>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-2xl font-bold">{s.investigation.title}</h1>
          <CurrencyBadge id={id} s={s} />
        </div>
        <ol className="mt-3 grid grid-cols-5 gap-1" aria-label={it("progress")}>
          {[0, 1, 2, 3, 4].map((i) => (
            <li key={i} className="grid gap-1 text-center">
              <span className={cn("h-1.5 rounded-full", st.done[i] ? "bg-primary" : i === st.current ? "bg-primary/40" : "bg-muted")} />
              <span className={cn("text-xs", i === st.current ? "font-bold text-primary" : st.done[i] ? "text-foreground" : "text-muted-foreground")}>
                {st.done[i] ? "✓ " : `${i + 1}. `}{it(`step${i + 1}`)}
              </span>
            </li>
          ))}
        </ol>
      </header>
      <GuideListener onGo={guideGo} />
      <div id="do-now" className="rounded-2xl"><DoNow s={s} id={id} go={go} openOutreach={(oid) => { setOpenOutreach(oid); go("suppliers"); }} /></div>
      {needsGeneralIdeas(s) && <GeneralIdeas id={id} />}
      <div id="leak" className="rounded-2xl"><Leak s={s} id={id} go={go} openOutreach={(oid) => { setOpenOutreach(oid); go("suppliers"); }} /></div>
      <section id="tabs" className="card-soft overflow-hidden">
        <nav className="flex overflow-x-auto border-b" role="tablist">
          {TABS.map((t) => (
            <button key={t} role="tab" aria-selected={active === t} onClick={() => setTab(t)}
              className={cn("whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium", active === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground")}>
              {it(`tab_${t}`)}{t === "suppliers" && !!s.outreach?.length ? ` (${s.outreach.length})` : ""}
            </button>
          ))}
        </nav>
        <div className="grid gap-4 p-4">
          {active === "files" && <><Files s={s} id={id} /><Memory /><Danger id={id} /></>}
          {active === "products" && (s.orders ? <><OrderProfit ov={s.orders} id={id} /><MoreCharts s={s} /></> : <Empty text={it("emptyNeedSales")} />)}
          {active === "whatif" && (s.orders?.simulator?.period ? <Simulator ov={s.orders} id={id} scenarios={s.scenarios} /> : <Empty text={it("emptyNeedSales")} />)}
          {active === "suppliers" && (s.orders ? <><Outreach s={s} id={id} openId={openOutreachId} /><div id="quotes"><Quotes id={id} currency={s.orders.currency} outreach={s.outreach} products={s.orders.products.map((p: any) => p.product)} /></div></> : <Empty text={it("emptyNeedSales")} />)}
          {active === "results" && (s.interventions.length ? <div id="tracking"><Tracking s={s} id={id} /></div> : <Empty text={it("emptyResults")} />)}
        </div>
      </section>
    </div>
  );
}

/** The currency the owner's files are in. Changing it re-labels amounts; it never converts them. */
function CurrencyBadge({ id, s }: { id: string; s: any }) {
  const it = useIT();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const [edit, setEdit] = useState(false);
  const cur: string = s.investigation.default_currency;
  const save = (c: string) => papi2.setCurrency(id, c)
    .then(() => { setEdit(false); toast.success(it("currencySaved", { c })); qc.invalidateQueries({ queryKey: ["inv", id] }); qc.invalidateQueries({ queryKey: ["investigations"] }); })
    .catch(onErr);
  if (!edit) return (
    <span className="text-sm text-muted-foreground">{it("filesCurrency")}: <b dir="ltr">{cur}</b>{" "}
      <button className="underline" onClick={() => setEdit(true)}>{it("change")}</button></span>
  );
  return (
    <span className="flex flex-wrap items-center gap-2 text-sm">
      <select defaultValue={cur} onChange={(e) => e.target.value !== cur && save(e.target.value)} aria-label={it("filesCurrency")} className="rounded-lg border bg-card px-2 py-1">
        {["EGP", "SAR", "AED", "USD", "EUR"].map((c) => <option key={c}>{c}</option>)}
      </select>
      <span className="text-xs text-muted-foreground">{it("noConversion")}</span>
      <button className="text-xs underline" onClick={() => setEdit(false)}>{it("cancelEdit")}</button>
    </span>
  );
}

/** Open the assistant and ask it a question about this investigation. */
function askRibhiya(text: string) {
  window.dispatchEvent(new CustomEvent("ribhiya:ask", { detail: { text } }));
}

/** Fallback while there's only one month (or too little data): general ideas, clearly labelled as not data-based. */
function GeneralIdeas({ id }: { id: string }) {
  const it = useIT();
  const { lang } = useApp();
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ["general-ideas", id, lang], queryFn: () => gapi.solutions(lang, id), enabled: open });
  const general = (q.data?.items ?? []).filter((x: any) => x.kind === "general");
  return (
    <section className="card-soft p-4">
      <button className="flex w-full items-center gap-2 text-start" onClick={() => setOpen(!open)}>
        <Lightbulb className="size-4 text-muted-foreground" />
        <span className="flex-1"><span className="block font-semibold">{it("generalIdeas")}</span><span className="block text-xs text-muted-foreground">{it("generalIdeasNote")}</span></span>
        <ChevronDown className={cn("size-4 transition", open && "rotate-180")} />
      </button>
      {open && general.map((g: any) => (
        <ul key={g.title} className="mt-3 grid gap-1.5 text-sm">
          {g.options.map((o: any) => <li key={o.title} className="rounded-lg bg-muted/50 p-2"><span className="font-medium">{o.title}</span><span className="block text-xs text-muted-foreground">{o.note}</span></li>)}
        </ul>
      ))}
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="py-6 text-center text-sm text-muted-foreground">{text}</p>;
}

/* --------------------------------------------------------------------------- "Do this now": one task */
function DoNow({ s, id, go, openOutreach }: { s: any; id: string; go: (t: Tab) => void; openOutreach: (oid: number) => void }) {
  const it = useIT();
  const { question: q, action: act } = nextStep(s);
  return (
    <section className="card-soft border-2 border-primary/50 p-5" aria-live="polite">
      <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-primary"><Lightbulb className="size-4" /> {it("doNow")}</div>
      {q ? <QuestionStep q={q} id={id} /> : act ? <ActionStep a={act} id={id} go={go} openOutreach={openOutreach} /> : <p className="text-lg font-semibold">{it("allDone")}</p>}
    </section>
  );
}

function WhyToggle({ children }: { children: React.ReactNode }) {
  const it = useIT();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="text-sm text-muted-foreground underline" onClick={() => setOpen(!open)}>{it("why")}</button>
      {open && <div className="mt-2 w-full rounded-lg bg-muted/50 p-3 text-sm text-muted-foreground">{children}</div>}
    </>
  );
}

function QuestionStep({ q, id }: { q: Question; id: string }) {
  const it = useIT();
  const { lang } = useApp();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const [text, setText] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const send = async (status: string, value?: string) => {
    setBusy(true);
    try { await papi.answer(id, q.id, status, value, q.kind === "profile"); setText(""); setPicked([]); await qc.invalidateQueries({ queryKey: ["inv", id] }); }
    catch (e) { onErr(e); } finally { setBusy(false); }
  };
  const isDoc = q.kind === "document" || (q.kind === "gap" && !!q.upload && !q.options.length);
  const x = q as any;
  return (
    <div>
      <h2 className="text-xl font-bold">{q.text[lang]}</h2>
      {q.options.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {q.options.map((o) => (
            <button key={o} disabled={busy} onClick={() => q.multi ? setPicked(picked.includes(o) ? picked.filter((v) => v !== o) : [...picked, o]) : send("answered", o)}
              className={cn("rounded-full border px-4 py-2 text-sm hover:border-primary", picked.includes(o) && "border-primary bg-primary-soft text-primary")}>{it(`opt_${o}`)}</button>
          ))}
          {q.multi && <button className="btn btn-primary !py-2" disabled={busy || !picked.length} onClick={() => send("answered", picked.join(","))}>{it("saveAnswer")}</button>}
        </div>
      )}
      {(isDoc || q.kind === "gap") && <div className="mt-4"><UploadBox id={id} category={q.category} upload={q.upload} /></div>}
      {!isDoc && !q.options.length && (
        <div className="mt-3 flex gap-2">
          <input value={text} onChange={(e) => setText(e.target.value)} maxLength={500} placeholder={it("yourAnswer")} className="flex-1 rounded-lg border bg-card px-3 py-2" />
          <button className="btn btn-outline !py-2" disabled={busy || !text.trim()} onClick={() => send("answered", text.trim())}>{it("saveAnswer")}</button>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-4">
        <button className="text-sm text-muted-foreground underline" disabled={busy} onClick={() => send("dont_know")}>{isDoc ? it("dontHaveFile") : it("dontKnow")}</button>
        <button className="text-sm text-muted-foreground underline" disabled={busy} onClick={() => send("skipped")}>{it("skip")}</button>
        <WhyToggle>
          <p>{q.why[lang]}</p>
          {x.if_unavailable && <p className="mt-1"><b>{it("ap_if_unavailable")}:</b> {x.if_unavailable[lang]}</p>}
        </WhyToggle>
      </div>
    </div>
  );
}

function ActionStep({ a, id, go, openOutreach }: { a: any; id: string; go: (t: Tab) => void; openOutreach: (oid: number) => void }) {
  const it = useIT();
  const { lang } = useApp();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const refresh = () => qc.invalidateQueries({ queryKey: ["inv", id] });
  const prepare = (body: Record<string, unknown>) => oapi.create(id, { ...body, lang }).then((o) => { refresh(); openOutreach(o.id); }).catch(onErr);
  const btn: Record<string, [string, () => void]> = {
    request_quotes: a.draft_ids?.length ? [it("btn_open_draft"), () => openOutreach(a.draft_ids[0])] : [it("btn_prepare_request"), () => prepare({ purpose: "quote_request", driver: a.driver })],
    await_reply: [it("btn_add_reply"), () => go("suppliers")],
    compare: [it("btn_go_compare"), () => go("suppliers")],
    moq: [it("btn_ask_moq"), () => prepare({ purpose: "moq_question", quote_id: a.quote_id })],
    track: [it("btn_track"), () => oapi.trackScenario(id, a.scenario_id).then(refresh).catch(onErr)],
    verify: [it("btn_go_tracking"), () => go("results")],
  };
  const [label, fn] = btn[a.kind] ?? [it("open"), () => go("files")];
  return (
    <div>
      <h2 className="text-xl font-bold">{it(`do_${a.kind}`)}</h2>
      <p className="mt-1 text-muted-foreground">{a.next}</p>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <button className="btn btn-primary" onClick={fn}>{label}</button>
        <WhyToggle>
          <p>{a.trigger}</p>
          {a.impact && <p className="mt-1"><b>{it("ap_impact")}:</b> {a.impact}</p>}
        </WhyToggle>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------- "What I found": the main leak */
function Leak({ s, id, go, openOutreach }: { s: any; id: string; go: (t: Tab) => void; openOutreach: (oid: number) => void }) {
  const it = useIT();
  const { lang, money } = useApp();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const [sel, setSel] = useState(0);
  const [explain, setExplain] = useState(false);
  const d = s.diagnosis;
  if (!d) return null;
  if (!d.comparable || d.gaps?.length) return null; // answer the missing-month question first
  if (!d.findings.length) return <section className="card-soft p-5"><div className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{it("whatIFound")}</div><p className="mt-2 text-lg">{it("noMaterialChange")}</p></section>;
  const f = d.findings[Math.min(sel, d.findings.length - 1)];
  const by: any = Object.fromEntries(s.charts.map((c: any) => [c.id, c]));
  const quotable = ["packaging", "shipping", "product_costs"].includes(f.driver);
  const existing = (s.outreach ?? []).find((o: any) => o.trigger?.driver === f.driver && o.status !== "cancelled");
  const fix = () => existing ? openOutreach(existing.id) : quotable
    ? oapi.create(id, { purpose: "quote_request", driver: f.driver, lang }).then((o) => { qc.invalidateQueries({ queryKey: ["inv", id] }); openOutreach(o.id); }).catch(onErr)
    : go("whatif");
  const e = f.explanation;
  return (
    <section className="card-soft p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{it("whatIFound")}</div>
        <span className="text-xs text-muted-foreground" dir="ltr">{d.base.period} → {d.current.period}</span>
      </div>
      <h2 className="mt-2 text-2xl font-bold leading-snug">{e.what}</h2>
      <p className="mt-1 text-lg">{it("perMonth", { x: money(Math.abs(f.impact_total), d.currency) })}</p>
      <div className="mt-3">{by.cost_per_order && <CostPerOrderChart c={by.cost_per_order} />}</div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button className="btn btn-primary" onClick={fix}>{quotable ? it("fixQuotes") : it("fixTry")}</button>
        <button className="text-sm underline" onClick={() => setExplain(!explain)}>{explain ? it("hideDetails") : it("explain")}</button>
        <button className="inline-flex items-center gap-1 text-sm text-primary underline" onClick={() => askRibhiya(it("askWhyQ"))}><MessageCircle className="size-4" /> {it("askWhy")}</button>
        {f.confidence !== "supported" && <Pill tone="warn">{it("conf_preliminary")}</Pill>}
      </div>
      {explain && <FindingDetails f={f} id={id} />}
      {d.findings.length > 1 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-3 text-sm">
          <span className="text-muted-foreground">{it("alsoFound")}</span>
          {d.findings.map((x: any, i: number) => i !== sel && (
            <button key={x.driver} onClick={() => { setSel(i); setExplain(false); }} className="rounded-full border px-3 py-1 hover:border-primary">
              {x.label} <span className="text-danger" dir="ltr">−{money(Math.abs(x.change_per_order), d.currency)}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function FindingDetails({ f, id }: { f: any; id: string }) {
  const it = useIT();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const e = f.explanation;
  const plan = (key: string) => papi.plan(id, f.driver, key).then(() => { toast.success(it("st_planned")); qc.invalidateQueries({ queryKey: ["inv", id] }); }).catch(onErr);
  return (
    <div className="mt-4 grid gap-3 rounded-xl bg-muted/40 p-4 text-sm">
      <p>{e.why}</p>
      <p className="text-muted-foreground">{e.evidence}</p>
      {e.caveats.map((c: string) => <p key={c} className="text-xs text-warning">{c}</p>)}
      <div>
        <div className="mb-1 font-semibold">{it("q_options")}</div>
        <ul className="grid gap-1.5">{f.recommendation.options.map((o: any) => (
          <li key={o.key} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-card px-3 py-2">
            <span>{o.title}</span>
            <button className="text-xs font-semibold text-primary underline" onClick={() => plan(o.key)}>{it("chooseThis")}</button>
          </li>))}</ul>
      </div>
      <p className="text-xs text-muted-foreground"><b>{it("projection")}:</b> {f.recommendation.projection.text}</p>
    </div>
  );
}

function MoreCharts({ s }: { s: any }) {
  const it = useIT();
  const [open, setOpen] = useState(false);
  const by: any = Object.fromEntries(s.charts.map((c: any) => [c.id, c]));
  if (!s.charts.length) return null;
  return (
    <div>
      <button className="text-sm font-semibold text-primary underline" onClick={() => setOpen(!open)}>{open ? it("hideCharts") : it("moreCharts")}</button>
      {open && (
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          {by.trend && by.trend.periods.length > 0 && <TrendChart c={by.trend} />}
          {by.bridge && <BridgeChart c={by.bridge} />}
          {by.products && <ProductsChart c={by.products} />}
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------- uploads */
function UploadBox({ id, category, upload }: { id: string; category?: string | null; upload?: string | null }) {
  const it = useIT();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [manual, setManual] = useState({ month: "", amount: "" });
  const go = async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    try {
      const r = await papi.upload(id, files);
      r.results.forEach((x, i) => x.status === "imported" ? toast.success(`${files[i]?.name}: ${it("imported")}`) : toast.error(`${files[i]?.name}: ${x.summary.fatal ?? it("failed")}`));
      await qc.invalidateQueries({ queryKey: ["inv", id] });
    } catch (e) { onErr(e); } finally { setBusy(false); }
  };
  return (
    <div className="grid gap-3">
      <label onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); go(Array.from(e.dataTransfer.files)); }}
        className={cn("flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed p-6 text-center", drag ? "border-primary bg-primary-soft" : "hover:border-primary/60")}>
        <FileUp className="size-7 text-primary" />
        <span className="btn btn-primary pointer-events-none !py-2">{it("uploadFiles")}</span>
        <span className="text-xs text-muted-foreground">{it("uploadHint")}</span>
        <input type="file" multiple accept=".csv,.xlsx,.xlsm,.pdf,text/csv" className="sr-only" onChange={(e) => go(Array.from(e.target.files ?? []))} />
      </label>
      <Spinner show={busy} label={it("processing")} />
      {(upload || category) && <OtherWays upload={upload} category={category} id={id} manual={manual} setManual={setManual} />}
    </div>
  );
}

function OtherWays({ upload, category, id, manual, setManual }: { upload: string | null | undefined; category: string | null | undefined; id: string; manual: { month: string; amount: string }; setManual: (m: { month: string; amount: string }) => void }) {
  const it = useIT();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const [open, setOpen] = useState(false);
  if (!open) return <button className="w-fit text-sm text-muted-foreground underline" onClick={() => setOpen(true)}>{it("otherWays")}</button>;
  return (
    <div className="grid gap-2 rounded-lg bg-muted/40 p-3">
      {upload && <a className="inline-flex w-fit items-center gap-1 text-sm text-primary underline" href={`/api/profit/templates/${upload}.csv`}><Download className="size-3.5" /> {it("template")}</a>}
      {category && (
        <form className="flex flex-wrap items-end gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); papi.manual(id, { category, ...manual }).then(() => { setManual({ month: "", amount: "" }); qc.invalidateQueries({ queryKey: ["inv", id] }); }).catch(onErr); }}>
          <span className="w-full text-muted-foreground">{it("typeManually")}</span>
          <input type="month" required value={manual.month} onChange={(e) => setManual({ ...manual, month: e.target.value })} aria-label={it("month")} className="rounded-lg border bg-card px-2 py-1.5" />
          <input required inputMode="decimal" value={manual.amount} onChange={(e) => setManual({ ...manual, amount: e.target.value })} placeholder={it("amount")} className="w-32 rounded-lg border bg-card px-2 py-1.5" dir="ltr" />
          <button className="btn btn-outline !py-1.5">{it("add")}</button>
        </form>
      )}
    </div>
  );
}

function Files({ s, id }: { s: any; id: string }) {
  const it = useIT();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const files = s.files.filter((f: any) => f.status !== "removed");
  return (
    <Card title={it("filesTitle")}>
      <EvidenceList items={s.evidence} />
      <UploadBox id={id} />
      {!!files.length && (
        <ul className="mt-4 grid gap-2">
          {files.map((f: any) => <FileRow key={f.id} f={f} id={id} onRemove={() => papi.removeFile(id, f.id).then(() => qc.invalidateQueries({ queryKey: ["inv", id] })).catch(onErr)} />)}
        </ul>
      )}
    </Card>
  );
}

function FileRow({ f, id, onRemove }: { f: any; id: string; onRemove: () => void }) {
  const it = useIT();
  const [open, setOpen] = useState(false);
  const ok = f.status === "imported";
  return (
    <li className="rounded-xl border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {ok ? <CheckCircle2 className="size-4 text-success" /> : <AlertTriangle className="size-4 text-danger" />}
        <span className="font-semibold" dir="auto">{f.filename}</span>
        <Pill tone={ok ? "ok" : "danger"}>{ok ? it("imported") : it("failed")}</Pill>
        <button className="ms-auto text-xs underline" onClick={() => setOpen(!open)}>{it("issues")} <ChevronDown className="inline size-3" /></button>
        <button onClick={onRemove} aria-label={it("remove")} className="rounded p-1 text-danger hover:bg-danger/10"><Trash2 className="size-4" /></button>
      </div>
      {f.summary.fatal && <p className="mt-1 text-danger" dir="auto">{f.summary.fatal}</p>}
      {f.summary.tables.map((t: any) => (
        <div key={t.sheet} className="mt-2 rounded-lg bg-muted/50 p-2">
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="font-mono">{t.sheet}</span>
            <span>{it("detectedAs")}: <b>{it(`type_${t.detected_type}`)}</b></span>
            <span>{t.rows_valid} {it("rowsValid")}</span>
            {!!t.rows_rejected && <span className="text-danger">{t.rows_rejected} {it("rowsRejected")}</span>}
            {t.mapping_reused_from_memory && <Pill tone="primary">{it("mappingReused")}</Pill>}
            {!!t.periods.length && <span dir="ltr">{t.periods[0]} → {t.periods.at(-1)}</span>}
          </div>
          {t.needs_confirmation.map((n: string) => <p key={n} className="mt-1 text-xs text-warning" dir="auto">{n}</p>)}
          {(t.detected_type === null || t.needs_confirmation.length > 0 || t.missing_required.length > 0) && <MappingFix t={t} id={id} fileId={f.id} />}
          {open && t.issues.length > 0 && (
            <ul className="mt-2 max-h-40 overflow-auto text-xs" dir="ltr">
              {t.issues.map((x: any, i: number) => <li key={i} className={x.severity === "error" ? "text-danger" : "text-warning"}>row {x.row} · {x.field} · {x.message}</li>)}
            </ul>
          )}
        </div>
      ))}
    </li>
  );
}

function MappingFix({ t, id, fileId }: { t: any; id: string; fileId: number }) {
  const it = useIT();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<string>(t.detected_type ?? "sales");
  const [map, setMap] = useState<Record<string, string>>(t.mapping ?? {});
  const fileRef = useRef<HTMLInputElement>(null);
  const apply = async (file?: File) => {
    if (!file) return;
    try {
      const r = await papi.upload(id, [file], { overrides: { [t.sheet]: { type, mapping: Object.fromEntries(Object.entries(map).filter(([, v]) => v)) } }, confirm: true, replace_file_id: fileId });
      r.results[0]?.status === "imported" ? toast.success(it("imported")) : toast.error(r.results[0]?.summary.fatal ?? it("failed"));
      await qc.invalidateQueries({ queryKey: ["inv", id] });
    } catch (e) { onErr(e); }
  };
  if (!open) return <button className="mt-2 text-xs font-semibold text-primary underline" onClick={() => setOpen(true)}>{it("fixMapping")}</button>;
  return (
    <div className="mt-2 grid gap-2 rounded-lg border bg-card p-2 text-xs">
      <select value={type} onChange={(e) => { setType(e.target.value); setMap({}); }} className="w-fit rounded border px-2 py-1">
        {Object.keys(FIELDS).map((k) => <option key={k} value={k}>{it(`type_${k}`)}</option>)}
      </select>
      <div className="grid gap-1 sm:grid-cols-2">
        {FIELDS[type]!.map((f) => (
          <label key={f} className="flex items-center justify-between gap-2"><span className="font-mono" dir="ltr">{f}</span>
            <select value={map[f] ?? ""} onChange={(e) => setMap({ ...map, [f]: e.target.value })} className="max-w-[60%] rounded border px-1 py-0.5">
              <option value="">—</option>{t.headers.map((h: string) => <option key={h} value={h}>{h}</option>)}
            </select></label>
        ))}
      </div>
      <p className="text-muted-foreground">{it("reuploadNeeded")}</p>
      <button className="btn btn-primary w-fit !py-1.5 text-xs" onClick={() => fileRef.current?.click()}>{it("confirmMapping")}</button>
      <input ref={fileRef} type="file" className="sr-only" accept=".csv,.xlsx,.xlsm,.pdf" onChange={(e) => apply(e.target.files?.[0])} />
    </div>
  );
}

/* --------------------------------------------------------------------------- findings */
/* --------------------------------------------------------------------------- tracking */
function Tracking({ s, id }: { s: any; id: string }) {
  const it = useIT();
  const { money } = useApp();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const [dates, setDates] = useState<Record<number, string>>({});
  const refresh = () => qc.invalidateQueries({ queryKey: ["inv", id] });
  return (
    <Card title={it("trackingTitle")}>
      <ul className="grid gap-3">
        {s.interventions.map((x: any) => {
          const r = x.result;
          const tone = x.status === "verified_improvement" ? "ok" : ["no_measurable_improvement", "inconclusive"].includes(x.status) ? "warn" : "primary";
          return (
            <li key={x.id} className="rounded-xl border p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2"><b>{x.title}</b><Pill tone={tone as any}>{it(`st_${x.status}`)}</Pill><span className="font-mono text-xs">{x.option_key}</span></div>
              <div className="mt-1 text-xs text-muted-foreground">{it("baseline")}: <span dir="ltr">{x.baseline.period}</span> · {money(Math.round(x.baseline.per_order), x.currency)} {it("perOrder")} · {x.baseline.orders}</div>
              <div className="mt-1 text-xs"><b>{it("projection")}:</b> {x.projection.text}</div>
              {x.status === "planned" && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span>{it("markStarted")}</span>
                  <input type="date" value={dates[x.id] ?? ""} onChange={(e) => setDates({ ...dates, [x.id]: e.target.value })} className="rounded border px-2 py-1" />
                  <button className="btn btn-outline !py-1 text-xs" disabled={!dates[x.id]} onClick={() => papi.setStatus(id, x.id, "in_progress", dates[x.id]).then(refresh).catch(onErr)}>{it("saveAnswer")}</button>
                </div>
              )}
              {x.implemented_on && <button className="btn btn-primary mt-2 !py-1.5 text-xs" onClick={() => papi.verify(id, x.id).then(refresh).catch(onErr)}>{it("checkResult")}</button>}
              {r && (
                <div className="mt-2 rounded-lg bg-muted/60 p-2 text-xs">
                  {r.post_per_order != null && <div>{it("afterChange")} ({r.orders_after}): {money(Math.round(r.post_per_order), x.currency)} {it("perOrder")} · {r.change_pct != null ? `${(r.change_pct * 100).toFixed(1)}%` : ""}</div>}
                  {r.reasons?.map((m: string) => <div key={m} className="text-warning" dir="auto">• {m}</div>)}
                  {r.notes?.map((m: string) => <div key={m} className="text-warning" dir="auto">• {m}</div>)}
                  {x.status === "verified_improvement" && <div className="mt-1 font-medium">{it("observedNote")}</div>}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/* --------------------------------------------------------------------------- advisor, memory, delete */
function Memory() {
  const it = useIT();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const q = useQuery({ queryKey: ["memory"], queryFn: papi.memory });
  if (!q.data) return null;
  const active = q.data.entries.filter((e: any) => e.status === "active");
  const rel = q.data.mapping_reliability;
  return (
    <Card title={it("memoryTitle")}>
      <p className="text-xs text-muted-foreground">{it("memoryNote")}</p>
      <p className="mt-1 text-xs">{it("mappingStats", { m: rel.mappings, u: rel.reuses, c: rel.corrections })}</p>
      {!!active.length && (
        <ul className="mt-2 grid gap-1 text-sm">
          {active.map((e: any) => (
            <li key={e.id} className="flex items-center gap-2 rounded-lg bg-muted/50 px-2 py-1">
              <Pill>{e.kind}</Pill><span className="flex-1 truncate" dir="auto">{e.kind === "mapping" ? `${e.value.type} · ${e.value.example_file}` : `${e.key}: ${typeof e.value === "string" ? e.value : JSON.stringify(e.value)}`}</span>
              <button className="text-xs text-danger underline" onClick={() => papi.retire(e.id).then(() => qc.invalidateQueries({ queryKey: ["memory"] })).catch(onErr)}>{it("forget")}</button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Danger({ id }: { id: string }) {
  const it = useIT();
  const nav = useNavigate();
  const onErr = useErrorToast();
  const [ask, setAsk] = useState(false);
  return (
    <div className="text-center">
      <button className="text-xs text-danger underline" onClick={() => setAsk(true)}>{it("deleteInvestigation")}</button>
      <Confirm open={ask} danger text={it("confirmDeleteInv")} onNo={() => setAsk(false)} onYes={() => { setAsk(false); papi.remove(id).then(() => nav({ to: "/" })).catch(onErr); }} />
    </div>
  );
}

export { major };
