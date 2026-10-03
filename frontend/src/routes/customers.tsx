import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Search, Star, Bot, User } from "lucide-react";
import { useMemo, useState } from "react";
import { Shell } from "@/components/Shell";
import { PageTitle, Sheet, StatusBadge, Loading, ErrorNote } from "@/components/ui-bits";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { STATUSES, type Customer, type Status } from "@/lib/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/customers")({
  head: () => ({
    meta: [
      { title: "العملاء — تحصيل" },
      { name: "description", content: "كل العملاء وحالة فواتيرهم وما فعله المساعد معهم." },
      { property: "og:title", content: "العملاء — تحصيل" },
      { property: "og:description", content: "تابع حالة كل فاتورة متأخرة." },
    ],
  }),
  component: () => <Shell><Customers /></Shell>,
});

function Customers() {
  const { t, money, business } = useApp();
  const { data = [], isLoading, isError, refetch } = useQuery({ queryKey: ["customers"], queryFn: api.customers });
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<Status | "">("");
  const [open, setOpen] = useState<string | null>(null);

  const list = useMemo(() => data.filter((c) =>
    (!business || c.business === business) && (!status || c.status === status) &&
    (!q || c.customer.toLowerCase().includes(q.toLowerCase()) || c.invoice_id.toLowerCase().includes(q.toLowerCase()))
  ), [data, business, status, q]);

  if (isError) return <ErrorNote onRetry={() => refetch()} />;
  if (isLoading) return <Loading />;
  return (
    <>
      <PageTitle>{t("nav_customers")}</PageTitle>
      <div className="relative mb-4">
        <Search className="pointer-events-none absolute start-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")}
          className="w-full rounded-xl border bg-card py-3.5 ps-12 pe-4 text-base outline-none focus:ring-2 focus:ring-ring" />
      </div>
      <div className="mb-6 flex flex-wrap gap-2">
        {(["", ...STATUSES] as const).map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
            className={cn("rounded-full border px-3.5 py-1.5 text-sm font-medium transition", status === s ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-muted")}>
            {s ? t(`status_${s}`) : t("all")}
          </button>
        ))}
      </div>
      <div className="card-soft divide-y overflow-hidden">
        {list.length === 0 && <p className="p-8 text-center text-muted-foreground">{t("noResults")}</p>}
        {list.map((c) => (
          <button key={c.invoice_id} onClick={() => setOpen(c.invoice_id)} className="flex w-full flex-wrap items-center gap-3 p-4 text-start hover:bg-muted/50">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 font-semibold">
                {c.tier === "key" && <Star className="size-4 fill-warning text-warning" />}
                <span className="truncate">{c.customer}</span>
              </div>
              <div className="text-sm text-muted-foreground">{c.invoice_id} · {t("overdueDays", { n: c.days_overdue })}</div>
            </div>
            <div className="font-bold tabular-nums">{money(c.amount_egp)}</div>
            <StatusBadge status={c.status} />
          </button>
        ))}
      </div>
      <CustomerSheet id={open} onClose={() => setOpen(null)} />
    </>
  );
}

function CustomerSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { t, money } = useApp();
  const { data: c } = useQuery({ queryKey: ["customer", id], queryFn: () => api.customer(id!), enabled: !!id });
  return (
    <Sheet open={!!id} onClose={onClose} title={c?.customer ?? ""}>
      {c && <Detail c={c} t={t} money={money} />}
    </Sheet>
  );
}

function Detail({ c, t, money }: { c: Customer; t: ReturnType<typeof useApp>["t"]; money: (n: number) => string }) {
  return (
    <div>
      <div className="text-3xl font-bold tabular-nums">{money(c.amount_egp)}</div>
      <div className="mt-1 text-muted-foreground">{c.invoice_id} · {t("overdueDays", { n: c.days_overdue })} · {t("contacted", { n: c.times_contacted })}</div>
      <div className="mt-3"><StatusBadge status={c.status} /></div>
      <h3 className="mb-4 mt-8 font-bold">{t("timeline")}</h3>
      <div className="flex flex-col gap-3">
        {(c.timeline ?? []).map((e, i) => {
          const fromCustomer = e.action === "customer_reply";
          return (
            <div key={i} className={cn("flex items-end gap-2", fromCustomer ? "flex-row-reverse" : "")}>
              <span className={cn("grid size-8 shrink-0 place-items-center rounded-full", fromCustomer ? "bg-muted" : "bg-primary-soft text-primary")}>
                {fromCustomer ? <User className="size-4" /> : <Bot className="size-4" />}
              </span>
              <div className={cn("max-w-[80%] rounded-2xl px-4 py-3", fromCustomer ? "bg-muted" : "bg-primary-soft")}>
                <div className="mb-1 text-xs font-medium text-muted-foreground">{fromCustomer ? t("customerSaid") : t("assistantDid")}</div>
                <div className="whitespace-pre-line" dir="auto">{e.message}</div>
              </div>
            </div>
          );
        })}
        {!c.timeline?.length && <p className="text-muted-foreground">{t("status_waiting")}</p>}
      </div>
    </div>
  );
}
