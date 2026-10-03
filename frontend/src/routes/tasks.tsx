import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Star, Send, Ban, Play, Sunrise, MessageCircle } from "lucide-react";
import { Shell } from "@/components/Shell";
import { useState } from "react";
import { toast } from "sonner";
import { Confirm, ErrorNote, Loading, PageTitle, Working } from "@/components/ui-bits";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { useAction, useJob, useSummary } from "@/lib/hooks";
import type { Decision } from "@/lib/types";
import type { Dict } from "@/i18n/ar";

export const Route = createFileRoute("/tasks")({
  head: () => ({
    meta: [
      { title: "مهامي — تحصيل" },
      { name: "description", content: "رسائل المساعد التي تنتظر موافقتك." },
      { property: "og:title", content: "مهامي — تحصيل" },
      { property: "og:description", content: "راجع رسائل التحصيل ووافق عليها بضغطة." },
    ],
  }),
  component: () => <Shell><Tasks /></Shell>,
});

function Tasks() {
  const { t, business } = useApp();
  const { data: summary } = useSummary();
  const { data: decisions = [], isLoading, isError, refetch } = useQuery({ queryKey: ["decisions"], queryFn: api.decisions });
  const [askNewDay, setAskNewDay] = useState(false);
  const list = decisions.filter((d) => !business || d.business === business);
  const job = useJob();

  return (
    <>
      <PageTitle>{list.length ? t("needDecision", { n: list.length }) : t("emptyInbox")}</PageTitle>
      <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        {summary?.workspace?.status === "running" ? (
          <button className="btn btn-primary text-lg" disabled={job.busy || summary.assistant.paused} onClick={() => job.run(api.nextRound)}>
            <Play className="size-5 rtl:-scale-x-100" /> {t("letContinue")}
          </button>
        ) : (
          <button className="btn btn-primary text-lg" disabled={job.busy} onClick={() => setAskNewDay(true)}>
            <Sunrise className="size-5" /> {t("startDay")}
          </button>
        )}
        <Working show={job.busy} />
      </div>
      <Confirm open={askNewDay} text={t("confirmNewDay")} onNo={() => setAskNewDay(false)}
        onYes={() => { setAskNewDay(false); job.run(api.newWorkspace); }} />
      {isError ? <ErrorNote onRetry={() => refetch()} /> : isLoading ? <Loading /> : (
        <div className="grid gap-5">
          {list.map((d) => <DecisionCard key={d.decision_id} d={d} />)}
        </div>
      )}
    </>
  );
}

function DecisionCard({ d }: { d: Decision }) {
  const { t, money } = useApp();
  const approve = useAction(api.approve);
  const reject = useAction(api.reject, t("rejected"));
  const tone = t(`tone_${d.tone}` as keyof Dict);
  const proposal = d.action === "send_reminder" ? t("propose_send_reminder", { tone })
    : d.action === "offer_payment_plan" ? t("propose_offer_payment_plan", { tone, n: d.installments })
    : t("propose_other", { tone });
  const busy = approve.isPending || reject.isPending;

  return (
    <article className="card-soft p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-bold">{d.customer}</h2>
            {d.tier === "key" && (
              <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2.5 py-0.5 text-sm font-medium text-warning">
                <Star className="size-3.5 fill-current" /> {t("keyCustomer")}
              </span>
            )}
          </div>
          <p className="mt-1 text-muted-foreground">{t("overdueDays", { n: d.days_overdue })} · {d.invoice_id}</p>
        </div>
        <div className="text-3xl font-bold tabular-nums">{money(d.amount_egp)}</div>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl bg-warning/10 p-4">
          <div className="text-sm font-medium text-warning">{t("whyAsk")}</div>
          <div className="mt-1 font-semibold">{t(`why_${d.why_code}` as keyof Dict)}</div>
        </div>
        <div className="rounded-xl bg-primary-soft p-4">
          <div className="text-sm font-medium text-primary">{t("iPropose")}</div>
          <div className="mt-1 font-semibold">{proposal}</div>
        </div>
      </div>

      {d.last_reply && (
        <div className="mt-4 flex items-start gap-2 text-muted-foreground">
          <MessageCircle className="mt-0.5 size-4 shrink-0" />
          <span><span className="font-medium">{t("lastReply")}:</span> <span dir={d.language === "ar" ? "rtl" : "ltr"}>“{d.last_reply}”</span></span>
        </div>
      )}

      <div className="mt-4">
        <div className="mb-2 text-sm font-medium text-muted-foreground">{t("messagePreview")} · {t("to")} {d.contact_name}</div>
        <div dir={d.language === "ar" ? "rtl" : "ltr"} lang={d.language}
          className="whitespace-pre-line rounded-xl border bg-background p-4 leading-relaxed text-start">
          {d.message}
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row">
        <button className="btn btn-primary flex-1 text-lg" disabled={busy} onClick={() => approve.mutate(d.decision_id, {
            onSuccess: (r) => (r as { result?: string })?.result === "blocked_on_recheck" ? toast.info(t("approvedRecheck")) : toast.success(t("approved")),
          })}>
          <Send className="size-5 rtl:-scale-x-100" /> {t("approve")}
        </button>
        <button className="btn btn-outline flex-1 text-lg" disabled={busy} onClick={() => reject.mutate(d.decision_id)}>
          <Ban className="size-5" /> {t("reject")}
        </button>
      </div>
    </article>
  );
}
