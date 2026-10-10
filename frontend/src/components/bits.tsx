import { Loader2, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { toast } from "sonner";
import { useApp } from "@/lib/app-context";
import { ApiError } from "@/lib/tapi";
import { BLOCKS } from "@/i18n/tahsila";
import { cn } from "@/lib/utils";

export function PageTitle({ children, sub, action }: { children: ReactNode; sub?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold sm:text-3xl">{children}</h1>
        {sub && <p className="mt-1.5 max-w-3xl text-muted-foreground">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

export function Card({ children, className, title, action }: { children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode }) {
  return (
    <section className={cn("card-soft p-5", className)}>
      {(title || action) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-lg font-bold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Loading() {
  const { t } = useApp();
  return (
    <div className="grid gap-4" aria-busy="true" aria-label={t("loading")}>
      <div className="h-8 w-1/3 animate-pulse rounded-lg bg-muted" />
      {[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-muted" />)}
    </div>
  );
}

export function ErrorNote({ error, onRetry }: { error?: unknown; onRetry?: () => void }) {
  const { t } = useApp();
  const down = error instanceof ApiError && (error.code === "network" || error.code === "not_json");
  const unauth = error instanceof ApiError && error.status === 401;
  return (
    <div role="alert" className="card-soft flex flex-col items-start gap-3 border-danger/30 p-6">
      <p className="font-semibold text-danger">{down ? t("serverDown") : unauth ? t("tokenNeeded") : t("loadError")}</p>
      {unauth && <button className="btn btn-primary" onClick={() => { const v = window.prompt(t("tokenPrompt")); if (v) { localStorage.setItem("tahsila.token", v); window.location.reload(); } }}>{t("enterToken")}</button>}
      {error instanceof ApiError && !down && <p className="text-sm text-muted-foreground">{error.message}</p>}
      {onRetry && <button className="btn btn-outline" onClick={onRetry}>{t("retry")}</button>}
    </div>
  );
}

export function Pill({ children, tone = "muted", title }: { children: ReactNode; tone?: "muted" | "ok" | "warn" | "danger" | "primary"; title?: string }) {
  const cls = { muted: "bg-muted text-muted-foreground", ok: "bg-success/10 text-success", warn: "bg-warning/10 text-warning",
    danger: "bg-danger/10 text-danger", primary: "bg-primary-soft text-primary" }[tone];
  return <span title={title} className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", cls)}>{children}</span>;
}

export function Confirm({ open, text, onYes, onNo, danger }: { open: boolean; text: string; onYes: () => void; onNo: () => void; danger?: boolean }) {
  const { t } = useApp();
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onNo();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onNo]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4" role="dialog" aria-modal="true" aria-label={text}>
      <div className="absolute inset-0 bg-foreground/30" onClick={onNo} />
      <div className="card-soft relative w-full max-w-sm p-6">
        <button onClick={onNo} aria-label={t("cancel")} className="absolute end-3 top-3 rounded p-1 hover:bg-muted"><X className="size-4" /></button>
        <p className="text-lg font-semibold">{text}</p>
        <div className="mt-6 flex gap-3">
          <button autoFocus className={cn("btn flex-1", danger ? "btn-danger" : "btn-primary")} onClick={onYes}>{t("yes")}</button>
          <button className="btn btn-outline flex-1" onClick={onNo}>{t("cancel")}</button>
        </div>
      </div>
    </div>
  );
}

export function Spinner({ show, label }: { show: boolean; label?: string }) {
  if (!show) return null;
  return <span className="inline-flex items-center gap-2 text-sm text-primary"><Loader2 className="size-4 animate-spin" />{label}</span>;
}

/** Localised policy blocks from an ApiError (or a raw list). */
export function Blocks({ blocks }: { blocks: { code: string; reason: string }[] }) {
  const { pick, t } = useApp();
  if (!blocks.length) return null;
  return (
    <div role="alert" className="rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm">
      <div className="mb-1 font-semibold text-warning">{t("blockedTitle")}</div>
      <ul className="list-disc ps-5">
        {blocks.map((b, i) => <li key={i}>{pick(BLOCKS[b.code], b.reason)}</li>)}
      </ul>
    </div>
  );
}

/** Toast an API error in the UI language; asks for the admin token on 401. */
export function useErrorToast() {
  const { pick, t } = useApp();
  return (e: unknown) => {
    if (e instanceof ApiError) {
      if (e.status === 401) {
        const tok = window.prompt(t("tokenPrompt"));
        if (tok) localStorage.setItem("tahsila.token", tok);
        toast.error(t("tokenNeeded"));
        return;
      }
      const msg = e.blocks.length ? e.blocks.map((b) => pick(BLOCKS[b.code], b.reason)).join(" · ") : pick(BLOCKS[e.code], e.message);
      toast.error(msg);
    } else toast.error(String(e));
  };
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: string }) {
  return (
    <div className="card-soft p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className={cn("mt-1 text-xl font-bold tabular-nums sm:text-2xl", tone)} dir="ltr" style={{ textAlign: "start" }}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}
