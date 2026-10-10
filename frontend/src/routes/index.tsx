import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Search } from "lucide-react";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { LogoFull } from "@/components/Logo";
import { ErrorNote, useErrorToast } from "@/components/bits";
import { useIT } from "@/components/charts";
import { useApp } from "@/lib/app-context";
import { papi, type InvSummary } from "@/lib/tapi";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [{ title: "ربحية · Ribhiya — Profitability & cost-leakage specialist" }] }),
  component: () => <AppShell><Home /></AppShell>,
});

function Home() {
  const it = useIT();
  const { lang } = useApp();
  const nav = useNavigate();
  const onErr = useErrorToast();
  const q = useQuery({ queryKey: ["investigations"], queryFn: papi.list, retry: false });
  const [title, setTitle] = useState("");
  const [cur, setCur] = useState("EGP");
  const [busy, setBusy] = useState(false);
  const [dup, setDup] = useState<InvSummary | null>(null);
  const Arrow = lang === "ar" ? ArrowLeft : ArrowRight;
  const norm = (x: string) => x.trim().toLocaleLowerCase().replace(/\s+/g, " ");
  const start = async (force = false) => {
    const name = title.trim() || it("myBusiness");
    // Same business name already exists? Offer to open it instead of silently making a duplicate.
    const same = (q.data ?? []).find((i) => norm(i.title) === norm(name));
    if (same && !force) { setDup(same); return; }
    setBusy(true);
    try {
      const inv = await papi.create(name, cur);
      nav({ to: "/investigation/$id", params: { id: inv.id } });
    } catch (e) { onErr(e); } finally { setBusy(false); }
  };
  if (q.isError) return <ErrorNote error={q.error} onRetry={() => q.refetch()} />;
  return (
    <div className="mx-auto grid max-w-3xl gap-6 py-4">
      <section className="card-soft flex flex-col items-center gap-4 p-8 text-center">
        <LogoFull size={150} />
        <p className="text-sm font-semibold text-primary">{it("positioning")}</p>
        <h1 className="text-3xl font-bold">{it("homeTitle")}</h1>
        <p className="max-w-xl text-muted-foreground">{it("homeSub")}</p>
        <div className="mt-2 flex w-full max-w-md flex-col gap-2 sm:flex-row">
          <input value={title} onChange={(e) => { setTitle(e.target.value); setDup(null); }} maxLength={120} placeholder={it("businessName")}
            className="flex-1 rounded-lg border bg-card px-3 py-2.5" />
          <select value={cur} onChange={(e) => setCur(e.target.value)} aria-label={it("filesCurrency")} title={it("filesCurrency")} className="rounded-lg border bg-card px-2">
            {["EGP", "SAR", "AED", "USD", "EUR"].map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        <p className="-mt-2 text-xs text-muted-foreground">{it("currencyHint")}</p>
        <button className="btn btn-primary" disabled={busy} onClick={() => start()}><Search className="size-5" /> {it("newInvestigation")}</button>
        {dup && (
          <div className="w-full max-w-md rounded-xl border border-warning/50 bg-warning/10 p-3 text-sm" role="alert">
            <p>{it("alreadyHave")} <b>{dup.title}</b> ({dup.file_count ? it("filesN", { n: dup.file_count }) : it("noFilesYet")})</p>
            <div className="mt-2 flex flex-wrap justify-center gap-2">
              <Link to="/investigation/$id" params={{ id: dup.id }} className="btn btn-primary !py-1.5 text-sm">{it("openIt")}</Link>
              <button className="btn btn-outline !py-1.5 text-sm" onClick={() => { setDup(null); start(true); }}>{it("startAnyway")}</button>
            </div>
          </div>
        )}
      </section>
      {!!q.data?.length && (
        <section className="card-soft p-5">
          <h2 className="mb-3 text-lg font-bold">{it("yourInvestigations")}</h2>
          <ul className="grid gap-2">
            {q.data.map((i) => (
              <li key={i.id}>
                <Link to="/investigation/$id" params={{ id: i.id }} className="flex items-center gap-3 rounded-xl border p-3 hover:border-primary">
                  <span className="flex-1 font-semibold">{i.title}</span>
                  <span className="text-end text-xs text-muted-foreground">
                    {it(`stage_${i.stage}`)} · {i.file_count ? it("filesN", { n: i.file_count }) : it("noFilesYet")}
                    <span className="block" dir="ltr">{new Date(i.created_at * 1000).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                  </span>
                  <Arrow className="size-4" />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
