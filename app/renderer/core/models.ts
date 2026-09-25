/* The model a run talks to. Kept in one place because the shell, the settings dialog and the goal frame
 * all have to agree on the same three keys and the same defaults. */

export interface ModelDefaults {
  base_url: string;
  model: string;
  api_key_env: string;
}

/**
 * The name that means "no model at all": the sidecar fills the proposer's and the evaluator's seats
 * with rules instead of an endpoint. It is the default on purpose.
 *
 * The app used to open pointing at `qwen2.5:7b` on a local Ollama. On a machine without that exact
 * model pulled — which is most machines, including one running Ollama — every run died on its second
 * event with `proposer_error: 404`, and every panel in the window correctly drew nothing. A first run
 * has to be able to happen before any of this is worth looking at, so the default is the one engine
 * that is always there.
 */
export const BUILTIN = "builtin";

export const isBuiltin = (model: string): boolean => model.trim().toLowerCase() === BUILTIN;

export const MODELS: { defaults: ModelDefaults; labels: Record<string, string> } = {
  defaults: {
    base_url: "",
    model: BUILTIN,
    api_key_env: "OPENAI_API_KEY",
  },
  labels: {
    base_url: "Model endpoint (any OpenAI-compatible one)",
    model: "Model",
    api_key_env: "API key: the NAME of the env var holding it",
  } as Record<string, string>,
};

/** What an endpoint-backed run should open with, once someone switches away from the rules. */
export const LLM_SUGGESTION: ModelDefaults = {
  base_url: "http://localhost:11434/v1",
  model: "",
  api_key_env: "OPENAI_API_KEY",
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

/**
 * How a model is named wherever a run is listed. `builtin` is a wire value — the string the goal frame
 * carries — and it was being printed raw in the library's model column, a lowercase identifier sitting
 * in a list beside "deepseek-flash" and "qwen2.5:7b" as though it were another vendor's model. It is the
 * absence of one, and it should read that way everywhere it is shown.
 */
export const modelLabel = (model: string): string =>
  (isBuiltin(model) ? "built-in rules" : model || "—");

/** The one-line summary the settings button shows, so the model in play is visible without opening it. */
export function modelSummary(config: Record<string, string | boolean>): string {
  const model = String(config["model"] ?? MODELS.defaults["model"]);
  // The rules are not a provider and have no host, so naming one would be a lie about where the
  // deciding happens.
  if (isBuiltin(model)) return "built-in rules · no model";
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

/**
 * What the rules get instead. The engine's own defaults are sized for a model that costs twenty seconds
 * and real money per decision; the built-in reasoner costs neither, and a maze it could solve in thirty
 * steps would stop at six and show a half-drawn map for no reason at all. These are the numbers a run
 * with no model to pay for should actually get.
 */
export const BUILTIN_BUDGET: Budget = {
  max_depth: 80, max_branches: 3, max_model_calls: 600, max_backtracks: 40,
};

/** The budget a run should open with, given what is sitting in the two seats. */
export const budgetFor = (model: string): Budget =>
  (isBuiltin(model) ? { ...BUILTIN_BUDGET } : { ...BUDGET.defaults });

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
