import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ChevronDown, Compass, ExternalLink, MapPin, MessageCircle, MessageSquareHeart, RotateCcw, Send, Star, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useGT } from "@/i18n/guide";
import { useApp } from "@/lib/app-context";
import { gapi, papi, type GuideAction, type GuideGo, type GuideReply } from "@/lib/tapi";
import { nextStep, steps } from "@/lib/investigation-state";
import { useIT } from "./charts";
import { cn } from "@/lib/utils";
import { LogoMark } from "./Logo";
import { Md } from "./Md";
import { useErrorToast } from "./bits";

type Panel = "chat" | "tour" | "learn" | "feedback";
const PANELS: Panel[] = ["chat", "tour", "learn", "feedback"];
type Msg = { role: "user" | "assistant"; text: string; reply?: GuideReply };
const KEY = "ribhiya.guide.chat";
export const PENDING_GO = "ribhiya.guide.pendingGo";

/** The investigation open on this page (if any) and its state. Uses the page's own query, so it's the same data. */
function useInvContext() {
  const { lang } = useApp();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const iid = path.startsWith("/investigation/") ? decodeURIComponent(path.split("/")[2] ?? "") : undefined;
  const st = useQuery({ queryKey: ["inv", iid, lang], queryFn: () => papi.state(iid!, lang), enabled: !!iid, retry: false });
  return { iid, s: st.data as any };
}

/** Take the owner to a feature: a page, a tab on the investigation page, or a card on it. */
function useGoTo() {
  const nav = useNavigate();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const gt = useGT();
  return async (go: GuideGo) => {
    if (!go) return;
    if (go.route) { nav({ to: go.route as "/" }); return; }
    if (path.startsWith("/investigation/")) { window.dispatchEvent(new CustomEvent("ribhiya:go", { detail: go })); return; }
    const list = await papi.list().catch(() => []);
    const latest = list[0];
    if (!latest) { nav({ to: "/" }); toast(gt("noInv")); return; }
    sessionStorage.setItem(PENDING_GO, JSON.stringify(go));
    nav({ to: "/investigation/$id", params: { id: latest.id } });
  };
}

export function GuideChat() {
  const gt = useGT();
  // remembered for the session, so the panel stays open when "Show me" moves to another page
  const [open, setOpenS] = useState(() => typeof sessionStorage !== "undefined" && sessionStorage.getItem("ribhiya.guide.open") === "1");
  const [panel, setPanelS] = useState<Panel>(() => {
    const p = (typeof sessionStorage !== "undefined" && sessionStorage.getItem("ribhiya.guide.panel")) as Panel;
    return PANELS.includes(p) ? p : "chat";
  });
  const setOpen = (v: boolean) => { setOpenS(v); sessionStorage.setItem("ribhiya.guide.open", v ? "1" : "0"); };
  const setPanel = (p: Panel) => { setPanelS(p); sessionStorage.setItem("ribhiya.guide.panel", p); };
  // "Ask Ribhiya about this" on the page: open the chat and ask
  const [pending, setPending] = useState<{ text: string; n: number } | null>(null);
  useEffect(() => {
    const h = (e: Event) => { setOpen(true); setPanel("chat"); setPending({ text: (e as CustomEvent).detail?.text ?? "", n: Date.now() }); };
    window.addEventListener("ribhiya:ask", h);
    return () => window.removeEventListener("ribhiya:ask", h);
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  const tabs: [Panel, typeof Compass][] = [["chat", MessageCircle], ["tour", Compass], ["learn", BookOpen], ["feedback", MessageSquareHeart]];
  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="fixed bottom-4 end-4 z-50 flex items-center gap-2 rounded-full border bg-card py-1.5 pe-4 ps-1.5 font-semibold shadow-lg hover:border-primary">
        <LogoMark size={34} /> {gt("open")}
      </button>
    );
  }
  return (
    <section role="dialog" aria-label={gt("open")} className="fixed bottom-4 end-4 z-50 flex h-[min(640px,calc(100vh-2rem))] w-[min(420px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border bg-card shadow-2xl">
      <header className="flex items-center gap-2 border-b px-3 py-2">
        <LogoMark size={32} />
        <div className="flex-1 leading-tight"><div className="font-bold">{gt("title")}</div><div className="text-xs text-muted-foreground">{gt("sub")}</div></div>
        <button onClick={() => setOpen(false)} aria-label={gt("close")} className="rounded-lg p-1.5 hover:bg-muted"><X className="size-5" /></button>
      </header>
      <nav className="grid grid-cols-4 border-b text-xs" role="tablist">
        {tabs.map(([k, Icon]) => (
          <button key={k} role="tab" aria-selected={panel === k} onClick={() => setPanel(k)}
            className={cn("flex flex-col items-center gap-0.5 py-2", panel === k ? "border-b-2 border-primary font-bold text-primary" : "text-muted-foreground hover:text-foreground")}>
            <Icon className="size-4" /> {gt(`t_${k}`)}
          </button>
        ))}
      </nav>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {panel === "chat" && <Chat setPanel={setPanel} pending={pending} />}
        {panel === "tour" && <Tour />}
        {panel === "learn" && <Learn />}
        {panel === "feedback" && <Feedback />}
      </div>
    </section>
  );
}

