import { useApp } from "@/lib/app-context";

export function LogoMark({ size = 36 }: { size?: number }) {
  return <img src="/logo-mark.png" width={size} height={size} alt="" aria-hidden className="shrink-0" />;
}

/** The full logo (mascot + the Arabic wordmark), for the home page. */
export function LogoFull({ size = 160 }: { size?: number }) {
  return <img src="/logo.png" width={size} height={size} alt="ربحية" className="shrink-0" />;
}

export function Logo({ size = 36 }: { size?: number }) {
  const { t } = useApp();
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark size={size} />
      <span className="text-xl font-bold tracking-tight">{t("appName")}</span>
    </div>
  );
}
