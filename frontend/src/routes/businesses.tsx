import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Building2 } from "lucide-react";
import { Shell } from "@/components/Shell";
import { PageTitle , Loading, ErrorNote } from "@/components/ui-bits";
import { useApp } from "@/lib/app-context";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export const Route = createFileRoute("/businesses")({
  head: () => ({
    meta: [
      { title: "الشركات — تحصيل" },
      { name: "description", content: "تابع التحصيل لكل شركة تعمل معها." },
      { property: "og:title", content: "الشركات — تحصيل" },
      { property: "og:description", content: "كل شركاتك في مكان واحد." },
    ],
  }),
  component: () => <Shell><Businesses /></Shell>,
});

function Businesses() {
  const { t, money, lang, setBusiness } = useApp();
  const navigate = useNavigate();
  const { data, isError, refetch } = useQuery({ queryKey: ["summary", ""], queryFn: () => api.summary() });
  if (isError) return <ErrorNote onRetry={() => refetch()} />;
  if (!data) return <Loading />;
  return (
    <>
      <PageTitle>{t("nav_businesses")}</PageTitle>
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {data.businesses.map((b) => {
          const total = b.collected_egp + b.outstanding_egp || 1;
          const pct = Math.round((b.collected_egp / total) * 100);
          return (
            <div key={b.id} className="card-soft flex flex-col p-6">
              <div className="flex items-center gap-3">
                <span className="grid size-11 place-items-center rounded-xl bg-primary-soft text-primary"><Building2 className="size-5" /></span>
                <div>
                  <h2 className="text-lg font-bold">{lang === "ar" ? b.name_ar : b.name_en}</h2>
                  <p className="text-sm text-muted-foreground">{t("customersN", { n: b.customers })}</p>
                </div>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-3">
                <div><div className="text-sm text-muted-foreground">{t("collected")}</div><div className="font-bold text-success tabular-nums">{money(b.collected_egp)}</div></div>
                <div><div className="text-sm text-muted-foreground">{t("outstanding")}</div><div className="font-bold tabular-nums">{money(b.outstanding_egp)}</div></div>
              </div>
              <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-success" style={{ width: `${pct}%` }} /></div>
              <div className="mt-1 text-sm text-muted-foreground">{pct}%</div>
              <button className="btn btn-primary mt-5" onClick={() => { setBusiness(b.id); navigate({ to: "/tasks" }); }}>{t("open")}</button>
            </div>
          );
        })}
      </div>
    </>
  );
}
