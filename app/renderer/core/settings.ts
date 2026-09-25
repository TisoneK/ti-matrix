/*
 * User settings that outlive the window: endpoint, model, the env-var name for its key, the world and
 * its field values, the goal. Hydrated once at launch, saved (debounced, by the caller) on change.
 *
 * The line this module will not cross: a key's *value* is never persisted, never accepted here, and
 * stripped defensively if it ever shows up in world field values. Values live in the environment or in
 * renderer memory for one session — a settings file on disk is exactly the kind of quiet, permanent
 * copy a secret must never get. The `settingsLoad`/`settingsSave` calls are absent in a plain browser
 * tab, where this module simply becomes a no-op.
 */

import { MODELS, budgetFor } from "./models";

export interface StoredModel {
  base_url: string;
  model: string;
  api_key_env: string;
}

export interface AppSettings {
  model?: StoredModel;
  world?: string;
  values?: Record<string, string | boolean>;
  goal?: string;
  /** What a run may spend — plain numbers, mirrored from the engine's budget fields. */
  budget?: { max_depth?: number; max_branches?: number; max_model_calls?: number; max_backtracks?: number };
  /** True once the first-run welcome has been dismissed — it never nags again. */
  welcomeSeen?: boolean;
  /** Whether a run carries what earlier runs in the same world established. Default on. */
  remember?: boolean;
}

interface SettingsBridge {
  settingsLoad?: () => Promise<unknown>;
  settingsSave?: (value: AppSettings) => Promise<boolean>;
}

const bridge = (): SettingsBridge | undefined =>
  (window as unknown as { tm?: SettingsBridge }).tm;

const str = (value: unknown): string => (typeof value === "string" ? value : "");

/** Anything secret-shaped is dropped on the floor, wherever it tried to hide. */
const stripKeyish = (values: Record<string, string | boolean>): Record<string, string | boolean> => {
  const out: Record<string, string | boolean> = {};
  for (const [k, v] of Object.entries(values)) {
    if (/api[-_]?key/i.test(k)) continue;
    out[k] = v;
  }
  return out;
};

export async function loadSettings(): Promise<AppSettings | null> {
  const api = bridge();
  if (!api?.settingsLoad) return null;
  try {
    const raw = await api.settingsLoad();
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return null;
    const s = raw as Record<string, unknown>;
    const out: AppSettings = {};
    if (s["model"] && typeof s["model"] === "object") {
      const m = s["model"] as Record<string, unknown>;
      out.model = { base_url: str(m["base_url"]), model: str(m["model"]), api_key_env: str(m["api_key_env"]) };
    }
    if (typeof s["world"] === "string") out.world = s["world"];
    if (s["values"] && typeof s["values"] === "object" && !Array.isArray(s["values"])) {
      const values: Record<string, string | boolean> = {};
      for (const [k, v] of Object.entries(s["values"] as Record<string, unknown>)) {
        if (typeof v === "string" || typeof v === "boolean") values[k] = v;
      }
      out.values = stripKeyish(values);
    }
    if (typeof s["goal"] === "string") out.goal = s["goal"];
    if (s["budget"] && typeof s["budget"] === "object" && !Array.isArray(s["budget"])) {
      const budget: Record<string, number> = {};
      for (const [k, v] of Object.entries(s["budget"] as Record<string, unknown>)) {
        if (typeof v === "number" && Number.isFinite(v)) budget[k] = v;
      }
      out.budget = budget;
    }
    if (typeof s["welcomeSeen"] === "boolean") out.welcomeSeen = s["welcomeSeen"];
    if (typeof s["remember"] === "boolean") out.remember = s["remember"];
    return migrate(out);
  } catch {
    return null; // unreadable settings are not an error, they are defaults
  }
}

/**
 * The one settings value that is not a preference: the endpoint the app used to write down for you.
 *
 * Until now the app opened pointing at `qwen2.5:7b` on a local Ollama and saved that on the first
 * change — so a machine without that exact model pulled recorded a broken run configuration and kept
 * it forever. Changing the shipped default fixes the next fresh install and nobody else; everyone who
 * has ever opened the window still has the old one on disk, which is precisely the person who has been
 * looking at an empty map.
 *
 * So this rewrites exactly one value — the old shipped pair, byte for byte — to the built-in rules. It
 * is safe to do silently because that pair is indistinguishable from "never configured": it is what the
 * app chose on the user's behalf, not what the user chose. Any other endpoint, including the same
 * Ollama with a model someone actually picked, is left exactly as it was found.
 */
const ABANDONED_DEFAULT = { base_url: "http://localhost:11434/v1", model: "qwen2.5:7b" };
const OLD_BUDGET = { max_depth: 6, max_branches: 3, max_model_calls: 16, max_backtracks: 2 };

function migrate(out: AppSettings): AppSettings {
  const m = out.model;
  if (!m || m.base_url !== ABANDONED_DEFAULT.base_url || m.model !== ABANDONED_DEFAULT.model) return out;
  out.model = { ...m, base_url: MODELS.defaults.base_url, model: MODELS.defaults.model };
  // The budget travels with the seat for the same reason: the engine's six-step default exists because
  // a model call is slow and costly, and against the rules it would stop a solvable maze half-drawn.
  // Only an untouched budget moves — a number someone typed is a number they meant.
  const b = out.budget;
  const untouched = b !== undefined
    && (Object.keys(OLD_BUDGET) as (keyof typeof OLD_BUDGET)[]).every((k) => b[k] === OLD_BUDGET[k]);
  if (b === undefined || untouched) out.budget = { ...budgetFor(MODELS.defaults.model) };
  return out;
}

export function saveSettings(settings: AppSettings): void {
  const api = bridge();
  if (!api?.settingsSave) return;
  // Defensive by construction: what App hands us never contains the key value, and stripKeyish runs
  // again here so the invariant holds even if a caller forgets.
  const safe: AppSettings = {
    ...settings,
    values: settings.values ? stripKeyish(settings.values) : undefined,
  };
  void api.settingsSave(safe).catch(() => undefined);
}
