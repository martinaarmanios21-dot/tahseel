import { Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Moon, Power, Sun } from "lucide-react";
import { useState, type ReactNode } from "react";
import { GuideChat } from "./GuideChat";
import { LogoMark } from "./Logo";
import { Confirm, useErrorToast } from "./bits";
import { useApp } from "@/lib/app-context";
import { tapi } from "@/lib/tapi";
import { cn } from "@/lib/utils";

export function useStatus() {
  return useQuery({ queryKey: ["status"], queryFn: tapi.status, refetchInterval: 15000, retry: 1 });
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t, lang, setLang, theme, toggleTheme } = useApp();
  const { data: s } = useStatus();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const [ask, setAsk] = useState(false);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b bg-card/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Link to="/" className="flex items-center gap-2.5">
            <LogoMark size={36} />
            <span className="leading-tight">
              <span className="block text-lg font-bold">{t("appName")} <span className="text-sm font-medium text-muted-foreground">· {lang === "ar" ? "Ribhiya" : "ربحية"}</span></span>
              <span className="block text-xs text-muted-foreground">{t("role")}</span>
            </span>
          </Link>
          <div className="ms-auto flex items-center gap-1.5">
            {s && (
              <button onClick={() => setAsk(true)} title={s.kill_switch ? t("resume") : t("pause")} className={cn("inline-flex min-h-10 items-center gap-1.5 rounded-lg border px-2.5 text-sm font-semibold",
                s.kill_switch ? "border-danger bg-danger text-destructive-foreground" : "hover:bg-muted")}>
                <Power className="size-4" /> <span className={s.kill_switch ? "" : "sr-only"}>{s.kill_switch ? t("resume") : t("pause")}</span>
              </button>
            )}
            <button onClick={() => setLang(lang === "ar" ? "en" : "ar")} aria-label={t("language")} className="min-h-10 rounded-lg border px-2.5 text-sm font-semibold hover:bg-muted">{lang === "ar" ? "EN" : "ع"}</button>
            <button onClick={toggleTheme} aria-label={t("theme")} className="min-h-10 min-w-10 rounded-lg border p-2 hover:bg-muted">
              {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
          </div>
        </div>
      </header>
      {s?.kill_switch && <div className="bg-danger px-4 py-2 text-center text-sm font-medium text-destructive-foreground">{t("killOn")}</div>}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-24 pt-6">{children}</main>
      <GuideChat />
      <Confirm open={ask} danger={!s?.kill_switch} text={s?.kill_switch ? t("confirmResume") : t("confirmPause")} onNo={() => setAsk(false)}
        onYes={() => { setAsk(false); tapi.kill(!s?.kill_switch).then(() => qc.invalidateQueries()).catch(onErr); }} />
    </div>
  );
}
