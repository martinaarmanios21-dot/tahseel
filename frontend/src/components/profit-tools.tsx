/* Order-level profit and the what-if simulator. All numbers come from the backend (orders.py / simulator.py). */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, Pill, Spinner, useErrorToast } from "./bits";
import { major, useIT } from "./charts";
import { useApp } from "@/lib/app-context";
import { oapi, papi2, qapi } from "@/lib/tapi";
import { cn } from "@/lib/utils";

/* eslint-disable @typescript-eslint/no-explicit-any */
const vizCss = `.viz2{--s1:#2a78d6;--s2:#eb6834;--grid:#e7e5df;--ink2:#52514e}.dark .viz2{--s1:#3987e5;--s2:#d95926;--grid:#33332f;--ink2:#c3c2b7}`;
const fmt = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });

export function OrderProfit({ ov, id }: { ov: any; id: string }) {
  const it = useIT();
  const { money, lang } = useApp();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const [tab, setTab] = useState<"products" | "channels" | "loss">("products");
  const [showTable, setShowTable] = useState(false);
  const cur = ov.currency;
  const m = (v: number | null | undefined) => (v == null ? "—" : money(Math.round(v), cur));
  const setAlloc = (cat: string, method: string) =>
    papi2.setAllocation(id, { ...ov.allocation, [cat]: method }).then(() => qc.invalidateQueries({ queryKey: ["inv", id] })).catch(onErr);
  const chartData = ov.products.filter((p: any) => p.contribution != null).slice(0, 10)
    .map((p: any) => ({ k: p.product, sales: major(p.net_sales, cur), kept: major(p.contribution, cur) }));
  const r = ov.reconciliation;
  return (
    <Card title={it("op_title")}>
      <p className="-mt-2 mb-3 text-sm text-muted-foreground">{it("op_sub")}</p>
      {ov.insights.filter((x: any) => x.kind !== "allocation_note").map((x: any) => (
        <p key={x.kind} className="mb-2 rounded-lg bg-primary-soft p-3 text-sm font-medium">{x.text}</p>
      ))}
      <div className="mb-3 flex flex-wrap gap-2 text-xs">
        {!!ov.incomplete_orders && <Pill tone="warn">{it("op_incomplete", { n: ov.incomplete_orders })}</Pill>}
        {!!ov.unmatched_costs.length && <Pill tone="warn">{it("op_unmatched", { n: ov.unmatched_costs.length })}</Pill>}
      </div>
      {chartData.length > 1 && (
        <figure className="viz2 mb-4" aria-label={it("ch_products_contrib")}>
          <style>{vizCss}</style>
          <figcaption className="text-sm font-bold">{it("ch_products_contrib")}</figcaption>
          <div className="text-xs text-muted-foreground">{cur} · {it("ch_products_contrib_note")}</div>
          <div dir="ltr" className="h-64">
            <ResponsiveContainer>
              <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 30, left: 10, bottom: 0 }} barGap={2}>
                <CartesianGrid stroke="var(--grid)" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11, fill: "var(--ink2)" }} tickFormatter={fmt} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="k" width={110} tick={{ fontSize: 11, fill: "var(--ink2)" }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(x: number) => fmt(x)} />
                <Legend />
                <Bar dataKey="sales" name={it("op_net")} fill="var(--s1)" radius={[0, 4, 4, 0]} barSize={10} />
                <Bar dataKey="kept" name={it("op_contrib")} fill="var(--s2)" radius={[0, 4, 4, 0]} barSize={10} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <button className="text-xs text-primary underline" onClick={() => setShowTable(!showTable)}>{showTable ? it("hideNumbers") : it("showNumbers")}</button>
        </figure>
      )}
      <div className="mb-2 flex gap-1 text-sm" role="tablist">
        {(["products", "channels", "loss"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={cn("rounded-full px-3 py-1", tab === t ? "bg-primary text-primary-foreground" : "bg-muted")}>
            {it(t === "products" ? "op_products" : t === "channels" ? "op_channels" : "op_loss")}{t === "loss" ? ` (${ov.loss_order_count})` : ""}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        {(tab === "products" || showTable) && tab !== "loss" && tab !== "channels" && (
          <table className="w-full text-sm">
            <thead><tr className="text-muted-foreground">{["op_products", "op_units", "op_net", "op_contrib", "op_per_unit", "op_margin"].map((k) => <th key={k} className="border-b px-2 py-1.5 text-start font-medium">{it(k)}</th>)}</tr></thead>
            <tbody>{ov.products.map((p: any) => (
              <tr key={p.product}><td className="border-b px-2 py-1.5" dir="auto">{p.product}</td><td className="border-b px-2 py-1.5 tabular-nums">{p.units}</td>
                <td className="border-b px-2 py-1.5 tabular-nums" dir="ltr">{m(p.net_sales)}</td>
                <td className="border-b px-2 py-1.5 tabular-nums" dir="ltr">{p.contribution == null ? <Pill tone="warn">{it("op_missing_cost")}</Pill> : m(p.contribution)}</td>
                <td className="border-b px-2 py-1.5 tabular-nums" dir="ltr">{m(p.contribution_per_unit)}</td>
                <td className="border-b px-2 py-1.5 tabular-nums">{p.contribution_margin == null ? "—" : `${(p.contribution_margin * 100).toFixed(1)}%`}</td></tr>))}</tbody>
          </table>
        )}
        {tab === "channels" && (
          <table className="w-full text-sm">
            <thead><tr className="text-muted-foreground">{["op_channels", "op_orders", "op_net", "op_contrib", "op_per_order", "op_loss"].map((k) => <th key={k} className="border-b px-2 py-1.5 text-start font-medium">{it(k)}</th>)}</tr></thead>
            <tbody>{ov.channels.map((c: any) => (
              <tr key={c.key}><td className="border-b px-2 py-1.5">{c.key}</td><td className="border-b px-2 py-1.5">{c.orders}</td>
                <td className="border-b px-2 py-1.5" dir="ltr">{m(c.net_sales)}</td><td className="border-b px-2 py-1.5" dir="ltr">{m(c.contribution)}</td>
                <td className="border-b px-2 py-1.5" dir="ltr">{m(c.contribution_per_order)}</td><td className="border-b px-2 py-1.5">{c.loss_orders}</td></tr>))}</tbody>
          </table>
        )}
        {tab === "loss" && <LossOrders id={id} />}
      </div>
      <details className="mt-4 text-sm">
        <summary className="cursor-pointer font-semibold">{it("op_allocation")}</summary>
        <p className="mt-1 text-xs text-muted-foreground">{ov.insights.find((x: any) => x.kind === "allocation_note")?.text ?? it("op_allocation_note")}</p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {Object.entries(ov.allowed_allocation as Record<string, string[]>).map(([cat, methods]) => (
            <label key={cat} className="flex items-center justify-between gap-2 rounded-lg bg-muted/50 px-3 py-2">
              <span>{it(`c_${cat}`)}</span>
              <select value={ov.allocation[cat]} onChange={(e) => setAlloc(cat, e.target.value)} className="rounded border bg-card px-2 py-1 text-xs">
                {methods.map((mm) => <option key={mm} value={mm}>{it(`op_method_${mm}`)}</option>)}
              </select>
            </label>
          ))}
        </div>
        {ov.allocations.map((a: any) => (
          <p key={`${a.period}-${a.category}`} className="mt-1 text-xs text-muted-foreground" dir="auto">
            {a.period} · {it(`c_${a.category}`)}: {m(a.amount)} → {a.orders} {it("op_orders")} · {ov.method_text[a.method][lang]}
          </p>
        ))}
        <div className="mt-3 rounded-lg border p-2 text-xs">
          <div className="font-semibold">{it("op_recon")}</div>
          <div dir="ltr" className="mt-1 grid gap-0.5 tabular-nums">
            <div>{it("op_recon_orders")}: {m(r.orders_contribution_known_costs)}</div>
            <div>− {it("op_recon_unalloc")}: {m(r.unallocated_costs)}</div>
            <div>− {it("op_recon_unmatched")}: {m(r.costs_linked_to_unknown_orders)}</div>
            <div>− {it("op_recon_refunds")}: {m(r.refunds_linked_to_unknown_orders)}</div>
            <div className="font-semibold">{it("op_recon_monthly")}: {m(r.implied_monthly_contribution_total)} {r.implied_monthly_contribution_total === ov.monthly_contribution_total ? "✓" : `≠ ${m(ov.monthly_contribution_total)}`}</div>
          </div>
        </div>
      </details>
    </Card>
  );
}

function LossOrders({ id }: { id: string }) {
  const it = useIT();
  const { money } = useApp();
  const q = useQuery({ queryKey: ["orders", id, "loss"], queryFn: () => papi2.orders(id, "loss") });
  if (!q.data) return <Spinner show label="…" />;
  if (!q.data.orders.length) return <p className="py-2 text-sm text-muted-foreground">—</p>;
  return (
    <ul className="grid gap-2 text-sm">
      {q.data.orders.map((o: any) => (
        <li key={o.order_id} className="rounded-lg border p-2">
          <div className="flex flex-wrap items-center gap-2"><b dir="ltr">{o.order_id}</b><span className="text-xs text-muted-foreground" dir="ltr">{o.date}</span>
            <span className="text-danger" dir="ltr">{money(o.contribution, q.data.currency)}</span><span className="text-xs">{o.products.join(", ")}</span></div>
          <div className="mt-1 flex flex-wrap gap-1 text-xs">
            {Object.entries(o.costs).map(([k, v]: [string, any]) => (
              <Pill key={k} tone={v.basis === "actual" ? "primary" : "muted"}>{it(`c_${k}`)} {money(v.amount, q.data.currency)} · {v.basis === "actual" ? it("op_actual") : it("op_allocated")}</Pill>
            ))}
            <Pill>{it("c_cogs")} {money(o.cogs, q.data.currency)}</Pill>
          </div>
        </li>
      ))}
    </ul>
  );
}

/* --------------------------------------------------------------------------- what-if simulator */
export function Simulator({ ov, id, scenarios }: { ov: any; id: string; scenarios: any[] }) {
  const it = useIT();
  const { lang, money } = useApp();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const caps: any = ov.simulator.capabilities;
  const [period, setPeriod] = useState<string>(ov.simulator.period);
  const [f, setF] = useState<any>({ priceProduct: "all" });
  const [res, setRes] = useState<any>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const cur = ov.currency;
  const scenario = () => {
    const s: any = {};
    if (f.price) s.price_change_pct = { [f.priceProduct || "all"]: Number(f.price) };
    if (f.packaging) s.packaging_per_order = f.packaging;
    if (f.shipping) s.shipping_per_order = f.shipping;
    if (f.discount) s.discount_pct = Number(f.discount);
    if (f.returns) s.return_rate_pct = Number(f.returns);
    if (f.unitCost && f.unitProduct) s.product_unit_cost = { [f.unitProduct]: f.unitCost };
    if (f.threshold) s.free_shipping = { threshold: f.threshold, fee: f.fee || "0" };
    if (f.volume) s.volume_change_pct = Number(f.volume);
    return s;
  };
  const run = async () => {
    setBusy(true);
    try { setRes(await papi2.simulate(id, scenario(), period, lang)); } catch (e) { onErr(e); setRes(null); } finally { setBusy(false); }
  };
  const save = async (track: boolean) => {
    try {
      await papi2.saveScenario(id, scenario(), period, name || it("sim_title"), track, lang);
      toast.success(track ? it("st_planned") : it("sim_saved"));
      qc.invalidateQueries({ queryKey: ["inv", id] });
    } catch (e) { onErr(e); }
  };
  const input = "w-28 rounded-lg border bg-card px-2 py-1.5 text-sm";
  const Field = ({ k, label, cap, children }: { k: string; label: string; cap: string; children?: React.ReactNode }) => (
    <label className={cn("flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2", caps[cap]?.ok ? "bg-muted/50" : "bg-muted/20 opacity-70")}>
      <span className="text-sm">{label}{!caps[cap]?.ok && <span className="block text-xs text-warning">{it("sim_not_supported")} {caps[cap]?.reason}</span>}</span>
      <span className="flex items-center gap-1">{children}{k && <input disabled={!caps[cap]?.ok} inputMode="decimal" value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} className={input} dir="ltr" />}</span>
    </label>
  );
  const rows = ["orders", "net_sales", "shipping_income", "contribution", "contribution_margin", "contribution_per_order", "loss_orders", "after_fixed", "break_even_orders"];
  const show = (k: string, v: any) => v == null ? "—" : k === "contribution_margin" ? `${(v * 100).toFixed(1)}%` : ["orders", "loss_orders", "break_even_orders"].includes(k) ? String(v) : money(Math.round(v), cur);
  return (
    <Card title={it("sim_title")}>
      <p className="-mt-2 mb-3 text-sm text-muted-foreground">{it("sim_sub")}</p>
      <label className="mb-2 flex items-center gap-2 text-sm">{it("sim_month")}
        <select value={period} onChange={(e) => setPeriod(e.target.value)} className="rounded border bg-card px-2 py-1">{ov.simulator.periods.map((p: string) => <option key={p}>{p}</option>)}</select></label>
      <div className="grid gap-2 md:grid-cols-2">
        <Field k="price" label={it("sim_price")} cap="price_change_pct">
          <select value={f.priceProduct} onChange={(e) => setF({ ...f, priceProduct: e.target.value })} className="rounded border bg-card px-1 py-1 text-xs">
            <option value="all">{it("sim_all_products")}</option>{ov.products.map((p: any) => <option key={p.product} value={p.product}>{p.product}</option>)}
          </select>
        </Field>
        <Field k="packaging" label={`${it("sim_packaging")} (${cur})`} cap="packaging_per_order" />
        <Field k="shipping" label={`${it("sim_shipping")} (${cur})`} cap="shipping_per_order" />
        <Field k="discount" label={it("sim_discount")} cap="discount_pct" />
        <Field k="returns" label={it("sim_returns")} cap="return_rate_pct" />
        <Field k="unitCost" label={`${it("sim_unit_cost")} (${cur})`} cap="product_unit_cost">
          <select value={f.unitProduct ?? ""} onChange={(e) => setF({ ...f, unitProduct: e.target.value })} className="rounded border bg-card px-1 py-1 text-xs" disabled={!caps.product_unit_cost?.ok}>
            <option value="">—</option>{(caps.product_unit_cost?.products ?? []).map((p: string) => <option key={p}>{p}</option>)}
          </select>
        </Field>
        <Field k="threshold" label={`${it("sim_free_ship")} (${cur})`} cap="free_shipping">
          <span className="text-xs">{it("sim_fee_below")}</span>
          <input disabled={!caps.free_shipping?.ok} value={f.fee ?? ""} onChange={(e) => setF({ ...f, fee: e.target.value })} className="w-16 rounded-lg border bg-card px-2 py-1.5 text-sm" dir="ltr" />
        </Field>
        <Field k="volume" label={it("sim_volume")} cap="volume_change_pct" />
      </div>
      <button className="btn btn-primary mt-3 !py-2" disabled={busy || !Object.keys(scenario()).length} onClick={run}>{it("sim_run")}</button>
      <Spinner show={busy} />
      {res && (
        <div className="mt-4 grid gap-3">
          <p className="rounded-lg bg-primary-soft p-3 text-sm font-medium">{res.summary}</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-muted-foreground"><th className="border-b px-2 py-1 text-start" /><th className="border-b px-2 py-1 text-start">{it("sim_baseline")} <span dir="ltr">{res.period}</span></th><th className="border-b px-2 py-1 text-start">{it("sim_projected")}</th><th className="border-b px-2 py-1 text-start">{it("sim_change")}</th></tr></thead>
              <tbody>{rows.map((k) => (
                <tr key={k}><td className="border-b px-2 py-1">{it(`m_${k}`)}</td><td className="border-b px-2 py-1 tabular-nums" dir="ltr">{show(k, res.baseline[k])}</td>
                  <td className="border-b px-2 py-1 tabular-nums" dir="ltr">{show(k, res.projected[k])}</td>
                  <td className={cn("border-b px-2 py-1 tabular-nums", (res.delta[k] ?? 0) < 0 ? "text-danger" : "text-success")} dir="ltr">{k === "contribution_margin" || res.delta[k] == null ? "" : (res.delta[k] > 0 ? "+" : "") + show(k, res.delta[k])}</td></tr>))}</tbody>
            </table>
          </div>
          <div className="text-sm"><b>{it("sim_assumptions")}:</b><ul className="mt-1 list-disc ps-5 text-muted-foreground" dir="ltr" style={{ textAlign: "start" }}>{res.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul></div>
          {!!res.excluded_incomplete_orders && <p className="text-xs text-warning">{it("op_incomplete", { n: res.excluded_incomplete_orders })}</p>}
          <div className="flex flex-wrap items-center gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder={it("sim_name")} maxLength={120} className="rounded-lg border bg-card px-2 py-1.5 text-sm" />
            <button className="btn btn-outline !py-1.5 text-sm" onClick={() => save(false)}>{it("sim_save")}</button>
            <button className="btn btn-primary !py-1.5 text-sm" onClick={() => save(true)}>{it("sim_track")}</button>
          </div>
        </div>
      )}
      {!!scenarios.length && (
        <div className="mt-4">
          <div className="text-sm font-semibold">{it("sim_saved")}</div>
          <ul className="mt-1 grid gap-1 text-sm">{scenarios.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/50 px-2 py-1">
              <b>{s.name}</b><span dir="ltr">{s.period}</span>
              <span dir="ltr" className={(s.delta_contribution ?? 0) < 0 ? "text-danger" : "text-success"}>{s.delta_contribution > 0 ? "+" : ""}{money(s.delta_contribution, s.currency)}</span>
              <Pill>{it("projection")}</Pill>{s.intervention_id && <Pill tone="primary">{it("st_planned")}</Pill>}
            </li>))}</ul>
        </div>
      )}
    </Card>
  );
}