function useContent() {
  const { lang } = useApp();
  return useQuery({ queryKey: ["guide", lang], queryFn: () => gapi.content(lang), staleTime: Infinity });
}

function Actions({ actions, setPanel }: { actions: GuideAction[]; setPanel: (p: Panel) => void }) {
  const goTo = useGoTo();
  if (!actions.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {actions.map((a, i) => (
        <button key={i} className="rounded-full border border-primary/40 px-3 py-1 text-xs font-semibold text-primary hover:bg-primary-soft"
          onClick={() => a.type === "panel" ? setPanel(a.panel as Panel) : goTo(a.go)}>{a.label}</button>
      ))}
    </div>
  );
}

function Links({ links }: { links: { kind: string; label: string; url: string }[] }) {
  const gt = useGT();
  if (!links.length) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
      <span className="text-muted-foreground">{gt("watch")}</span>
      {links.map((l) => (
        <a key={l.url} href={l.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 hover:text-primary">
          {l.label} <ExternalLink className="size-3" />
        </a>
      ))}
    </div>
  );
}

function Chat({ setPanel, pending }: { setPanel: (p: Panel) => void; pending: { text: string; n: number } | null }) {
  const gt = useGT();
  const { lang } = useApp();
  const content = useContent();
  const onErr = useErrorToast();
  const { iid, s } = useInvContext();
  const key = `${KEY}.${iid ?? "home"}`;  // each investigation keeps its own conversation
  const load = () => { try { return JSON.parse(sessionStorage.getItem(key) ?? "[]") as Msg[]; } catch { return []; } };
  const [msgs, setMsgs] = useState<Msg[]>(load);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { setMsgs(load()); }, [key]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { sessionStorage.setItem(key, JSON.stringify(msgs.slice(-30))); end.current?.scrollIntoView({ block: "end" }); }, [msgs, busy, key]);
  const send = async (q: string) => {
    q = q.trim();
    if (!q || busy) return;
    const before = load();
    const next: Msg[] = [...before, { role: "user", text: q }];
    setMsgs(next); setText(""); setBusy(true);
    try {
      const r = await gapi.ask(q, lang, next.slice(-7, -1).map((m) => ({ role: m.role, text: m.text })), iid);
      setMsgs([...next, { role: "assistant", text: r.answer, reply: r }]);
    } catch (e) { onErr(e); setMsgs(before); setText(q); } finally { setBusy(false); }
  };
  useEffect(() => { if (pending?.text) send(pending.text); }, [pending?.n]);  // eslint-disable-line react-hooks/exhaustive-deps
  const chips: string[] = iid ? contextChips(s, gt) : (content.data?.quick ?? []);
  return (
    <div className="flex min-h-full flex-col">
      <ContextStrip iid={iid} s={s} />
      <div className="flex-1 space-y-3 p-3">
        <Bubble role="assistant"><p>{iid ? gt("helloInv") : gt("hello")}</p></Bubble>
        {!msgs.length && (
          <div className="flex flex-wrap gap-1.5">
            {chips.map((q) => (
              <button key={q} onClick={() => send(q)} className="rounded-full border px-3 py-1.5 text-sm hover:border-primary hover:text-primary">{q}</button>
            ))}
          </div>
        )}
        {msgs.map((m, i) => (
          <Bubble key={i} role={m.role}>
            {m.role === "assistant" ? <Md text={m.text} /> : <p className="whitespace-pre-wrap">{m.text}</p>}
            {m.reply && <Actions actions={m.reply.actions} setPanel={setPanel} />}
            {m.reply && <Links links={m.reply.links} />}
            {m.reply && <SourceNote r={m.reply} />}
          </Bubble>
        ))}
        {busy && <Bubble role="assistant"><p className="text-muted-foreground">{gt("thinking")}</p></Bubble>}
        <div ref={end} />
      </div>
      <form className="sticky bottom-0 flex items-center gap-2 border-t bg-card p-2" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        {!!msgs.length && <button type="button" onClick={() => setMsgs([])} title={gt("clear")} aria-label={gt("clear")} className="rounded-lg p-2 text-muted-foreground hover:bg-muted"><RotateCcw className="size-4" /></button>}
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} placeholder={iid ? gt("placeholderInv") : gt("placeholder")} className="min-w-0 flex-1 rounded-lg border bg-background px-3 py-2 text-sm" />
        <button disabled={busy || !text.trim()} aria-label={gt("send")} className="btn btn-primary !p-2"><Send className="size-4 rtl:-scale-x-100" /></button>
      </form>
    </div>
  );
}

