/* All visible text. Arabic = natural, professional Egyptian Arabic (العامية المصرية). */
export const ar = {
  appName: "ربحية",
  role: "متخصصة الربحية وتسريب التكاليف",
  language: "اللغة",
  theme: "المظهر",
  killOn: "الإيقاف الطارئ شغال: مفيش أي إجراء خارجي",
  pause: "إيقاف طارئ",
  resume: "إلغاء الإيقاف",
  confirmPause: "توقف كل الإجراءات الخارجية (الإرسال) فوراً؟",
  confirmResume: "ترجّع الإرسال تاني (لسه كل رسالة محتاجة موافقتك)؟",
  yes: "أيوه",
  cancel: "إلغاء",
  loading: "بنحمّل…",
  retry: "حاول تاني",
  loadError: "حصلت مشكلة في التحميل",
  serverDown: "السيرفر مش شغال. شغّل: uv run revenue-agent serve",
  tokenNeeded: "العملية دي محتاجة كلمة سر الإدارة (ADMIN_TOKEN)",
  tokenPrompt: "اكتب كلمة سر الإدارة:",
  enterToken: "ادخل كلمة سر الإدارة",
  blockedTitle: "مش هينفع تتبعت دلوقتي:",
} as const;

export type Dict = { [K in keyof typeof ar]: string };

export const en: Dict = {
  appName: "Ribhiya",
  role: "Profitability & cost-leakage specialist",
  language: "Language",
  theme: "Theme",
  killOn: "Emergency stop is on: no external actions",
  pause: "Emergency stop",
  resume: "Resume",
  confirmPause: "Stop all external actions (sending) now?",
  confirmResume: "Allow sending again (every message still needs your approval)?",
  yes: "Yes",
  cancel: "Cancel",
  loading: "Loading…",
  retry: "Retry",
  loadError: "Something went wrong while loading",
  serverDown: "The server is not running. Start it with: uv run revenue-agent serve",
  tokenNeeded: "This action needs the admin token (ADMIN_TOKEN)",
  tokenPrompt: "Enter the admin token:",
  enterToken: "Enter admin token",
  blockedTitle: "Cannot be sent right now:",
};

/* Policy block codes -> plain language. Backend reason (English) is the fallback. */
export const BLOCKS: Record<string, { ar: string; en: string }> = {
  kill_switch: { ar: "الإيقاف الطارئ شغال", en: "Emergency stop is on" },
  disputed: { ar: "الفاتورة عليها اعتراض", en: "Invoice is disputed" },
  no_recipient: { ar: "مفيش إيميل متسجّل للعميل", en: "No email on record" },
  email_not_configured: { ar: "الإرسال من البرنامج مش متوصّل", en: "Email sending is not configured" },
  subject: { ar: "الموضوع فاضي أو طويل جداً", en: "Subject empty or too long" },
  approval_mismatch: { ar: "النص اتغيّر بعد الموافقة", en: "Content changed after approval" },
  not_approved: { ar: "الرسالة محتاجة موافقة الأول (أو اتبعتت خلاص)", en: "Not approved (or already sent)" },
  send_failed: { ar: "الإرسال فشل", en: "Send failed" },
};

