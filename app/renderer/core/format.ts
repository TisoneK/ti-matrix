/* Small formatters shared by every view. No world knowledge lives here. */

export const pct = (v: unknown): string => `${Math.round(Number(v ?? 0) * 100)}%`;

export function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
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
