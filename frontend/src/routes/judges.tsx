import { createFileRoute } from "@tanstack/react-router";
import { Logo } from "@/components/Logo";
import { useApp } from "@/lib/app-context";

export const Route = createFileRoute("/judges")({
  head: () => ({
    meta: [
      { title: "Technical details — Tahseel" },
      { name: "description", content: "How Tahseel's collections assistant works: API, safety rules and approval-gated learning." },
      { property: "og:title", content: "Technical details — Tahseel" },
      { property: "og:description", content: "Architecture and safety details for judges." },
    ],
  }),
  component: Judges,
});

const endpoints = [
  "GET /api/summary?business=", "GET /api/decisions", "POST /api/approvals/{id}/approve | /reject",
  "GET /api/customers", "GET /api/customers/{id}", "GET /api/insights", "POST /api/skills/{v}/promote",
  "POST /api/kill {on}", "POST /api/workspace/new", "POST /api/workspace/next-round",
  "POST /api/train {episodes:2}", "POST /api/learn", "GET /api/job (polled every 1.5s)",
];

function Judges() {
  const { t } = useApp();
  return (
    <main className="mx-auto max-w-3xl px-4 py-10" dir="ltr">
      <Logo />
      <h1 className="mt-6 text-3xl font-bold">{t("judgesTitle")}</h1>
      <div className="card-soft mt-6 grid gap-3 p-6 text-start leading-relaxed">
        <p><b>Human-in-the-loop:</b> key accounts, amounts over EGP 100,000 and payment plans beyond the allowed installments are queued as decisions for staff approval.</p>
        <p><b>Safety:</b> no threats, no discounts, disputes are escalated, prompt-injection replies are flagged as suspicious and blocked. A global kill switch stops all sending.</p>
        <p><b>Learning:</b> the assistant proposes new rule versions from outcomes; each candidate is evaluated against collection rate, complaints and a safety test suite, and is only promoted after owner approval.</p>
        <p><b>Frontend:</b> all data goes through a single API client using same-origin <code>/api/…</code>; if unreachable it falls back to local mock data and shows a "Demo data" badge.</p>
      </div>
      <h2 className="mt-8 mb-3 text-xl font-bold">Endpoints</h2>
      <ul className="card-soft divide-y font-mono text-sm">
        {endpoints.map((e) => <li key={e} className="px-4 py-2.5">{e}</li>)}
      </ul>
    </main>
  );
}
