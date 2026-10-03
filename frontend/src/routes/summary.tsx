import { createFileRoute, Link } from "@tanstack/react-router";
import { Wallet, Clock, Users, CircleAlert, TrendingUp, Sparkles } from "lucide-react";
import { Shell } from "@/components/Shell";
import { PageTitle , Loading, ErrorNote } from "@/components/ui-bits";
import { useApp } from "@/lib/app-context";
import { useSummary } from "@/lib/hooks";

export const Route = createFileRoute("/summary")({
  head: () => ({
    meta: [
      { title: "الملخص — تحصيل" },
      { name: "description", content: "كم حصّلنا، وكم ما زال مستحقاً، وأين أموالك." },
      { property: "og:title", content: "الملخص — تحصيل" },
      { property: "og:description", content: "نظرة واحدة على أموالك المتأخرة." },
    ],
  }),
  component: () => <Shell><SummaryPage /></Shell>,
});

function SummaryPage() {
  const { t, money } = useApp();
  const { data, isError, refetch } = useSummary();
  if (isError) return <ErrorNote onRetry={() => refetch()} />;
  if (!data) return <Loading />;
  const m = data.money;
  const total = m.total_egp || 1;
  const L = data.learning;
  const stats = [
    { label: t("collected"), value: money(m.collected_egp), icon: Wallet, cls: "text-success bg-success/10" },
    { label: t("outstanding"), value: money(m.outstanding_egp), icon: Clock, cls: "text-primary bg-primary-soft" },
    { label: t("withTeam"), value: money(m.with_team_egp), icon: Users, cls: "text-warning bg-warning/10" },
    { label: t("waitingDecision"), value: `${data.needs_your_decision} ${t("messages")}`, icon: CircleAlert, cls: "text-warning bg-warning/10" },
  ];
  const bars = [
    { label: t("collected"), v: m.collected_egp, cls: "bg-success" },
    { label: t("outstanding"), v: m.outstanding_egp, cls: "bg-primary" },
    { label: t("withTeam"), v: m.with_team_egp, cls: "bg-warning" },
  ];

  return (
    <>
      <PageTitle>{t("nav_summary")}</PageTitle>
      {L.update_waiting_for_approval != null && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-primary bg-primary-soft p-4">
          <Sparkles className="size-6 text-primary" />
          <span className="flex-1 font-semibold">{t("updateWaiting")}</span>
          <Link to="/learning" className="btn btn-primary py-2">{t("review")}</Link>
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="card-soft p-5">
            <span className={`grid size-10 place-items-center rounded-xl ${s.cls}`}><s.icon className="size-5" /></span>
            <div className="mt-4 text-sm text-muted-foreground">{s.label}</div>
            <div className="mt-1 text-2xl font-bold tabular-nums">{s.value}</div>
          </div>
        ))}
      </div>
      <div className="card-soft mt-6 p-6">
        <h2 className="mb-4 text-lg font-bold">{t("whereMoney")}</h2>
        <div className="flex h-5 overflow-hidden rounded-full bg-muted">
          {bars.map((b) => <div key={b.label} className={b.cls} style={{ width: `${(b.v / total) * 100}%` }} />)}
        </div>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
          {bars.map((b) => (
            <div key={b.label} className="flex items-center gap-2 text-sm">
              <span className={`size-3 rounded-full ${b.cls}`} /> {b.label}: <span className="font-semibold tabular-nums">{money(b.v)}</span>
              <span className="text-muted-foreground">({Math.round((b.v / total) * 100)}%)</span>
            </div>
          ))}
        </div>
      </div>
      <div className="card-soft mt-6 flex items-center gap-4 p-6">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-success/10 text-success"><TrendingUp className="size-6" /></span>
        <div>
          <h2 className="text-lg font-bold">{t("improving")}</h2>
          <p className="text-muted-foreground">{L.update_waiting_for_approval != null && L.candidate_collection_rate != null
            ? t("improvingPending", { a: L.current_collection_rate ?? L.first_collection_rate ?? 0, b: L.candidate_collection_rate, c: L.current_complaints ?? L.first_complaints ?? 0, d: L.candidate_complaints ?? 0 })
            : L.first_collection_rate == null || L.current_collection_rate == null
            ? t("improvingNone")
            : t("improvingText", { a: L.first_collection_rate, b: L.current_collection_rate, c: L.first_complaints ?? 0, d: L.current_complaints ?? 0 })}</p>
        </div>
      </div>
    </>
  );
}
