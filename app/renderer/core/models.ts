/* The model a run talks to. Kept in one place because the shell, the settings dialog and the goal frame
 * all have to agree on the same three keys and the same defaults. */

export interface ModelDefaults {
  base_url: string;
  model: string;
  api_key_env: string;
}

export const MODELS: { defaults: ModelDefaults; labels: Record<string, string> } = {
  defaults: {
    base_url: "http://localhost:11434/v1",
    model: "qwen2.5:7b",
    api_key_env: "OPENAI_API_KEY",
  },
  labels: {
    base_url: "Model endpoint (any OpenAI-compatible one)",
    model: "Model",
    api_key_env: "API key: the NAME of the env var holding it",
  } as Record<string, string>,
};

/** The one-line summary the settings button shows, so the model in play is visible without opening it. */
export function modelSummary(config: Record<string, string | boolean>): string {
  const model = String(config["model"] ?? MODELS.defaults["model"]);
  const url = String(config["base_url"] ?? MODELS.defaults["base_url"]);
  let host = url;
  try { host = new URL(url).host; } catch { /* a half-typed URL is not worth a throw */ }
  return `${model} · ${host}`;
}