/* --------------------------------------------------------------------------- supplier quotes */

export function Quotes({ id, currency, outreach = [], products = [] }: { id: string; currency: string; outreach?: any[]; products?: string[] }) {
  const it = useIT();
  const { money, lang } = useApp();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const q = useQuery({ queryKey: ["quotes", id], queryFn: () => qapi.list(id) });
  const empty = { item_key: "", category: "packaging", supplier: "", spec: "", unit_price: "", moq: "", setup_fee: "", delivery_fee: "", payment_terms: "", lead_time_days: "", quality_notes: "", source: "written_quote", owner_confirmed_quote: false, spec_confirmed: false, outreach_id: "", linked_product: "", document_name: "" };
  const [extracted, setExtracted] = useState<Record<string, { value: string; snippet: string }>>({});
  const [f, setF] = useState<any>(empty);
  const [cmp, setCmp] = useState<any>(null);
  const [qty, setQty] = useState("");
  const [sim, setSim] = useState<Record<number, string>>({});
  const groups = [...new Set((q.data ?? []).map((x: any) => x.item_key))];
  const add = () => {
    // a value read from the document counts as confirmed only if the owner left it as read (after checking it)
    const field_sources = Object.fromEntries(Object.keys(empty).filter((k) => f[k] !== "" && typeof f[k] === "string")
      .map((k) => [k, extracted[k] && extracted[k].value === f[k] ? "extracted_confirmed" : "typed"]));
    return qapi.add(id, { ...f, currency, lead_time_days: f.lead_time_days || null, outreach_id: f.outreach_id || null, linked_product: f.linked_product || null, field_sources })
      .then(() => { setF({ ...empty, item_key: f.item_key, category: f.category }); setExtracted({}); qc.invalidateQueries({ queryKey: ["quotes", id] }); qc.invalidateQueries({ queryKey: ["inv", id] }); }).catch(onErr);
  };
  const readDoc = (file?: File) => file && oapi.extractQuote(id, file).then((r) => {
    if (r.error && !Object.keys(r.fields).length) { toast.error(r.error); return; }
    const vals = Object.fromEntries(Object.entries(r.fields).map(([k, v]: [string, any]) => [k, v.value]));
    setExtracted(r.fields); setF({ ...f, ...vals, document_name: r.document_name });
  }).catch(onErr);
  const ex = (k: string) => extracted[k] && extracted[k].value === f[k] ? <span className="text-[10px] text-warning" title={extracted[k].snippet}>{it("qt_extracted")}</span> : null;
  const compare = (g: string) => qapi.compare(id, g, qty || undefined).then(setCmp).catch(onErr);
  const trySim = (r: any) => papi2.simulate(id, cmp.category === "product" && r.linked_product
      ? { product_unit_cost: { [r.linked_product]: String(r.per_needed_unit / 100) } }
      : { [cmp.category === "shipping" ? "shipping_per_order" : "packaging_per_order"]: String(r.per_needed_unit / 100) }, undefined, lang)
    .then((res) => setSim({ ...sim, [r.quote_id]: res.summary })).catch(onErr);
  const inp = "rounded-lg border bg-card px-2 py-1.5 text-sm";
  const m = (v: number | null | undefined) => (v == null ? it("qt_unknown") : money(Math.round(v), cmp?.currency ?? currency));
  return (
    <Card title={it("qt_title")}>
      <p className="-mt-2 mb-3 text-sm text-muted-foreground">{it("qt_sub")}</p>
      <label className="mb-2 inline-flex cursor-pointer items-center gap-2 text-sm text-primary underline">{it("qt_read_doc")}
        <input type="file" accept=".pdf,.csv,.txt,.xlsx" className="sr-only" onChange={(e) => readDoc(e.target.files?.[0])} />
      </label>
      {!!Object.keys(extracted).length && <p className="mb-2 rounded-lg bg-warning/10 p-2 text-xs text-warning">{it("qt_extracted")} · {f.document_name}</p>}
      <form className="grid gap-2 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); add(); }}>
        <input required value={f.item_key} onChange={(e) => setF({ ...f, item_key: e.target.value })} placeholder={it("qt_group")} list="qt-groups" className={inp} />
        <datalist id="qt-groups">{groups.map((g) => <option key={g} value={g} />)}</datalist>
        <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} className={inp} aria-label={it("qt_category")}>
          {["packaging", "shipping", "cogs_materials", "product"].map((c) => <option key={c} value={c}>{it(`c_${c === "cogs_materials" ? "cogs" : c === "product" ? "product_costs" : c}`)}</option>)}
        </select>
        <input required value={f.supplier} onChange={(e) => setF({ ...f, supplier: e.target.value })} placeholder={it("qt_supplier")} className={inp} />
        <input required value={f.spec} onChange={(e) => setF({ ...f, spec: e.target.value })} placeholder={it("qt_spec")} className={inp} />
        {([["unit_price", `${it("qt_unit")} (${currency})`, true], ["moq", it("qt_moq")], ["setup_fee", it("qt_setup")], ["delivery_fee", it("qt_delivery")], ["payment_terms", it("qt_terms")], ["lead_time_days", it("qt_lead")]] as [string, string, boolean?][]).map(([k, ph, req]) => (
          <span key={k} className="grid"><input required={!!req} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} placeholder={ph} className={inp} dir={k === "payment_terms" ? "auto" : "ltr"} />{ex(k)}</span>
        ))}
        {!!outreach.length && (
          <select value={f.outreach_id} onChange={(e) => setF({ ...f, outreach_id: e.target.value })} className={inp} aria-label={it("qt_answers_request")}>
            <option value="">{it("qt_answers_request")}: —</option>
            {outreach.filter((o) => o.status !== "cancelled").map((o) => <option key={o.id} value={o.id}>#{o.id} {o.subject}</option>)}
          </select>
        )}
        {f.category === "product" && (
          <select value={f.linked_product} onChange={(e) => setF({ ...f, linked_product: e.target.value })} className={inp} aria-label={it("qt_linked_product")}>
            <option value="">{it("qt_linked_product")}: —</option>{products.map((p) => <option key={p}>{p}</option>)}
          </select>
        )}
        <input value={f.quality_notes} onChange={(e) => setF({ ...f, quality_notes: e.target.value })} placeholder={it("qt_quality")} className={`${inp} sm:col-span-2`} />
        <select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} className={inp} aria-label={it("qt_source")}>
          {["written_quote", "verbal", "web_listing"].map((s) => <option key={s} value={s}>{it(`qt_src_${s}`)}</option>)}
        </select>
        <div className="grid gap-1 text-xs">
          <label className="flex items-center gap-1.5"><input type="checkbox" disabled={f.source === "web_listing"} checked={f.owner_confirmed_quote && f.source !== "web_listing"} onChange={(e) => setF({ ...f, owner_confirmed_quote: e.target.checked })} /> {it("qt_confirm_real")}</label>
          <label className="flex items-center gap-1.5"><input type="checkbox" checked={f.spec_confirmed} onChange={(e) => setF({ ...f, spec_confirmed: e.target.checked })} /> {it("qt_confirm_spec")}</label>
        </div>
        <button className="btn btn-outline w-fit !py-1.5 text-sm">{it("qt_add")}</button>
      </form>
      {!!q.data?.length && (
        <div className="mt-4">
          <div className="text-sm font-semibold">{it("qt_list")}</div>
          <ul className="mt-1 grid gap-1 text-xs">{q.data.map((x: any) => (
            <li key={x.id} className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/50 px-2 py-1">
              <b>{x.item_key}</b> · {x.supplier} · <span dir="ltr">{money(x.unit_price_minor, x.currency)}</span> · {it(`qt_src_${x.source}`)}
              {!x.owner_confirmed_quote && x.source !== "web_listing" && <button className="underline" onClick={() => qapi.confirm(id, x.id, { owner_confirmed_quote: true }).then(() => qc.invalidateQueries({ queryKey: ["quotes", id] }))}>{it("qt_confirm_real")}</button>}
              {!x.spec_confirmed && <button className="underline" onClick={() => qapi.confirm(id, x.id, { spec_confirmed: true }).then(() => qc.invalidateQueries({ queryKey: ["quotes", id] }))}>{it("qt_confirm_spec")}</button>}
            </li>))}</ul>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <input inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} placeholder={it("qt_qty")} className={`${inp} w-36`} dir="ltr" />
            {groups.map((g) => <button key={g} className="btn btn-primary !py-1.5 text-sm" onClick={() => compare(g)}>{it("qt_compare")}: {g}</button>)}
          </div>
        </div>
      )}
      {cmp && (
        <div className="mt-4 grid gap-2 text-sm">
          <p className="text-xs text-muted-foreground" dir="ltr" style={{ textAlign: "start" }}>{cmp.quantity} · {cmp.quantity_source}</p>
          <div className="overflow-x-auto"><table className="w-full">
            <thead><tr className="text-muted-foreground">{["qt_supplier", "qt_buy", "qt_total", "qt_per_needed", "qt_vs_current", "qt_terms", "qt_lead", "qt_quality"].map((k) => <th key={k} className="border-b px-2 py-1 text-start font-medium">{it(k)}</th>)}<th className="border-b" /></tr></thead>
            <tbody>{cmp.comparable.map((r: any) => (
              <tr key={r.quote_id} className="align-top">
                <td className="border-b px-2 py-1"><b>{r.supplier}</b> {r.value_type === "quoted" && <Pill tone="primary">{it("vt_quoted")}</Pill>}<div className="text-xs text-muted-foreground">{r.spec}</div></td>
                <td className="border-b px-2 py-1" dir="ltr">{r.units_to_buy}{r.extra_units_due_to_moq ? <div className="text-xs text-warning">+{r.extra_units_due_to_moq} {it("qt_extra")}</div> : null}</td>
                <td className="border-b px-2 py-1" dir="ltr">{m(r.total_known)}{r.total_is_lower_bound && <div className="text-xs text-warning">{it("qt_lower_bound")}</div>}</td>
                <td className="border-b px-2 py-1 font-semibold" dir="ltr">{m(r.per_needed_unit)}</td>
                <td className={cn("border-b px-2 py-1", (r.vs_current_per_unit ?? 0) > 0 ? "text-danger" : "text-success")} dir="ltr">{r.vs_current_per_unit == null ? "—" : (r.vs_current_per_unit > 0 ? "+" : "") + m(r.vs_current_per_unit)}</td>
                <td className="border-b px-2 py-1">{r.payment_terms ?? it("qt_unknown")}</td>
                <td className="border-b px-2 py-1">{r.lead_time_days ?? it("qt_unknown")}</td>
                <td className="border-b px-2 py-1 text-xs">{r.quality_notes ?? "—"}</td>
                <td className="border-b px-2 py-1">{((cmp.current_cost_per_unit != null && ["packaging", "shipping"].includes(cmp.category)) || (cmp.category === "product" && r.linked_product)) && <button className="text-xs text-primary underline" onClick={() => trySim(r)}>{it("qt_try_sim")}</button>}
                  {sim[r.quote_id] && <div className="mt-1 max-w-xs text-xs">{sim[r.quote_id]}</div>}</td>
              </tr>))}</tbody>
          </table></div>
          <p className="text-xs text-muted-foreground" dir="ltr" style={{ textAlign: "start" }}>{cmp.note}</p>
          {!!cmp.not_comparable.length && (
            <div className="text-xs"><b>{it("qt_not_comparable")}:</b>
              <ul className="list-disc ps-5">{cmp.not_comparable.map((r: any) => <li key={r.quote_id}>{r.supplier}: <span dir="ltr">{r.not_comparable_because.join("; ")}</span></li>)}</ul></div>
          )}
        </div>
      )}
    </Card>
  );
}
