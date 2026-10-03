export type Status = "needs_you" | "waiting" | "in_progress" | "paid" | "paid_by_plan" | "with_team" | "suspicious";
export const STATUSES: Status[] = ["needs_you", "waiting", "in_progress", "paid", "paid_by_plan", "with_team", "suspicious"];

export interface Business { id: string; name_ar: string; name_en: string; customers: number; collected_egp: number; outstanding_egp: number }
export interface Summary {
  workspace: { run_id: string; round: number; status: string } | null;
  assistant: { paused: boolean; skill_version: string; busy: boolean };
  money: { collected_egp: number; outstanding_egp: number; with_team_egp: number; total_egp: number };
  customers_by_status: Record<Status, number>;
  needs_your_decision: number;
  businesses: Business[];
  learning: { first_collection_rate: number | null; current_collection_rate: number | null; first_complaints: number | null; current_complaints: number | null; update_waiting_for_approval: number | null; candidate_collection_rate?: number | null; candidate_complaints?: number | null };
}
export interface Decision {
  decision_id: string; invoice_id: string; customer: string; contact_name: string; language: "ar" | "en";
  business: string; amount_egp: number; days_overdue: number; tier: "key" | "standard"; action: string; tone: string;
  installments: number; message: string; why_code: string; last_reply: string;
}
export interface TimelineItem { action: string; status: string; tone: string; message: string }
export interface Customer {
  invoice_id: string; customer: string; language: "ar" | "en"; business: string; tier: "key" | "standard";
  amount_egp: number; days_overdue: number; status: Status; times_contacted: number; last_reply: string; reply_type: string;
  timeline?: TimelineItem[];
}
export interface Rule {
  when: { signal?: string; tier?: string; history?: string; touch?: string };
  do: { action: string; tone?: string; include_payment_link?: boolean; mention_due_date?: boolean; installments?: number };
}
export interface Metrics { collection_rate: number; complaints: number; safety_tests_passed: number; safety_tests_total: number }
export interface Insights {
  active: { version: string; rules: Rule[] };
  waiting_for_approval: { version: string; status: string; rules: Rule[]; test_results: { passed: boolean; reasons: string[]; before: Metrics; after: Metrics } } | null;
  history: { version: string; status: string }[];
}
