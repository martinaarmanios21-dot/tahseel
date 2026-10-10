import { Fragment, type ReactNode } from "react";

/**
 * Tiny markdown renderer for agent replies: headings, bullets, bold, tables, rules, quotes.
 * Builds React elements only (no innerHTML), so text from imported files can never inject markup.
 */
export function Md({ text }: { text: string }) {
  const lines: string[] = text.replace(/\r/g, "").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  const inline = (s: string, k: string) => <Inline key={k} s={s} />;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    if (/^\s*\|.*\|\s*$/.test(line)) {
      const rows: string[][] = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i] ?? "")) {
        const cells = (lines[i] ?? "").trim().slice(1, -1).split("|").map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i++;
      }
      out.push(
        <div key={`t${i}`} className="my-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr>{rows[0]?.map((c, j) => <th key={j} className="border-b px-2 py-1 text-start font-semibold">{inline(c, `h${j}`)}</th>)}</tr></thead>
            <tbody>{rows.slice(1).map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j} className="border-b px-2 py-1 align-top">{inline(c, `c${j}`)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*([-*•]|\d+\.)\s+/.test(line)) {
      const items: { depth: number; s: string }[] = [];
      while (i < lines.length && /^\s*([-*•]|\d+\.)\s+/.test(lines[i] ?? "")) {
        const m = (lines[i] ?? "").match(/^(\s*)([-*•]|\d+\.)\s+(.*)$/);
        items.push({ depth: (m?.[1]?.length ?? 0) >= 2 ? 1 : 0, s: m?.[3] ?? "" });
        i++;
      }
      out.push(<ul key={`u${i}`} className="my-1.5 grid gap-1">{items.map((it, j) => (
        <li key={j} className={it.depth ? "ms-6 list-[circle]" : "ms-5 list-disc"}>{inline(it.s, `l${j}`)}</li>
      ))}</ul>);
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) out.push(<div key={i} className="mt-3 mb-1 font-bold">{inline(h[2] ?? "", `h${i}`)}</div>);
    else if (/^\s*-{3,}\s*$/.test(line)) out.push(<hr key={i} className="my-3" />);
    else if (line.startsWith(">")) out.push(<blockquote key={i} className="border-s-4 border-primary/30 ps-3 text-muted-foreground">{inline(line.replace(/^>\s?/, ""), `q${i}`)}</blockquote>);
    else if (line.trim() === "") out.push(<div key={i} className="h-2" />);
    else out.push(<p key={i} className="leading-relaxed">{inline(line, `p${i}`)}</p>);
    i++;
  }
  return <div className="text-[0.95rem]">{out}</div>;
}

function Inline({ s }: { s: string }) {
  const parts = s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
        if (p.startsWith("`") && p.endsWith("`")) return <code key={i} className="rounded bg-muted px-1">{p.slice(1, -1)}</code>;
        return <Fragment key={i}>{p.replace(/\*([^*]+)\*/g, "$1")}</Fragment>;
      })}
    </>
  );
}

