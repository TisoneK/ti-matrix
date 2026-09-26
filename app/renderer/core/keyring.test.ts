/* The remembered API key — the rules that decide whether it is used at all.
 *
 * The feature exists because pasting a key on every launch is a real annoyance. The rules below are what
 * keeps it from becoming a new way to leak one: remembered only for the endpoint it was entered for,
 * never applied to a blank or different endpoint, and a bridge that says no is obeyed rather than
 * worked around. The pure endpoint comparison is checked first because everything else depends on it.
 */
import { canRememberKey, forgetKey, loadRememberedKey, rememberedEndpoint, rememberKey, sameEndpoint } from "./keyring";

let pass = 0;
const failures: string[] = [];
const eq = (what: string, got: unknown, want: unknown) => {
  if (JSON.stringify(got) === JSON.stringify(want)) { pass++; return; }
  failures.push(`${what}\n    got  ${JSON.stringify(got)}\n    want ${JSON.stringify(want)}`);
};

/* ── is this the same place to send a key? ──────────────────────────────── */

eq("the same endpoint is the same", sameEndpoint("https://api.deepseek.com", "https://api.deepseek.com"), true);
eq("a trailing slash is not a different provider",
   sameEndpoint("https://api.deepseek.com/", "https://api.deepseek.com"), true);
eq("and neither is the host's case",
   sameEndpoint("https://API.DeepSeek.com", "https://api.deepseek.com"), true);
eq("a version prefix is part of the address, not decoration",
   sameEndpoint("https://api.deepseek.com/v1", "https://api.deepseek.com"), false);
eq("a path is compared as written — it is not the host",
   sameEndpoint("https://host.example/V1", "https://host.example/v1"), false);
eq("a different port is a different place", sameEndpoint("http://localhost:11434/v1", "http://localhost:1234/v1"), false);
eq("a different host is a different place", sameEndpoint("https://api.deepseek.com", "https://api.openai.com"), false);
eq("a blank endpoint matches nothing, not even another blank", sameEndpoint("", ""), false);
eq("and a half-typed endpoint does not match the endpoint it will become",
   sameEndpoint("https://api.deep", "https://api.deepseek.com"), false);

/* ── what the renderer does with it ─────────────────────────────────────── */

type Bridge = {
  keyLoad?: () => Promise<{ base_url: string; key: string } | null>;
  keySave?: (value: { base_url: string; api_key: string }) => Promise<boolean>;
  keyClear?: () => Promise<boolean>;
};
const setBridge = (bridge: Bridge | undefined): void => {
  (globalThis as unknown as { window: { tm?: Bridge } }).window = bridge ? { tm: bridge } : {};
};

async function main(): Promise<void> {
  const HELD = { base_url: "https://api.deepseek.com", key: "sk-remembered" };

  setBridge(undefined);
  eq("a browser tab has no keyring", canRememberKey(), false);
  eq("and asking it for a key is empty, not a throw", await loadRememberedKey("https://api.deepseek.com"), "");

  setBridge({ keyLoad: async () => HELD });
  eq("a remembered key comes back for its own endpoint", await loadRememberedKey(HELD.base_url), HELD.key);
  eq("with the trailing slash the field may carry", await loadRememberedKey("https://api.deepseek.com/"), HELD.key);
  eq("a *different* endpoint gets nothing — the key is not carried to another host",
     await loadRememberedKey("https://api.openai.com"), "");
  eq("an empty endpoint gets nothing", await loadRememberedKey(""), "");
  eq("and the sheet can still say one is stored, and for where", await rememberedEndpoint(), HELD.base_url);

  setBridge({ keyLoad: async () => null });
  eq("nothing stored is nothing returned", await loadRememberedKey(HELD.base_url), "");
  eq("and nothing to name", await rememberedEndpoint(), "");

  setBridge({ keyLoad: async () => { throw new Error("decrypt failed"); } });
  eq("an unreadable store is an ordinary empty, not a crash", await loadRememberedKey(HELD.base_url), "");
  eq("and does not stop the sheet saying nothing is stored", await rememberedEndpoint(), "");

  const saved: Array<{ base_url: string; api_key: string }> = [];
  setBridge({ keySave: async (v) => { saved.push(v); return true; } });
  eq("a typed key is handed to main with its endpoint",
     await rememberKey(HELD.base_url, "sk-typed"), true);
  eq("…verbatim, and paired with the endpoint it was entered for", saved, [{ base_url: HELD.base_url, api_key: "sk-typed" }]);
  eq("an empty key is never stored", await rememberKey(HELD.base_url, "   "), false);
  eq("nor is a key with no endpoint to bind it to", await rememberKey("", "sk-typed"), false);
  eq("only the one real attempt reached main", saved.length, 1);

  let cleared = 0;
  setBridge({ keyClear: async () => { cleared++; return true; } });
  eq("forgetting reports what main said", await forgetKey(), true);
  eq("and did ask main to clear it", cleared, 1);

  setBridge({});
  eq("a bridge without the channels stores nothing", await rememberKey(HELD.base_url, "sk-typed"), false);
  eq("and forgets nothing", await forgetKey(), false);

  console.log(`\n${pass} passed, ${failures.length} failed`);
  if (failures.length) throw new Error("keyring checks failed:\n" + failures.map((f) => "  ✗ " + f).join("\n"));
}

void main();
