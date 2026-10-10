/* Action plan, evidence checklist and supplier requests: contextual next steps inside the investigation. */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { ArrowDownRight, CheckCircle2, Mail } from "lucide-react";
import { Card, Pill, useErrorToast } from "./bits";
import { useIT } from "./charts";
import { useStatus } from "./AppShell";
import { useApp } from "@/lib/app-context";
import { oapi } from "@/lib/tapi";
import { cn } from "@/lib/utils";

/* eslint-disable @typescript-eslint/no-explicit-any */
const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

export function ActionPlan({ s, id, onOpenOutreach }: { s: any; id: string; onOpenOutreach: (oid: number) => void }) {
  const it = useIT();
  const { lang } = useApp();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const refresh = () => qc.invalidateQueries({ queryKey: ["inv", id] });
  const prepare = (body: Record<string, unknown>) =>
    oapi.create(id, { ...body, lang }).then((o) => { refresh(); onOpenOutreach(o.id); setTimeout(() => scrollTo("outreach"), 300); }).catch(onErr);
  const acts: any[] = s.actions ?? [];
  if (!s.record_counts?.sales) return null;
  return (
    <Card title={it("ap_title")}>
      {!acts.length ? <p className="text-sm text-muted-foreground">{it("ap_none")}</p> : (
        <ol className="grid gap-3">
          {acts.map((a, i) => (
            <li key={i} className="rounded-xl border p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2"><Pill tone="primary">{it(`act_${a.kind}`)}</Pill><b dir="auto">{a.title}</b></div>
              <dl className="mt-2 grid gap-1">
                <div><dt className="inline font-semibold text-muted-foreground">{it("ap_trigger")}: </dt><dd className="inline" dir="auto">{a.trigger}</dd></div>
                <div><dt className="inline font-semibold text-muted-foreground">{it("ap_why")}: </dt><dd className="inline">{a.why}</dd></div>
                <div><dt className="inline font-semibold text-muted-foreground">{it("ap_expected")}: </dt><dd className="inline">{a.expected}</dd></div>
                {a.impact && <div><dt className="inline font-semibold text-muted-foreground">{it("ap_impact")}: </dt><dd className="inline">{a.impact}</dd></div>}
                {a.if_unavailable && <div><dt className="inline font-semibold text-muted-foreground">{it("ap_if_unavailable")}: </dt><dd className="inline">{a.if_unavailable}</dd></div>}
                <div><dt className="inline font-semibold text-primary">{it("ap_next")}: </dt><dd className="inline">{a.next}</dd></div>
              </dl>
              <div className="mt-2 flex flex-wrap gap-2">
                {a.kind === "document" && <button className="btn btn-outline !py-1 text-xs" onClick={() => scrollTo("next-step")}><ArrowDownRight className="size-3.5" /> {it("uploadFiles")}</button>}
                {a.kind === "request_quotes" && (a.draft_ids?.length
                  ? <button className="btn btn-outline !py-1 text-xs" onClick={() => { onOpenOutreach(a.draft_ids[0]); scrollTo("outreach"); }}>{it("btn_open_draft")}</button>
                  : <button className="btn btn-primary !py-1 text-xs" onClick={() => prepare({ purpose: "quote_request", driver: a.driver })}><Mail className="size-3.5" /> {it("btn_prepare_request")}</button>)}
                {a.kind === "await_reply" && <button className="btn btn-outline !py-1 text-xs" onClick={() => scrollTo("quotes")}>{it("btn_add_reply")}</button>}
                {a.kind === "compare" && <button className="btn btn-outline !py-1 text-xs" onClick={() => scrollTo("quotes")}>{it("btn_go_compare")}</button>}
                {a.kind === "moq" && <button className="btn btn-primary !py-1 text-xs" onClick={() => prepare({ purpose: "moq_question", quote_id: a.quote_id })}>{it("btn_ask_moq")}</button>}
                {a.kind === "track" && <button className="btn btn-primary !py-1 text-xs" onClick={() => oapi.trackScenario(id, a.scenario_id).then(refresh).catch(onErr)}>{it("btn_track")}</button>}
                {a.kind === "verify" && <button className="btn btn-outline !py-1 text-xs" onClick={() => scrollTo("tracking")}>{it("btn_go_tracking")}</button>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

export function EvidenceList({ items }: { items: any[] }) {
  const it = useIT();
  const { lang } = useApp();
  if (!items?.length) return null;
  const tone: Record<string, any> = { processed: "ok", missing: "warn", awaiting_confirmation: "warn", unavailable: "muted", skipped: "muted" };
  return (
    <div className="mb-4">
      <div className="mb-1 text-sm font-semibold">{it("ev_title")}</div>
      <ul className="grid gap-1 text-sm">
        {items.map((e) => (
          <li key={e.key} className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/40 px-2 py-1">
            {e.status === "processed" ? <CheckCircle2 className="size-4 text-success" /> : <span className="size-4" />}
            <span className="flex-1">{e.label[lang]}{e.optional && <span className="text-xs text-muted-foreground"> · {it("optional")}</span>}
              <span className="block text-xs text-muted-foreground">{e.question[lang]}</span>
              {e.confirmation_needed && <span className="block text-xs text-warning" dir="auto">{e.confirmation_needed}</span>}</span>
            <Pill tone={tone[e.status]}>{it(`evs_${e.status}`)}</Pill>
          </li>
        ))}
      </ul>
    </div>
  );
}

const TERMS = ["unit_price", "price_tiers", "moq", "setup_fee", "delivery_fee", "lead_time", "payment_terms", "samples"];

export function Outreach({ s, id, openId }: { s: any; id: string; openId: number | null }) {
  const it = useIT();
  if (!s.outreach?.length) return null;
  return (
    <div id="outreach">
      <Card title={it("or_title")}>
        <p className="-mt-2 mb-3 text-sm text-muted-foreground">{it("or_sub")}</p>
        <div className="grid gap-3">{s.outreach.map((o: any) => <OutreachItem key={`${o.id}-${o.updated_at}`} o={o} id={id} open={openId === o.id || o.status === "draft"} />)}</div>
      </Card>
    </div>
  );
}

function OutreachItem({ o, id, open: open0 }: { o: any; id: string; open: boolean }) {
  const it = useIT();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const status = useStatus();
  const [open, setOpen] = useState(open0);
  const [b, setB] = useState<any>({ ...o.brief, quantity: o.brief.quantity ?? "" });
  const [sup, setSup] = useState({ name: o.supplier_name ?? "", email: o.supplier_email ?? "" });
  const [subject, setSubject] = useState(o.subject);
  const [body, setBody] = useState(o.body);
  const [lng, setLng] = useState<string>(o.language);
  const editable = o.status === "draft" || o.status === "approved";
  const refresh = () => qc.invalidateQueries({ queryKey: ["inv", id] });
  const run = (p: Promise<unknown>, ok?: string) => p.then(() => { if (ok) toast.success(ok); refresh(); }).catch(onErr);
  const emailOn = !!status.data?.email_configured;
  const inp = "rounded-lg border bg-card px-2 py-1.5 text-sm";
  const tone = o.status === "sent" ? "ok" : ["send_failed", "send_unknown"].includes(o.status) ? "danger" : o.status === "copied_manual" ? "warn" : "primary";
  return (
    <article className="rounded-xl border p-3 text-sm">
      <button className="flex w-full flex-wrap items-center gap-2 text-start" onClick={() => setOpen(!open)}>
        <Pill tone={tone as any}>{it(`ors_${o.status}`)}</Pill><b dir="auto">{o.subject}</b>
        <span className="text-xs text-muted-foreground" dir="ltr">{o.trigger.kind === "finding" ? `${o.trigger.driver} · ${o.trigger.periods?.join(" → ")}` : `MOQ ${o.trigger.moq} vs ${o.trigger.needed}`}</span>
      </button>
      {open && (
        <div className="mt-3 grid gap-2">
          {editable && (
            <div className="grid gap-2 sm:grid-cols-2">
              <input value={b.sourcing} onChange={(e) => setB({ ...b, sourcing: e.target.value })} placeholder={it("or_sourcing")} className={inp} />
              <input value={b.specification} onChange={(e) => setB({ ...b, specification: e.target.value })} placeholder={it("or_spec")} className={inp} />
              <input value={b.quality_requirements} onChange={(e) => setB({ ...b, quality_requirements: e.target.value })} placeholder={it("or_quality")} className={inp} />
              <div className="flex items-center gap-2">
                <input inputMode="decimal" value={b.quantity} onChange={(e) => setB({ ...b, quantity: e.target.value })} placeholder={it("or_quantity")} className={`${inp} flex-1`} dir="ltr" />
                {o.brief.suggested_quantity && b.quantity === "" && <button className="text-xs text-primary underline" onClick={() => setB({ ...b, quantity: o.brief.suggested_quantity.value })}>{it("or_use_suggested", { n: o.brief.suggested_quantity.value, b: o.brief.suggested_quantity.basis })}</button>}
              </div>
              <input value={b.business_name} onChange={(e) => setB({ ...b, business_name: e.target.value })} placeholder={it("or_business")} className={inp} />
              <input value={b.contact_name} onChange={(e) => setB({ ...b, contact_name: e.target.value })} placeholder={it("or_contact")} className={inp} />
              <input value={sup.name} onChange={(e) => setSup({ ...sup, name: e.target.value })} placeholder={it("or_supplier")} className={inp} />
              <input value={sup.email} onChange={(e) => setSup({ ...sup, email: e.target.value })} placeholder={it("or_email")} className={inp} dir="ltr" />
              <div className="sm:col-span-2 flex flex-wrap items-center gap-2 text-xs"><span className="font-semibold">{it("or_terms")}:</span>
                {TERMS.map((t) => <label key={t} className="flex items-center gap-1"><input type="checkbox" checked={b.terms.includes(t)} onChange={(e) => setB({ ...b, terms: e.target.checked ? [...b.terms, t] : b.terms.filter((x: string) => x !== t) })} />{it(`term_${t}`)}</label>)}
              </div>
              <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
                <select value={lng} onChange={(e) => setLng(e.target.value)} className={inp} aria-label="language"><option value="ar">العربية</option><option value="en">English</option></select>
                <button className="btn btn-outline w-fit !py-1.5 text-xs" onClick={() => run(oapi.edit(id, o.id, { brief: { ...b, quantity: b.quantity === "" ? null : b.quantity }, supplier_name: sup.name, supplier_email: sup.email, regenerate: true, language: lng }))}>{it("or_update")}</button>
              </div>
            </div>
          )}
          <input value={subject} disabled={!editable} onChange={(e) => setSubject(e.target.value)} className={inp} dir={o.language === "ar" ? "rtl" : "ltr"} />
          <textarea value={body} disabled={!editable} onChange={(e) => setBody(e.target.value)} rows={12} className={cn(inp, "leading-relaxed")} dir={o.language === "ar" ? "rtl" : "ltr"} />
          {!!o.placeholders.length && <p className="rounded-lg bg-warning/10 p-2 text-xs text-warning">{it("or_placeholders")} <span dir="auto">{o.placeholders.join(" · ")}</span></p>}
          {editable && (subject !== o.subject || body !== o.body) && <button className="btn btn-outline w-fit !py-1.5 text-xs" onClick={() => run(oapi.edit(id, o.id, { subject, body, supplier_name: sup.name, supplier_email: sup.email }), it("saved"))}>{it("saveEdits")}</button>}
          {o.status === "approved" && !emailOn && <p className="rounded-lg bg-muted p-2 text-xs">{it("emailOffNote")}</p>}
          <div className="flex flex-wrap gap-2">
            {o.status === "draft" && <button className="btn btn-primary !py-1.5 text-sm" disabled={!!o.placeholders.length} onClick={() => run(oapi.act(id, o.id, "approve"), it("approved"))}>{it("or_approve")}</button>}
            {o.status === "approved" && emailOn && <button className="btn btn-primary !py-1.5 text-sm" onClick={() => run(oapi.act(id, o.id, "send", { approval: o.approval_hash }), it("ors_sent"))}>{it("or_send")}</button>}
            {o.status === "approved" && <button className="btn btn-outline !py-1.5 text-sm" onClick={() => navigator.clipboard.writeText(`${o.subject}\n\n${o.body}`).then(() => toast.success(it("copied")))}>{it("or_copy")}</button>}
            {o.status === "approved" && <button className="btn btn-outline !py-1.5 text-sm" onClick={() => run(oapi.act(id, o.id, "copied"))}>{it("or_i_sent")}</button>}
            {editable && <button className="btn btn-outline !py-1.5 text-sm text-danger" onClick={() => run(oapi.act(id, o.id, "cancel"))}>{it("or_cancel")}</button>}
            {editable && <span className="self-center text-xs font-semibold uppercase text-muted-foreground">{it("or_not_sent")}</span>}
          </div>
          {o.provider_result?.error && <p className="text-xs text-danger" dir="ltr">{o.provider_result.error}</p>}
        </div>
      )}
    </article>
  );
}
