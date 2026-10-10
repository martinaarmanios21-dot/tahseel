/* Investigation charts. Data comes only from the backend's metrics (same numbers as the findings).
 * Palette: validated categorical slots 1–2 (light #2a78d6/#eb6834, dark #3987e5/#d95926) for two-series charts;
 * diverging blue↔red with gray totals for the waterfall; one hue for single-series bars. One axis per chart. */
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApp } from "@/lib/app-context";
import { IT } from "@/i18n/investigation";

/* eslint-disable @typescript-eslint/no-explicit-any */
const css = `.viz{--s1:#2a78d6;--s2:#eb6834;--neg:#d03b3b;--pos:#2a78d6;--tot:#9a9893;--grid:#e7e5df;--ink2:#52514e}
.dark .viz{--s1:#3987e5;--s2:#d95926;--neg:#e66767;--pos:#3987e5;--tot:#6b6a66;--grid:#33332f;--ink2:#c3c2b7}`;
const v = (name: string) => `var(--${name})`;

export function useIT() {
  const { lang } = useApp();
  return (k: string, vars?: Record<string, string | number>) => {
    let s = IT[k]?.[lang] ?? k;
    if (vars) for (const [a, b] of Object.entries(vars)) s = s.replace(`{${a}}`, String(b));
    return s;
  };
}

function exp(cur: string) { return ({ KWD: 3, BHD: 3, OMR: 3, JOD: 3, TND: 3, JPY: 0 } as Record<string, number>)[cur] ?? 2; }
export function major(minor: number, cur: string) { return minor / 10 ** exp(cur); }

function Frame({ title, period, currency, note, estimated, notice, table, children }: {
  title: string; period: string; currency: string; note?: string | undefined; estimated?: boolean | undefined; notice?: string | undefined;
  table: { head: string[]; rows: (string | number)[][] }; children: React.ReactNode;
}) {
  const it = useIT();
  const [show, setShow] = useState(false);
  return (
    <figure className="viz card-soft p-4" aria-label={title}>
      <style>{css}</style>
      <figcaption className="mb-1">
        <div className="font-bold">{title}</div>
        <div className="text-xs text-muted-foreground"><span dir="ltr">{period}</span> · {currency}{note ? ` · ${note}` : ""}</div>
      </figcaption>
      {notice && <p className="mb-2 text-sm font-medium">{notice}</p>}
      <div dir="ltr" className="h-64 w-full">{children}</div>
      {estimated && <p className="mt-1 text-xs text-warning">{it("estimatedNote")}</p>}
      <button className="mt-2 text-xs text-primary underline" onClick={() => setShow(!show)}>{show ? it("hideNumbers") : it("showNumbers")}</button>
      {show && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-xs" dir="ltr">
            <thead><tr>{table.head.map((h) => <th key={h} className="border-b px-2 py-1 text-start">{h}</th>)}</tr></thead>
            <tbody>{table.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="border-b px-2 py-1 tabular-nums">{c}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
    </figure>
  );
}

const fmt = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });
const axis = { tick: { fontSize: 11, fill: "var(--ink2)" }, axisLine: false, tickLine: false } as const;

