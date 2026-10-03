import { CircleCheck, Clock, Hourglass, Handshake, Users, ShieldAlert, CircleAlert, Loader2, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { useApp } from "@/lib/app-context";
import { useMockMode } from "@/lib/api";
import type { Status } from "@/lib/types";
import { cn } from "@/lib/utils";

const statusStyle: Record<Status, { icon: typeof Clock; cls: string }> = {
  needs_you: { icon: CircleAlert, cls: "text-warning bg-warning/10" },
  waiting: { icon: Clock, cls: "text-muted-foreground bg-muted" },
  in_progress: { icon: Hourglass, cls: "text-primary bg-primary-soft" },
  paid: { icon: CircleCheck, cls: "text-success bg-success/10" },
  paid_by_plan: { icon: Handshake, cls: "text-success bg-success/10" },
  with_team: { icon: Users, cls: "text-warning bg-warning/10" },
  suspicious: { icon: ShieldAlert, cls: "text-danger bg-danger/10" },
};

export function StatusBadge({ status }: { status: Status }) {
  const { t } = useApp();
  const s = statusStyle[status];
  const Icon = s.icon;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-medium", s.cls)}>
      <Icon className="size-4" /> {t(`status_${status}`)}
    </span>
  );
}

export function MockBadge() {
  const mock = useMockMode();
  const { t } = useApp();
  if (!mock) return null;
  return <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">{t("demoData")}</span>;
}

export function Working({ show }: { show: boolean }) {
  const { t } = useApp();
  if (!show) return null;
  return (
    <div className="flex items-center gap-2 rounded-xl bg-primary-soft px-4 py-3 text-primary font-medium">
      <Loader2 className="size-5 animate-spin" /> {t("working")}
    </div>
  );
}

export function PageTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-bold sm:text-3xl">{children}</h1>
      {sub && <p className="mt-1.5 text-muted-foreground">{sub}</p>}
    </div>
  );
}

export function Sheet({ open, onClose, children, title }: { open: boolean; onClose: () => void; children: ReactNode; title: ReactNode }) {
  const { t } = useApp();
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-foreground/30 animate-in fade-in" onClick={onClose} />
      <aside className="absolute inset-y-0 end-0 flex w-full max-w-lg flex-col bg-background shadow-2xl animate-in slide-in-from-end">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div className="font-bold text-lg">{title}</div>
          <button onClick={onClose} aria-label={t("close")} className="rounded-lg p-2 hover:bg-muted"><X className="size-5" /></button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </aside>
    </div>
  );
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
      <div className="card-soft relative w-full max-w-sm p-6 animate-in zoom-in-95">
        <p className="text-lg font-semibold">{text}</p>
        <div className="mt-6 flex gap-3">
          <button autoFocus className={cn("btn flex-1", danger ? "btn-danger" : "btn-primary")} onClick={onYes}>{t("yes")}</button>
          <button className="btn btn-outline flex-1" onClick={onNo}>{t("cancel")}</button>
        </div>
      </div>
    </div>
  );
}

/** Calm placeholder while data loads (no spinners jumping around). */
export function Loading({ rows = 3 }: { rows?: number }) {
  const { t } = useApp();
  return (
    <div className="grid gap-4" aria-busy="true" aria-label={t("loading")}>
      <div className="h-8 w-1/3 animate-pulse rounded-lg bg-muted" />
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="h-28 animate-pulse rounded-2xl bg-muted" />)}
    </div>
  );
}

/** Plain-language error with a retry button (never raw codes). */
export function ErrorNote({ onRetry }: { onRetry?: () => void }) {
  const { t } = useApp();
  return (
    <div role="alert" className="card-soft flex flex-col items-start gap-3 border-danger/30 p-6">
      <p className="font-semibold text-danger">{t("loadError")}</p>
      {onRetry && <button className="btn btn-outline" onClick={onRetry}>{t("retry")}</button>}
    </div>
  );
}
