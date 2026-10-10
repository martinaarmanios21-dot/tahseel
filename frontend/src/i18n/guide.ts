import { useApp } from "@/lib/app-context";

const G: Record<string, { ar: string; en: string }> = {
  open: { ar: "اتكلم مع ربحية", en: "Chat with Ribhiya" },
  close: { ar: "اقفل", en: "Close" },
  title: { ar: "ربحية", en: "Ribhiya" },
  sub: { ar: "مساعدتك في التطبيق والبيزنس", en: "Your guide to the app and to business" },
  t_chat: { ar: "اسأل", en: "Ask" }, t_tour: { ar: "جولة", en: "Tour" }, t_learn: { ar: "اتعلّم", en: "Learn" },
  t_feedback: { ar: "رأيك", en: "Feedback" },
  hello: { ar: "أهلاً! أنا ربحية. اسألني إزاي تستخدم التطبيق، أو عن أي مفهوم في البيزنس.", en: "Hi! I'm Ribhiya. Ask me how to use the app, or about any business concept." },
  placeholder: { ar: "اكتب سؤالك…", en: "Type your question…" },
  send: { ar: "ابعت", en: "Send" },
  thinking: { ar: "بفكّر…", en: "Thinking…" },
  clear: { ar: "محادثة جديدة", en: "New chat" },
  aiNote: { ar: "إجابة بالذكاء الاصطناعي من غير بياناتك", en: "AI answer, without your data" },
  showMe: { ar: "وريني", en: "Show me" },
  tourIntro: { ar: "اختار جزء وأنا أشرحه في خطوات.", en: "Pick a part and I'll explain it in steps." },
  learnIntro: { ar: "أهم مفاهيم البيزنس، بأمثلة بسيطة.", en: "Key business concepts, with simple examples." },
  example: { ar: "مثال", en: "Example" },
  seeInApp: { ar: "شوفه في ربحية", en: "See it in Ribhiya" },
  watch: { ar: "اتعلّم أكتر:", en: "Learn more:" },



  fb_kind: { ar: "عايز تقول إيه؟", en: "What would you like to share?" },
  fb_review: { ar: "تقييم", en: "Review" }, fb_idea: { ar: "فكرة ميزة", en: "Feature idea" }, fb_bug: { ar: "مشكلة", en: "Problem" },
  fb_rating: { ar: "تقييمك", en: "Your rating" },
  fb_text_review: { ar: "إيه اللي عجبك أو ما عجبكش؟", en: "What did you like or not like?" },
  fb_text_idea: { ar: "إيه الميزة اللي نفسك فيها؟", en: "What feature would you like?" },
  fb_text_bug: { ar: "إيه اللي حصل؟ وكنت في أنهي صفحة؟", en: "What happened, and on which page?" },
  fb_send: { ar: "ابعت رأيك", en: "Send feedback" },
  fb_thanks: { ar: "شكراً! اتحفظ.", en: "Thank you! Saved." },
  fb_where: { ar: "بيتحفظ مع بياناتك على الجهاز ده بس، ومش بيتبعت لأي حد.", en: "Saved with your data on this machine only; it isn't sent anywhere." },
  fb_mine: { ar: "اللي بعته قبل كده", en: "What you sent before" },
  helloInv: { ar: "أنا شايفة تحقيقك. اسألني عن أرقامك، أو أعمل إيه دلوقتي.", en: "I can see your investigation. Ask me about your numbers, or what to do next." },
  placeholderInv: { ar: "اسأل عن أرقامك أو عن أي خطوة…", en: "Ask about your numbers or any step…" },
  q_next: { ar: "أعمل إيه دلوقتي؟", en: "What should I do now?" },
  q_why: { ar: "ليه ربحي قلّ؟", en: "Why is my profit down?" },
  q_fix: { ar: "أعمل إيه عشان أصلّحها؟", en: "What can I do about it?" },
  q_missing: { ar: "إيه الملفات الناقصة؟", en: "What files are missing?" },
  q_whyNeeded: { ar: "محتاج ده ليه؟", en: "Why do you need this?" },
  q_whatif: { ar: "إزاي أجرّب «لو غيّرت»؟", en: "How do I try a what-if?" },
  stepOf: { ar: "خطوة {n} من ٥", en: "Step {n} of 5" },
  nextIs: { ar: "الجاي:", en: "Next:" },
  continue: { ar: "كمّل:", en: "Continue:" },
  openInv: { ar: "افتح", en: "Open" },
  startHint: { ar: "ابدأ باسم نشاطك وأنا أمشي معاك خطوة خطوة.", en: "Start with your business name and I'll guide you step by step." },
  src_state: { ar: "من حالة تحقيقك (نفس كارت «اعمل ده دلوقتي»)", en: "From this investigation's status (same as “Do this now”)" },
  src_numbers_rules: { ar: "من حسابات تحقيقك مباشرة", en: "Straight from this investigation's calculations" },
  src_numbers_api: { ar: "صياغة بالذكاء الاصطناعي، والأرقام متراجعة على حساباتك", en: "Worded by AI; figures checked against your calculations" },
  src_numbers_hermes: { ar: "رد من Hermes، والأرقام متراجعة على حساباتك", en: "Answered by Hermes; figures checked against your calculations" },
  noInv: { ar: "ابدأ تحقيق الأول، وبعدين أوريك.", en: "Start an investigation first, then I'll show you." },
};

export function useGT() {
  const { lang } = useApp();
  return (k: string) => G[k]?.[lang] ?? k;
}