/** Starter questions that fit where the investigation is. */
function contextChips(s: any, gt: (k: string) => string): string[] {
  if (!s) return [gt("q_next")];
  const findings = !!s.diagnosis?.comparable && !!s.diagnosis?.findings?.length && !s.diagnosis?.gaps?.length;
  if (findings) return [gt("q_why"), gt("q_fix"), gt("q_next"), gt("q_missing")];
  if (s.questions?.length) return [gt("q_next"), gt("q_whyNeeded"), gt("q_missing")];
  return [gt("q_next"), gt("q_missing"), gt("q_whatif")];
}

/** Where you are: the investigation, its step, and the one next thing (the same as the "Do this now" card). */
function ContextStrip({ iid, s }: { iid?: string | undefined; s: any }) {
  const gt = useGT();
  const it = useIT();
  const { lang } = useApp();
  const goTo = useGoTo();
  const nav = useNavigate();
  const list = useQuery({ queryKey: ["investigations"], queryFn: papi.list, enabled: !iid, retry: false });
  if (!iid) {
    const latest = list.data?.[0];
    return (
      <div className="sticky top-0 z-10 flex items-center gap-2 border-b bg-muted px-3 py-2 text-xs">
        <MapPin className="size-3.5 shrink-0 text-primary" />
        {latest
          ? <><span className="flex-1 truncate">{gt("continue")} <b>{latest.title}</b></span>
              <button className="font-semibold text-primary underline" onClick={() => nav({ to: "/investigation/$id", params: { id: latest.id } })}>{gt("openInv")}</button></>
          : <span className="flex-1">{gt("startHint")}</span>}
      </div>
    );
  }
  if (!s) return null;
  const st = steps(s);
  const { question, action } = nextStep(s);
  const next = question ? question.text[lang] : action ? it(`do_${action.kind}`) : it("allDone");
  return (
    <div className="sticky top-0 z-10 border-b bg-muted px-3 py-2 text-xs">
      <div className="flex items-center gap-1.5 font-semibold"><MapPin className="size-3.5 shrink-0 text-primary" /><span className="truncate">{s.investigation.title}</span>
        <span className="ms-auto shrink-0 font-normal text-muted-foreground">{gt("stepOf").replace("{n}", String(st.current + 1))} · {it(`step${st.current + 1}`)}</span></div>
      <div className="mt-1 flex items-center gap-2"><span className="flex-1 truncate text-muted-foreground">{gt("nextIs")} {next}</span>
        <button className="shrink-0 font-semibold text-primary underline" onClick={() => goTo({ anchor: "do-now" })}>{gt("showMe")}</button></div>
    </div>
  );
}

/** Where an answer came from, so the owner can judge it. */
function SourceNote({ r }: { r: GuideReply }) {
  const gt = useGT();
  const key = r.source === "your_numbers" ? `src_numbers_${r.engine ?? "rules"}` : r.source === "help_ai" ? "aiNote" : r.source === "state" ? "src_state" : null;
  if (!key) return null;
  return <p className="mt-1 text-[11px] text-muted-foreground">{gt(key)}</p>;
}

function Bubble({ role, children }: { role: "user" | "assistant"; children: React.ReactNode }) {
  return (
    <div className={cn("max-w-[90%] rounded-2xl px-3 py-2 text-sm", role === "user" ? "ms-auto bg-primary text-primary-foreground" : "bg-muted/60")}>{children}</div>
  );
}

