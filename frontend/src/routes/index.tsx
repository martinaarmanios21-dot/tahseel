import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Headset, Briefcase, Calculator, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect } from "react";
import { LogoMark } from "@/components/Logo";
import { Footer, NAV } from "@/components/Shell";
import { useApp, type Role } from "@/lib/app-context";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "تحصيل — مساعدك لتحصيل الفواتير المتأخرة" },
      { name: "description", content: "اختر دورك وابدأ: موظف التحصيل، صاحب العمل، أو المحاسب." },
      { property: "og:title", content: "تحصيل — مساعدك لتحصيل الفواتير المتأخرة" },
      { property: "og:description", content: "مساعد ذكي يذكّر عملاءك بلطف ويحصّل فواتيرك المتأخرة." },
    ],
  }),
  component: Welcome,
});

const roles: { id: Role; icon: typeof Headset }[] = [
  { id: "employee", icon: Headset },
  { id: "owner", icon: Briefcase },
  { id: "accountant", icon: Calculator },
];

function Welcome() {
  const { t, role, setRole, ready, lang, setLang } = useApp();
  const navigate = useNavigate();
  useEffect(() => { if (ready && role) navigate({ to: NAV[role][0]!.to, replace: true }); }, [ready, role, navigate]);
  if (!ready || role) return null;
  const Chevron = lang === "ar" ? ChevronLeft : ChevronRight;

  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex justify-end p-4">
        <button onClick={() => setLang(lang === "ar" ? "en" : "ar")} className="rounded-lg border bg-card px-3 py-1.5 text-sm font-semibold">ع / EN</button>
      </div>
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center px-4 pb-10 text-center">
        <LogoMark size={72} />
        <h1 className="mt-6 text-3xl font-bold sm:text-4xl">{t("welcomeTitle")}</h1>
        <p className="mt-3 text-lg text-muted-foreground">{t("welcomeSub")}</p>
        <div className="mt-10 grid w-full gap-4">
          {roles.map(({ id, icon: Icon }) => (
            <button key={id} onClick={() => setRole(id)}
              className="card-soft group flex items-center gap-4 p-5 text-start transition hover:border-primary hover:-translate-y-0.5">
              <span className="grid size-14 shrink-0 place-items-center rounded-2xl bg-primary-soft text-primary"><Icon className="size-7" /></span>
              <span className="flex-1">
                <span className="block text-lg font-bold">{t(`role_${id}`)}</span>
                <span className="block text-muted-foreground">{t(`role_${id}_desc`)}</span>
              </span>
              <Chevron className="size-6 text-muted-foreground group-hover:text-primary" />
            </button>
          ))}
        </div>
      </main>
      <Footer />
    </div>
  );
}
