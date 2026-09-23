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

/** The provider's name, from its host — the readout people actually scan. */
const PROVIDERS: [RegExp, string][] = [
  [/^api\.deepseek\./, "DeepSeek"],
  [/^api\.openai\./, "OpenAI"],
  [/^openrouter\./, "OpenRouter"],
  [/^api\.groq\./, "Groq"],
  [/^api\.anthropic\./, "Anthropic"],
  [/^(localhost|127\.0\.0\.1|\[::1\])(:|$)/, "local"],
];

export function providerName(baseUrl: string): string {
  let host = baseUrl;
  try { host = new URL(baseUrl).host; } catch { /* a half-typed URL is not worth a throw */ }
  for (const [pattern, name] of PROVIDERS) {
    if (pattern.test(host)) return name;
  }
  // An unknown host is still a name: the domain without its port, not a URL.
  return host.replace(/^www\./, "").split(":")[0] || host;
}

/** The one-line summary the settings button shows, so the model in play is visible without opening it. */
export function modelSummary(config: Record<string, string | boolean>): string {
  const model = String(config["model"] ?? MODELS.defaults["model"]);
  return `${model} · ${providerName(String(config["base_url"] ?? MODELS.defaults["base_url"]))}`;
}

/**
 * What a run may spend. Mirrors `EngineBudget`'s own defaults, so the drawer opens showing what an
 * untouched run would actually get — the numbers are the engine's, not the app's invention.
 *
 * These are the first thing a real model makes you care about: a maze run against a live endpoint spends
 * 20–45 seconds per decision, so the default depth of six ends the run long before the exit, and without
 * these controls there is nothing a viewer can do about it from the window.
 */
export interface Budget {
  max_depth: number;
  max_branches: number;
  max_model_calls: number;
  max_backtracks: number;
}

export const BUDGET: {
  defaults: Budget;
  fields: { name: keyof Budget; label: string; hint: string }[];
} = {
  defaults: { max_depth: 6, max_branches: 3, max_model_calls: 16, max_backtracks: 2 },
  fields: [
    { name: "max_depth", label: "Steps", hint: "how deep the search may go — one step is one decision" },
    { name: "max_branches", label: "Options per step", hint: "how many moves it may weigh at once" },
    { name: "max_model_calls", label: "Model calls", hint: "the hard ceiling: a proposer call and an evaluator call per step" },
    { name: "max_backtracks", label: "Retreats", hint: "how many times it may give a branch up" },
  ],
};
