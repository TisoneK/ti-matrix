/*
 * The API key at rest, as the renderer sees it.
 *
 * Until now a key lived for exactly one session: pasted into the sheet, held in renderer memory, sent
 * with the run config, and gone when the window closed — which meant pasting it again on every launch.
 * The annoyance is real, so the key can now be remembered; the line that does *not* move is where it is
 * kept. It never enters `settings.json` (see `settings.ts`, whose `stripKeyish` still strips it and whose
 * serialisation never sees it), it is never written in the clear anywhere, and it is never part of a
 * saved run. Main owns the file and encrypts with the OS's own protection (`safeStorage`); this module
 * only asks for it back, and refuses to hand it over for a different endpoint than the one it was
 * entered for.
 *
 * In a plain browser tab `window.tm` is absent, so every function here is a no-op and the app behaves
 * exactly as it did before: the key lives in renderer memory for the session.
 */

interface KeyBridge {
  keyLoad?: () => Promise<{ base_url: string; key: string } | null>;
  keySave?: (value: { base_url: string; api_key: string }) => Promise<boolean>;
  keyClear?: () => Promise<boolean>;
}

const bridge = (): KeyBridge | undefined => (window as unknown as { tm?: KeyBridge }).tm;

/**
 * Whether two endpoints are the same place to send a key.
 *
 * Hosts are case-insensitive by standard and a trailing slash is not a different address, so those are
 * normalised away; a path is *not* case-insensitive, so it is compared as written. The empty endpoint is
 * never "the same" as anything, which is what keeps a remembered key from being applied while the
 * endpoint field is blank or half-typed.
 */
export function sameEndpoint(a: string, b: string): boolean {
  const norm = (raw: string): string => {
    const trimmed = raw.trim().replace(/\/+$/, "");
    if (!trimmed) return "";
    try {
      const u = new URL(trimmed);
      return `${u.protocol}//${u.host}${u.pathname}`.replace(/\/+$/, "");
    } catch {
      return trimmed; // not a URL yet — it still has to compare equal to itself
    }
  };
  const left = norm(a);
  return left !== "" && left === norm(b);
}

/** True when this window can remember a key at all (the desktop app, not a browser tab). */
export const canRememberKey = (): boolean => typeof bridge()?.keyLoad === "function";

/**
 * The remembered key for this endpoint, or `""`.
 *
 * Three things return empty, and all three are ordinary rather than errors: nothing was ever saved,
 * the OS cannot decrypt what is there (a different machine, a rotated login credential), or the saved
 * key belongs to a *different* endpoint — in which case the caller must ask for one rather than send
 * the wrong provider's credential to this host.
 */
export async function loadRememberedKey(baseUrl: string): Promise<string> {
  const api = bridge();
  if (typeof api?.keyLoad !== "function" || !baseUrl.trim()) return "";
  try {
    const held = await api.keyLoad();
    if (!held || typeof held.key !== "string" || typeof held.base_url !== "string") return "";
    return sameEndpoint(held.base_url, baseUrl) ? held.key : "";
  } catch {
    return "";
  }
}

/** True when a key is stored for *some* endpoint — used only to say so in the sheet. */
export async function rememberedEndpoint(): Promise<string> {
  const api = bridge();
  if (typeof api?.keyLoad !== "function") return "";
  try {
    const held = await api.keyLoad();
    return held && typeof held.base_url === "string" ? held.base_url : "";
  } catch {
    return "";
  }
}

/** Store the key for this endpoint. Returns whether the OS actually agreed to hold it. */
export async function rememberKey(baseUrl: string, apiKey: string): Promise<boolean> {
  const api = bridge();
  if (typeof api?.keySave !== "function") return false;
  if (!apiKey.trim() || !baseUrl.trim()) return false;
  try {
    return await api.keySave({ base_url: baseUrl, api_key: apiKey });
  } catch {
    return false;
  }
}

export async function forgetKey(): Promise<boolean> {
  const api = bridge();
  if (typeof api?.keyClear !== "function") return false;
  try {
    return await api.keyClear();
  } catch {
    return false;
  }
}
