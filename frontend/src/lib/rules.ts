import type { Dict } from "@/i18n/ar";
import type { Rule } from "./types";

type T = (k: keyof Dict, v?: Record<string, string | number>) => string;
const k = (s: string) => s as keyof Dict;

export function ruleSentence(r: Rule, t: T) {
  const w: string[] = [];
  if (r.when.signal) w.push(t(k(`sig_${r.when.signal}`)));
  if (r.when.tier) w.push(t(k(`tier_${r.when.tier}`)));
  if (r.when.history) w.push(t(k(`hist_${r.when.history}`)));
  if (r.when.touch) w.push(t(k(`touch_${r.when.touch}`)));
  const d: string[] = [t(k(`act_${r.do.action}`))];
  if (r.do.installments) d.push(t("installmentsN", { n: r.do.installments }));
  if (r.do.tone) d.push(t("toneWord", { tone: t(k(`tone_${r.do.tone}`)) }));
  if (r.do.include_payment_link) d.push(t("withLink"));
  if (r.do.mention_due_date) d.push(t("withDueDate"));
  return { when: w.length ? w.join(" · ") : t("anyCase"), action: d.join(" ") };
}