function Tour() {
  const gt = useGT();
  const content = useContent();
  const goTo = useGoTo();
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="grid gap-2 p-3">
      <p className="text-sm text-muted-foreground">{gt("tourIntro")}</p>
      {(content.data?.features ?? []).map((f: any, i: number) => (
        <div key={f.id} className="rounded-xl border">
          <button onClick={() => setOpen(open === f.id ? null : f.id)} className="flex w-full items-center gap-2 p-3 text-start">
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary-soft text-xs font-bold text-primary">{i + 1}</span>
            <span className="flex-1 font-semibold">{f.title}</span>
            <ChevronDown className={cn("size-4 transition", open === f.id && "rotate-180")} />
          </button>
          {open === f.id && (
            <div className="border-t px-3 pb-3 pt-2 text-sm">
              <p className="mb-2">{f.what}</p>
              <ol className="list-decimal space-y-1 ps-5 text-muted-foreground">{f.steps.map((s: string) => <li key={s}>{s}</li>)}</ol>
              {f.go && <button onClick={() => goTo(f.go)} className="btn btn-primary mt-3 !py-1.5 text-sm">{gt("showMe")}</button>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Learn() {
  const gt = useGT();
  const content = useContent();
  const goTo = useGoTo();
  const [open, setOpen] = useState<string | null>(null);
  const features = Object.fromEntries((content.data?.features ?? []).map((f: any) => [f.id, f]));
  return (
    <div className="grid gap-2 p-3">
      <p className="text-sm text-muted-foreground">{gt("learnIntro")}</p>
      {(content.data?.concepts ?? []).map((c: any) => (
        <div key={c.id} className="rounded-xl border">
          <button onClick={() => setOpen(open === c.id ? null : c.id)} className="flex w-full items-start gap-2 p-3 text-start">
            <span className="flex-1"><span className="block font-semibold">{c.title}</span><span className="block text-sm text-muted-foreground">{c.simple}</span></span>
            <ChevronDown className={cn("mt-1 size-4 shrink-0 transition", open === c.id && "rotate-180")} />
          </button>
          {open === c.id && (
            <div className="space-y-2 border-t px-3 pb-3 pt-2 text-sm">
              <p className="rounded-lg bg-primary-soft p-2">{c.example}</p>
              <p>{c.why}</p>
              {features[c.feature]?.go && <button onClick={() => goTo(features[c.feature].go)} className="text-sm font-semibold text-primary underline">{gt("seeInApp")}</button>}
              <Links links={c.links} />
            </div>
          )}
        </div>
      ))}
      {content.data?.links_note && <p className="text-xs text-muted-foreground">{content.data.links_note}</p>}
    </div>
  );
}

function Feedback() {
  const gt = useGT();
  const { lang } = useApp();
  const qc = useQueryClient();
  const onErr = useErrorToast();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const [kind, setKind] = useState<"review" | "idea" | "bug">("review");
  const [rating, setRating] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const mine = useQuery({ queryKey: ["guide-feedback"], queryFn: gapi.myFeedback });
  const send = async () => {
    setBusy(true);
    try {
      await gapi.feedback({ kind, rating: kind === "review" ? rating : null, text, page: path, lang });
      toast.success(gt("fb_thanks")); setText(""); setRating(null);
      qc.invalidateQueries({ queryKey: ["guide-feedback"] });
    } catch (e) { onErr(e); } finally { setBusy(false); }
  };
  return (
    <div className="grid gap-3 p-3 text-sm">
      <div className="font-semibold">{gt("fb_kind")}</div>
      <div className="grid grid-cols-3 gap-1.5">
        {(["review", "idea", "bug"] as const).map((k) => (
          <button key={k} onClick={() => setKind(k)} className={cn("rounded-lg border py-2", kind === k ? "border-primary bg-primary-soft font-semibold text-primary" : "hover:border-primary/50")}>{gt(`fb_${k}`)}</button>
        ))}
      </div>
      {kind === "review" && (
        <div className="flex items-center gap-1" aria-label={gt("fb_rating")}>
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} onClick={() => setRating(n)} aria-label={`${n}`} className="p-0.5">
              <Star className={cn("size-6", rating && n <= rating ? "fill-amber-400 text-amber-400" : "text-muted-foreground")} />
            </button>
          ))}
        </div>
      )}
      <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} rows={4} placeholder={gt(`fb_text_${kind}`)} className="rounded-lg border bg-background p-2" />
      <button onClick={send} disabled={busy || (!text.trim() && !(kind === "review" && rating))} className="btn btn-primary w-fit !py-2">{gt("fb_send")}</button>
      <p className="text-xs text-muted-foreground">{gt("fb_where")}</p>
      {!!mine.data?.length && (
        <div className="border-t pt-2">
          <div className="mb-1 text-xs font-semibold text-muted-foreground">{gt("fb_mine")}</div>
          <ul className="space-y-1">
            {mine.data.slice(0, 5).map((f) => (
              <li key={f.id} className="rounded-lg bg-muted/50 p-2 text-xs">
                <span className="font-semibold">{gt(`fb_${f.kind}`)}</span>{f.rating ? ` · ${"★".repeat(f.rating)}` : ""}{f.text ? ` · ${f.text}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
