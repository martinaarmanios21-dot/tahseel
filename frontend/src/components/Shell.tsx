import { Link, useNavigate } from "@tanstack/react-router";
import { Moon, Sun, ArrowLeftRight, Inbox, Users, Bot, LayoutDashboard, Sparkles, Building2 } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Logo } from "./Logo";
import { MockBadge } from "./ui-bits";
import { useApp, type Role } from "@/lib/app-context";
import { useSummary } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { Dict } from "@/i18n/ar";

type NavTo = "/tasks" | "/customers" | "/assistant" | "/summary" | "/learning" | "/businesses";
export const NAV: Record<Role, { to: NavTo; key: keyof Dict }[]> = {
  employee: [{ to: "/tasks", key: "nav_tasks" }, { to: "/customers", key: "nav_customers" }, { to: "/assistant", key: "nav_assistant" }],
  owner: [{ to: "/summary", key: "nav_summary" }, { to: "/learning", key: "nav_learning" }, { to: "/customers", key: "nav_customers" }, { to: "/assistant", key: "nav_assistant" }],
  accountant: [{ to: "/businesses", key: "nav_businesses" }, { to: "/tasks", key: "nav_tasks" }, { to: "/customers", key: "nav_customers" }, { to: "/assistant", key: "nav_assistant" }],
};

const NAV_ICON: Record<NavTo, typeof Inbox> = {
  "/tasks": Inbox, "/customers": Users, "/assistant": Bot, "/summary": LayoutDashboard, "/learning": Sparkles, "/businesses": Building2,
};

export function Shell({ children }: { children: ReactNode }) {
  const { role, setRole, t, lang, setLang, theme, toggleTheme, business, setBusiness } = useApp();
  const navigate = useNavigate();
  const { data } = useSummary();
  const { ready } = useApp();
  useEffect(() => { if (ready && !role) navigate({ to: "/" }); }, [ready, role, navigate]);
  if (!role) return null;
  const paused = data?.assistant.paused;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b bg-card/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2 px-4 py-3">
          <Link to="/"><Logo size={32} /></Link>
          <button
            onClick={() => { setRole(null); navigate({ to: "/" }); }}
            title={t("switchRole")}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary-soft px-3 py-1.5 text-sm font-medium text-primary hover:opacity-80"
          >
            {t(`role_${role}`)} <ArrowLeftRight className="size-3.5" />
          </button>
          {data && (
            <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium", paused ? "bg-danger/10 text-danger" : "bg-success/10 text-success")}>
              <span className={cn("size-2 rounded-full", paused ? "bg-danger" : "bg-success animate-pulse")} />
              {paused ? t("assistantOff") : t("assistantOn")}
            </span>
          )}
          <MockBadge />
          <div className="ms-auto flex items-center gap-1.5">
            {role === "accountant" && data && (
              <select value={business} onChange={(e) => setBusiness(e.target.value)} className="rounded-lg border bg-card px-2 py-1.5 text-sm">
                <option value="">{t("allBusinesses")}</option>
                {data.businesses.map((b) => <option key={b.id} value={b.id}>{lang === "ar" ? b.name_ar : b.name_en}</option>)}
              </select>
            )}
            <button onClick={() => setLang(lang === "ar" ? "en" : "ar")} aria-label={t("language")} className="min-h-10 rounded-lg border px-2.5 py-1.5 text-sm font-semibold hover:bg-muted">ع / EN</button>
            <button onClick={toggleTheme} aria-label={t("theme")} className="min-h-10 min-w-10 rounded-lg border p-2 hover:bg-muted">
              {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
          </div>
        </div>
        <nav className="mx-auto hidden max-w-5xl gap-1 overflow-x-auto px-4 sm:flex" aria-label={t("menu")}>
          {NAV[role].map((n) => (
            <Link key={n.to} to={n.to}
              className="whitespace-nowrap border-b-2 border-transparent px-4 py-3 font-medium text-muted-foreground hover:text-foreground"
              activeProps={{ className: "!border-primary !text-primary" }}>
              {t(n.key)}
            </Link>
          ))}
        </nav>
      </header>
      {paused && <div className="bg-danger px-4 py-2.5 text-center font-medium text-destructive-foreground">{t("pausedBanner")}</div>}
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-28 pt-8 sm:pb-8">{children}</main>
      <Footer />
      {/* Mobile: bottom tab bar with big touch targets */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t bg-card/95 backdrop-blur sm:hidden" aria-label={t("menu")}>
        {NAV[role].map((n) => {
          const Icon = NAV_ICON[n.to];
          return (
            <Link key={n.to} to={n.to} className="flex min-h-16 flex-1 flex-col items-center justify-center gap-1 text-xs font-medium text-muted-foreground"
              activeProps={{ className: "!text-primary" }}>
              <Icon className="size-5" aria-hidden="true" />
              {t(n.key)}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

export function Footer() {
  const { t } = useApp();
  return (
    <footer className="py-6 text-center text-sm text-muted-foreground">
      <a href="/judges" target="_blank" rel="noreferrer" className="hover:text-primary underline-offset-4 hover:underline">{t("judgesLink")}</a>
    </footer>
  );
}
