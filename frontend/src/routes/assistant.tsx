import { createFileRoute } from "@tanstack/react-router";
import { CircleCheck, CircleX, Power } from "lucide-react";
import { useState } from "react";
import { Shell } from "@/components/Shell";
import { Confirm, PageTitle } from "@/components/ui-bits";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { useAction, useSummary } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/assistant")({
  head: () => ({
    meta: [
      { title: "المساعد — تحصيل" },
      { name: "description", content: "ما يستطيع المساعد فعله وما لا يفعله أبداً، وزر الإيقاف المؤقت." },
      { property: "og:title", content: "المساعد — تحصيل" },
      { property: "og:description", content: "حدود واضحة وزر إيقاف في أي وقت." },
    ],
  }),
  component: () => <Shell><Assistant /></Shell>,
});

function Assistant() {
  const { t } = useApp();
  const { data } = useSummary();
  const paused = !!data?.assistant.paused;
  const [ask, setAsk] = useState(false);
  const kill = useAction(api.kill);

  return (
    <>
      <PageTitle>{t("nav_assistant")}</PageTitle>
      <div className={cn("card-soft flex items-center gap-4 p-6", paused && "border-danger")}>
        <span className={cn("grid size-14 shrink-0 place-items-center rounded-2xl", paused ? "bg-danger/10 text-danger" : "bg-success/10 text-success")}>
          <Power className="size-7" />
        </span>
        <div className="flex-1">
          <div className="text-lg font-bold">{t("pauseAssistant")}</div>
          <div className="text-muted-foreground">{t("pauseHint")}</div>
        </div>
        <button role="switch" aria-checked={paused} aria-label={t("pauseAssistant")} onClick={() => setAsk(true)} disabled={!data || kill.isPending}
          className={cn("relative h-9 w-16 shrink-0 rounded-full transition", paused ? "bg-danger" : "bg-muted border")}>
          <span className={cn("absolute top-1 size-7 rounded-full bg-card shadow transition-all", paused ? "start-8" : "start-1")} />
        </button>
      </div>
      <div className="mt-6 grid gap-5 md:grid-cols-2">
        <List title={t("canDo")} ok items={[t("can1"), t("can2"), t("can3"), t("can4")]} />
        <List title={t("cantDo")} items={[t("cant1"), t("cant2"), t("cant3"), t("cant4"), t("cant5")]} />
      </div>
      {data && <p className="mt-6 text-sm text-muted-foreground">{t("version")}: {data.assistant.skill_version}</p>}
      <Confirm open={ask} danger={!paused} text={paused ? t("confirmResume") : t("confirmPause")}
        onNo={() => setAsk(false)} onYes={() => { setAsk(false); kill.mutate(!paused); }} />
    </>
  );
}

function List({ title, items, ok }: { title: string; items: string[]; ok?: boolean }) {
  const Icon = ok ? CircleCheck : CircleX;
  return (
    <div className="card-soft p-6">
      <h2 className="mb-4 text-lg font-bold">{title}</h2>
      <ul className="grid gap-3">
        {items.map((i) => (
          <li key={i} className="flex items-start gap-3">
            <Icon className={cn("mt-0.5 size-5 shrink-0", ok ? "text-success" : "text-danger")} /> <span>{i}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