export function TrendChart({ c }: { c: any }) {
  const it = useIT();
  const data = c.periods.map((p: string, i: number) => ({ period: p, net: major(c.series.net_sales[i], c.currency), keep: major(c.series.contribution[i], c.currency) }));
  return (
    <Frame title={it("ch_trend")} period={`${c.periods[0]} → ${c.periods.at(-1)}`} currency={c.currency} note={it("ch_trend_note")} estimated={c.estimated}
      table={{ head: ["period", it("s_net_sales"), it("s_contribution")], rows: data.map((d: any) => [d.period, fmt(d.net), fmt(d.keep)]) }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 10, right: 110, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="period" {...axis} />
          <YAxis {...axis} tickFormatter={fmt} width={64} />
          <Tooltip formatter={(x: number) => fmt(x)} />
          <Legend />
          <Line type="monotone" dataKey="net" name={it("s_net_sales")} stroke={v("s1")} strokeWidth={2} dot={{ r: 4 }}>
            <LabelList dataKey="net" position="right" content={(p: any) => p.index === data.length - 1 ? <text x={p.x + 6} y={p.y} fontSize={11} fill="var(--ink2)" dominantBaseline="middle">{it("s_net_sales")}</text> : null} />
          </Line>
          <Line type="monotone" dataKey="keep" name={it("s_contribution")} stroke={v("s2")} strokeWidth={2} dot={{ r: 4 }}>
            <LabelList dataKey="keep" position="right" content={(p: any) => p.index === data.length - 1 ? <text x={p.x + 6} y={p.y} fontSize={11} fill="var(--ink2)" dominantBaseline="middle">{it("s_contribution")}</text> : null} />
          </Line>
        </LineChart>
      </ResponsiveContainer>
    </Frame>
  );
}

export function CostPerOrderChart({ c }: { c: any }) {
  const it = useIT();
  const [a, b] = c.periods;
  const data = Object.entries(c.series as Record<string, number[]>)
    .filter(([, vals]) => vals[0] || vals[1])
    .map(([k, vals]) => ({ k: it(`c_${k}`), a: major(vals[0] ?? 0, c.currency), b: major(vals[1] ?? 0, c.currency), raw: k }));
  const biggest = [...data].sort((x, y) => Math.abs(y.b - y.a) - Math.abs(x.b - x.a))[0];
  return (
    <Frame title={it("ch_cost")} period={`${a} → ${b}`} currency={`${c.currency} ${it("perOrder")}`} estimated={c.estimated}
      note={c.missing_months?.length ? `${it("notShownMissing")}: ${c.missing_months.map((m: string) => it(`c_${m}`)).join(", ")}` : undefined}
      notice={biggest && biggest.b !== biggest.a ? it("noticeBiggest", { x: biggest.k }) : undefined}
      table={{ head: ["", a, b], rows: data.map((d) => [d.k, d.a.toFixed(2), d.b.toFixed(2)]) }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, left: 10, bottom: 0 }} barGap={2}>
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" {...axis} tickFormatter={fmt} />
          <YAxis type="category" dataKey="k" {...axis} width={110} />
          <Tooltip formatter={(x: number) => x.toFixed(2)} />
          <Legend />
          <Bar dataKey="a" name={a} fill={v("s1")} radius={[0, 4, 4, 0]} barSize={10} />
          <Bar dataKey="b" name={b} fill={v("s2")} radius={[0, 4, 4, 0]} barSize={10}>
            <LabelList dataKey="b" position="right" fontSize={10} fill="var(--ink2)" formatter={(x: number) => x.toFixed(0)} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Frame>
  );
}

export function BridgeChart({ c }: { c: any }) {
  const it = useIT();
  const cur = c.currency;
  let run = major(c.start, cur);
  const steps = Object.entries(c.steps as Record<string, number>).filter(([, d]) => d !== 0);
  const data: any[] = [{ k: it("start"), base: 0, val: run, kind: "tot" }];
  for (const [k, d0] of steps) {
    const d = major(d0, cur);
    const lo = Math.min(run, run + d);
    data.push({ k: it(`c_${k}`), base: lo, val: Math.abs(d), kind: d < 0 ? "neg" : "pos", signed: d });
    run += d;
  }
  data.push({ k: it("end"), base: 0, val: major(c.end, cur), kind: "tot" });
  return (
    <Frame title={it("ch_bridge")} period={c.periods.join(" → ")} currency={`${cur} ${it("perOrder")}`} estimated={c.estimated}
      table={{ head: ["", "Δ"], rows: data.map((d) => [d.k, d.kind === "tot" ? d.val.toFixed(2) : (d.signed > 0 ? "+" : "") + d.signed.toFixed(2)]) }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 16, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="k" {...axis} interval={0} />
          <YAxis {...axis} tickFormatter={fmt} width={60} />
          <Tooltip formatter={(x: number, n: string, p: any) => (n === "base" ? null : p.payload.kind === "tot" ? x.toFixed(2) : (p.payload.signed > 0 ? "+" : "") + p.payload.signed.toFixed(2))} />
          <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
          <Bar dataKey="val" stackId="w" radius={[4, 4, 0, 0]} barSize={34}>
            {data.map((d, i) => <Cell key={i} fill={v(d.kind)} />)}
            <LabelList dataKey="val" position="top" fontSize={10} fill="var(--ink2)"
              formatter={(x: number) => x.toFixed(0)} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Frame>
  );
}

export function ProductsChart({ c }: { c: any }) {
  const it = useIT();
  const data = c.items.map((p: any) => ({ k: p.product, pct: p.margin_pct == null ? 0 : Math.round(p.margin_pct * 1000) / 10, units: p.units, m: major(p.product_margin, c.currency) }));
  return (
    <Frame title={it("ch_products")} period={c.periods[0]} currency={c.currency} note={it("ch_products_note")}
      table={{ head: ["product", "margin %", "units", "margin"], rows: data.map((d: any) => [d.k, d.pct, d.units, fmt(d.m)]) }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, left: 10, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" {...axis} unit="%" />
          <YAxis type="category" dataKey="k" {...axis} width={110} />
          <Tooltip formatter={(x: number) => `${x}%`} />
          <Bar dataKey="pct" fill={v("s1")} radius={[0, 4, 4, 0]} barSize={12}>
            <LabelList dataKey="pct" position="right" fontSize={10} fill="var(--ink2)" formatter={(x: number) => `${x}%`} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Frame>
  );
}
