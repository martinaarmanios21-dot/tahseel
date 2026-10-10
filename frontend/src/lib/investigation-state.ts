/* eslint-disable @typescript-eslint/no-explicit-any */
/* Where an investigation stands, computed from its state (GET /api/investigations/:id). Shared by the investigation
   page and the assistant so both always show the same stage and the same next step. */
import type { Question } from "./tapi";

export function steps(s: any) {
  const profileDone = ["p_worry", "p_sells", "p_channels"].some((k) => s.answers?.[k]) || !!s.record_counts?.sales;
  const uploaded = !!s.record_counts?.sales;
  const leakSeen = !!s.diagnosis?.comparable && !s.diagnosis?.gaps?.length;
  const fixing = !!(s.outreach?.length || s.scenarios?.length || s.interventions?.length);
  const checked = (s.interventions ?? []).some((x: any) => ["verified_improvement", "no_measurable_improvement", "inconclusive"].includes(x.status));
  const done = [profileDone, uploaded, leakSeen, fixing, checked];
  const current = done.findIndex((d) => !d);
  return { done, current: current === -1 ? 4 : current };
}

/** The single thing the "Do this now" card shows: the first open question, else the first non-document action. */
export function nextStep(s: any): { question?: Question; action?: any } {
  const question: Question | undefined = s.questions?.[0];
  if (question) return { question };
  const action = (s.actions ?? []).find((a: any) => a.kind !== "document");
  return action ? { action } : {};
}

/** Not enough data to compare two months yet (and no missing-month question pending): only then show general ideas. */
export function needsGeneralIdeas(s: any): boolean {
  const d = s.diagnosis;
  return !!s.record_counts?.sales && !d?.comparable && !d?.gaps?.length;
}
