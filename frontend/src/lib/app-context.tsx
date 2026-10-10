import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { ar, en, type Dict } from "@/i18n/tahsila";

export type Lang = "ar" | "en";
type Theme = "light" | "dark";

const EXP: Record<string, number> = { KWD: 3, BHD: 3, OMR: 3, JOD: 3, TND: 3, JPY: 0 };
const AR_SYMBOL: Record<string, string> = { EGP: "ج.م", SAR: "ر.س", AED: "د.إ" };

interface Ctx {
  lang: Lang; setLang: (l: Lang) => void;
  theme: Theme; toggleTheme: () => void;
  ready: boolean;
  t: (k: keyof Dict, vars?: Record<string, string | number>) => string;
  /** Format integer minor units in their own currency. Western digits keep IDs and amounts machine-readable. */
  money: (minor: number, currency: string) => string;
  pick: (o: { ar: string; en: string } | undefined, fallback?: string) => string;
}
const AppCtx = createContext<Ctx | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [lang, setLangS] = useState<Lang>("ar");
  const [theme, setTheme] = useState<Theme>("light");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("lang");
    if (q === "ar" || q === "en") localStorage.setItem("tahsila.lang", q);
    const l = localStorage.getItem("tahsila.lang") as Lang | null;
    const th = localStorage.getItem("tahsila.theme") as Theme | null;
    if (l === "ar" || l === "en") setLangS(l);
    setTheme(th ?? "light");
    setReady(true);
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);
  useEffect(() => { document.documentElement.classList.toggle("dark", theme === "dark"); }, [theme]);

  const setLang = (l: Lang) => { setLangS(l); localStorage.setItem("tahsila.lang", l); };
  const toggleTheme = () => setTheme((p) => { const n = p === "dark" ? "light" : "dark"; localStorage.setItem("tahsila.theme", n); return n; });
  const t = useCallback((k: keyof Dict, vars?: Record<string, string | number>) => {
    let s: string = (lang === "ar" ? ar : en)[k] ?? String(k);
    if (vars) for (const [key, v] of Object.entries(vars)) s = s.replace(`{${key}}`, String(v));
    return s;
  }, [lang]);
  const money = useCallback((minor: number, currency: string) => {
    const e = EXP[currency] ?? 2;
    const s = (minor / 10 ** e).toLocaleString("en-US", { minimumFractionDigits: e, maximumFractionDigits: e });
    const ar = AR_SYMBOL[currency];
    return lang === "ar" && ar ? `${s} ${ar}` : `${currency} ${s}`;
  }, [lang]);
  const pick = useCallback((o: { ar: string; en: string } | undefined, fallback = "") => (o ? o[lang] : fallback), [lang]);

  return <AppCtx.Provider value={{ lang, setLang, theme, toggleTheme, ready, t, money, pick }}>{children}</AppCtx.Provider>;
}

export function useApp() {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside provider");
  return c;
}
