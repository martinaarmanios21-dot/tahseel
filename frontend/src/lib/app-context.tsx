import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { ar, type Dict } from "@/i18n/ar";
import { en } from "@/i18n/en";

export type Lang = "ar" | "en";
export type Role = "employee" | "owner" | "accountant";
type Theme = "light" | "dark";

interface Ctx {
  lang: Lang; setLang: (l: Lang) => void;
  theme: Theme; toggleTheme: () => void;
  role: Role | null; setRole: (r: Role | null) => void;
  business: string; setBusiness: (b: string) => void;
  ready: boolean;
  t: (k: keyof Dict, vars?: Record<string, string | number>) => string;
  money: (n: number) => string;
}
const AppCtx = createContext<Ctx | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [lang, setLangS] = useState<Lang>("ar");
  const [theme, setTheme] = useState<Theme>("light");
  const [role, setRoleS] = useState<Role | null>(null);
  const [business, setBusiness] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const l = localStorage.getItem("tahseel.lang") as Lang | null;
    const th = localStorage.getItem("tahseel.theme") as Theme | null;
    const r = localStorage.getItem("tahseel.role") as Role | null;
    if (l) setLangS(l);
    setTheme(th ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
    if (r) setRoleS(r);
    setReady(true);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);
  useEffect(() => { document.documentElement.classList.toggle("dark", theme === "dark"); }, [theme]);

  const setLang = (l: Lang) => { setLangS(l); localStorage.setItem("tahseel.lang", l); };
  const toggleTheme = () => setTheme((p) => { const n = p === "dark" ? "light" : "dark"; localStorage.setItem("tahseel.theme", n); return n; });
  const setRole = (r: Role | null) => { setRoleS(r); if (r) localStorage.setItem("tahseel.role", r); else localStorage.removeItem("tahseel.role"); setBusiness(""); };

  const t = useCallback((k: keyof Dict, vars?: Record<string, string | number>) => {
    let s = (lang === "ar" ? ar : en)[k] ?? String(k);
    if (vars) for (const [key, v] of Object.entries(vars)) s = s.replace(`{${key}}`, String(v));
    return s;
  }, [lang]);
  const money = useCallback((n: number) => {
    const s = Math.round(n).toLocaleString("en-US");
    return lang === "ar" ? `${s} ج.م` : `EGP ${s}`;
  }, [lang]);

  return (
    <AppCtx.Provider value={{ lang, setLang, theme, toggleTheme, role, setRole, business, setBusiness, ready, t, money }}>
      {children}
    </AppCtx.Provider>
  );
}

export function useApp() {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside provider");
  return c;
}
