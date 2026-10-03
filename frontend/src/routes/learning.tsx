import type { Dict } from "@/i18n/ar";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { CircleCheck, CircleX, ChevronDown, Dumbbell, Lightbulb, ArrowLeft, ArrowRight } from "lucide-react";
import { useState } from "react";
import { Shell } from "@/components/Shell";
import { PageTitle, Working, Loading, ErrorNote, Confirm } from "@/components/ui-bits";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { useAction, useJob } from "@/lib/hooks";
import { ruleSentence } from "@/lib/rules";
import type { Metrics, Rule } from "@/lib/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/learning")({
  head: () => ({
    meta: [
      { title: "ما تعلّمته — تحصيل" },
      { name: "description", content: "تحسينات المساعد المختبرة، ولا يُطبّق أي منها إلا بموافقتك." },
      { property: "og:title", content: "ما تعلّمته — تحصيل" },
      { property: "og:description", content: "قارن قبل وبعد، ثم وافق على التحسين." },
    ],
  }),
  component: () => <Shell><Learning /></Shell>,
});

function Learning() {
  const { t } = useApp();
  const { data, isError, refetch } = useQuery({ queryKey: ["insights"], queryFn: api.insights });
  const promote = useAction(api.promote, t("applied"));
  const rollback = useAction(api.rollback, t("undone"));
  const [askApply, setAskApply] = useState(false);
  const [askUndo, setAskUndo] = useState(false);
  const job = useJob();
  const [demo, setDemo] = useState(false);
  if (isError) return <ErrorNote onRetry={() => refetch()} />;
  if (!data) return <Loading />;
  const w = data.waiting_for_approval;

  return (
    <>
      <PageTitle sub={t("learningIntro")}>{t("nav_learning")}</PageTitle>
      {w ? (
        <section className="card-soft p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-bold">{t("newUpdate")} · {w.version}</h2>
            <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-medium", w.test_results.passed ? "bg-success/10 text-success" : "bg-danger/10 text-danger")}>
              {w.test_results.passed ? <CircleCheck className="size-4" /> : <CircleX className="size-4" />}
              {w.test_results.passed ? t("passed") : t("failed")}
            </span>
          </div>
          <Compare before={w.test_results.before} after={w.test_results.after} />
          {!w.test_results.passed && (
            <ul className="mt-4 grid gap-2 rounded-xl bg-danger/10 p-4 text-danger">
              {w.test_results.reasons.map((r) => <li key={r}>• {t(`reason_${r}` as keyof Dict)}</li>)}
            </ul>
          )}
          <h3 className="mb-3 mt-6 font-bold">{t("newRules")}</h3>
          <Rules rules={w.rules} />
          {w.test_results.passed && (
            <button className="btn btn-primary mt-6 w-full text-lg sm:w-auto" disabled={promote.isPending} onClick={() => setAskApply(true)}>
              <CircleCheck className="size-5" /> {t("applyUpdate")}
            </button>
          )}
        </section>
      ) : (
        <p className="card-soft p-6 text-muted-foreground">{t("noUpdate")}</p>
      )}

      <section className="card-soft mt-6 p-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold">{t("currentRules")} · {data.active.version}</h2>
          {data.history.some((h) => h.status === "retired") && (
            <button className="btn btn-outline text-sm" disabled={rollback.isPending} onClick={() => setAskUndo(true)}>{t("undoUpdate")}</button>
          )}
        </div>
        <Confirm open={askApply} text={t("confirmApply")} onNo={() => setAskApply(false)}
          onYes={() => { setAskApply(false); if (data.waiting_for_approval) promote.mutate(data.waiting_for_approval.version); }} />
        <Confirm open={askUndo} danger text={t("confirmUndo")} onNo={() => setAskUndo(false)}
          onYes={() => { setAskUndo(false); rollback.mutate(undefined); }} />
        <Rules rules={data.active.rules} />
      </section>

      <section className="mt-6 rounded-2xl border border-dashed">
        <button onClick={() => setDemo(!demo)} className="flex w-full items-center justify-between p-4 font-medium text-muted-foreground">
          {t("demoLearning")} <ChevronDown className={cn("size-5 transition", demo && "rotate-180")} />
        </button>
        {demo && (
          <div className="flex flex-col gap-3 px-4 pb-4 sm:flex-row sm:items-center">
            <button className="btn btn-outline" disabled={job.busy} onClick={() => job.run(api.train)}><Dumbbell className="size-5" /> {t("train")}</button>
            <button className="btn btn-outline" disabled={job.busy} onClick={() => job.run(api.learn)}><Lightbulb className="size-5" /> {t("learn")}</button>
            <Working show={job.busy} />
          </div>
        )}
      </section>
    </>
  );
}

function Compare({ before, after }: { before: Metrics; after: Metrics }) {
  const { t } = useApp();
  const rows = [
    { label: t("collectionRate"), b: `${before.collection_rate}%`, a: `${after.collection_rate}%`, good: after.collection_rate >= before.collection_rate },
    { label: t("complaints"), b: before.complaints, a: after.complaints, good: after.complaints <= before.complaints },
    { label: t("safetyTests"), b: `${before.safety_tests_passed}/${before.safety_tests_total}`, a: `${after.safety_tests_passed}/${after.safety_tests_total}`, good: after.safety_tests_passed === after.safety_tests_total },
  ];
  return (
    <div className="mt-5 grid gap-3 sm:grid-cols-3">
      {rows.map((r) => (
        <div key={r.label} className="rounded-xl bg-muted/60 p-4">
          <div className="text-sm text-muted-foreground">{r.label}</div>
          <div className="mt-2 flex items-baseline gap-3 tabular-nums">
            <span className="text-muted-foreground"><span className="text-xs">{t("before")} </span>{r.b}</span>
            <span className={cn("text-2xl font-bold", r.good ? "text-success" : "text-danger")}><span className="text-xs font-normal text-muted-foreground">{t("after")} </span>{r.a}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function Rules({ rules }: { rules: Rule[] }) {
  const { t, lang } = useApp();
  const Arrow = lang === "ar" ? ArrowLeft : ArrowRight;
  return (
    <ul className="grid gap-2">
      {rules.map((r, i) => {
        const s = ruleSentence(r, t);
        return (
          <li key={i} className="flex flex-wrap items-center gap-2 rounded-xl border p-3">
            <span className="text-muted-foreground">{t("when")}</span>
            <span className="font-medium">{s.when}</span>
            <Arrow className="size-4 text-primary" />
            <span className="text-muted-foreground">{t("iDo")}</span>
            <span className="font-semibold text-primary">{s.action}</span>
          </li>
        );
      })}
    </ul>
  );
}
