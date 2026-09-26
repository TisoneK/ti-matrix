/* Small formatters shared by every view. No world knowledge lives here. */

export const pct = (v: unknown): string => `${Math.round(Number(v ?? 0) * 100)}%`;

export function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
}

/** A token total, compacted the way a person reads it back: 847, 1.2k, 34k — never a bare five-digit run. */
export function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 10_000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** The engine truncates observations; the tail marker it leaves is worth showing as a marker, not as text. */
export const TRUNCATION = /… ?\(truncated\)$/;

export function splitTruncation(text: string): { body: string; truncated: boolean } {
  const body = text.replace(/\n?… ?\(truncated\)$/, "");
  return { body, truncated: body !== text };
}

/** A path shortened for display, keeping the end that identifies it. */
export function shortPath(path: string, keep = 42): string {
  if (path.length <= keep) return path;
  const parts = path.split("/");
  let out = parts[parts.length - 1];
  for (let i = parts.length - 2; i >= 0; i--) {
    const next = `${parts[i]}/${out}`;
    if (next.length > keep) return `…/${out}`;
    out = next;
  }
  return out;
}

/* ── how a run ended, in words ──────────────────────────────────────────── */

/**
 * The engine stops for four reasons and names them for itself: `budget`, `no_moves`, `no_progress`,
 * and `stopped` when a person asked. Those are event vocabulary (ADR-3) and they were reaching the
 * screen raw — the library's "ended" column and the compare scorecard both printed `no_progress`.
 *
 * One map, so the same ending reads the same wherever it is shown.
 */
export function outcomeLabel(settled: boolean, reason: string | null): string {
  if (settled) return "settled";
  const r = (reason ?? "").trim();
  if (r === "") return "unsettled";
  if (r.startsWith("error:")) return "failed";
  const plain: Record<string, string> = {
    budget: "out of budget",
    no_moves: "nothing left to try",
    no_progress: "nothing improved",
    stopped: "stopped by you",
  };
  return plain[r] ?? r;
}

/** Green when it answered, amber when it gave up, red when it broke. Drives the lamp and the badges. */
export function outcomeTone(settled: boolean, reason: string | null): "ok" | "warn" | "bad" {
  if (settled) return "ok";
  return (reason ?? "").trim().startsWith("error:") ? "bad" : "warn";
}
