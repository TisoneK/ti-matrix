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
    return out;
  } catch {
    return null; // unreadable settings are not an error, they are defaults
  }
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
