import { useApp } from "@/lib/app-context";

export function LogoMark({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden className="shrink-0">
      <rect width="40" height="40" rx="11" className="fill-primary" />
      <g className="stroke-primary-foreground" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d="M7 12h11c3 0 4 1.5 4 4" />
        <path d="M18.5 8.5 22 12l-3.5 3.5" transform="translate(0 4) rotate(90 22 12)" />
        <rect x="11" y="18" width="22" height="14" rx="3.5" />
        <path d="M33 23h-5a2 2 0 0 0 0 4h5" />
      </g>
    </svg>
  );
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
