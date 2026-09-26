/*
 * The config drawer: the instrument panel, kept out of the way.
 *
 * Endpoint, model, key and the world's own fields are all real configuration — but they are not the
 * product, and a window that gives them half its area has decided the wrong thing is interesting. So they
 * live behind one toggle, they start closed, and they close themselves when a run begins.
 *
 * One key field, and it is the masked one: a value pasted here is session memory, rides with the run,
 * and is never saved. The env-var *name* stays as the durable setting for machines that keep the key in
 * their environment — two fields for one secret was a trap nobody should have to read twice.
 */

import { useEffect, useRef } from "react";
import { WorldField, WorldInfo } from "../protocol";
import { Button } from "../ui/controls";
import { Budget, BUDGET, BUILTIN, LLM_SUGGESTION, isBuiltin } from "../core/models";
import { Field, Fieldset } from "../ui/atoms";

export interface ModelConfig {
  base_url: string;
  model: string;
  api_key_env: string;
}

export function ConfigDrawer({ worlds, world, fields, values, set, model, setModel, modelLabels, budget, setBudget, remember, setRemember, onPick, headless, apiKey, setApiKey, onClose, models, modelsLoading, modelsError, onFetchModels, onClearModels }: {
  worlds: WorldInfo[];
  world: string;
  /** The world's own fields, from the sidecar's registry. */
  fields: WorldField[];
  values: Record<string, string | boolean>;
  set: (name: string, value: string | boolean) => void;
  model: ModelConfig;
  setModel: (name: keyof ModelConfig, value: string) => void;
  modelLabels: Record<string, string>;
  budget: Budget;
  setBudget: (name: keyof Budget, value: number) => void;
  /** Whether a run carries what earlier runs in this world established. */
  remember: boolean;
  setRemember: (value: boolean) => void;
  onPick: () => void;
  headless: boolean;
  /** The pasted key: session memory only, sent with the run, never saved anywhere. */
  apiKey: string;
  setApiKey: (value: string) => void;
  /** Closes the sheet — Esc does the same. A surface the user cannot dismiss is a trap. */
  onClose: () => void;
  /** What the endpoint answered last time it was asked what it offers — `null` before the first ask. */
  models: string[] | null;
  modelsLoading: boolean;
  modelsError: string | null;
  onFetchModels: () => void;
  onClearModels: () => void;
}) {
  const current = worlds.find((w) => w.name === world);
  // The rules need no endpoint, no key and no env var, so those four fields are not shown against them —
  // an empty "API key" box beside a run that will never make a request is a question with no answer.
  const rules = isBuiltin(model.model);
  // Ask the endpoint what it offers once the fields that matter settle down — not on every keystroke,
  // which would spend a call per letter typed and spam an incomplete key at whatever is listening.
  // Debounced rather than on-blur: a field left as-is when focus moves elsewhere (closing the drawer,
  // say) still deserves the fetch its value earned.
  const endpoint = `${model.base_url}\u0000${apiKey}\u0000${model.api_key_env}`;
  const fetching = useRef(onFetchModels);
  fetching.current = onFetchModels;
  useEffect(() => {
    if (rules || !model.base_url.trim()) { onClearModels(); return; }
    const timer = setTimeout(() => fetching.current(), 700);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `endpoint` folds the three real inputs into one key
  }, [rules, endpoint]);
  // Esc closes, from wherever the focus happens to be — unless it is in a text field mid-word.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== "Escape") return;
      const t = e.target as HTMLElement | null;
      if (t && ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) && document.activeElement === t) return;
      onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="drawer" role="dialog" aria-label="run configuration">
      <div className="drawer-bar">
        <span className="pane-title">Setup</span>
        <span className="pane-sub">saved as you type — the key never leaves this window</span>
        <span className="spacer" />
        <button type="button" className="winbtn" onClick={onClose} aria-label="close setup" title="close (Esc)">
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <path d="M1 1 L9 9 M9 1 L1 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      {/* Which engine decides. This is the first choice, above the endpoint fields, because it is the
          one that decides whether those fields matter at all — and because the rules are what makes a
          first run possible on a machine with no model on it. */}
      <div className="seatpick" role="group" aria-label="what decides the run">
        <button type="button" aria-pressed={rules}
                onClick={() => { setModel("model", BUILTIN); setModel("base_url", ""); }}>
          Built-in rules
          <small>instant, offline, no key — a real search with no model in it</small>
        </button>
        <button type="button" aria-pressed={!rules}
                onClick={() => {
                  if (!rules) return;
                  setModel("model", LLM_SUGGESTION.model);
                  setModel("base_url", LLM_SUGGESTION.base_url);
                }}>
          A language model
          <small>any OpenAI-compatible endpoint — slower, and it reasons</small>
        </button>
      </div>

      {rules ? null : (
        <section className="drawer-section">
          <h3 className="drawer-section-title">Endpoint &amp; model</h3>
          <div className="drawer-grid">
            <Field label={modelLabels["base_url"] ?? "Endpoint"} hint="any OpenAI-compatible base URL">
              {(f) => <input {...f} type="text" value={model.base_url} spellCheck={false}
                             onChange={(e) => setModel("base_url", e.target.value)} />}
            </Field>
            <Field label={modelLabels["model"] ?? "Model"}
                   hint={modelsLoading ? "asking the endpoint what it offers…"
                     : modelsError ? `couldn't list models: ${modelsError}`
                       : models && models.length > 0 ? `${models.length} fetched from the endpoint — pick one, or type your own`
                         : "the name the endpoint knows it by"}>
              {(f) => (
                <div className="model-pick">
                  <input {...f} type="text" value={model.model} spellCheck={false}
                         placeholder="the exact name the endpoint knows"
                         onChange={(e) => setModel("model", e.target.value)} />
                  {models && models.length > 0 ? (
                    <select aria-label="pick a model the endpoint offers" value=""
                            onChange={(e) => { if (e.target.value) setModel("model", e.target.value); }}>
                      <option value="">pick from the endpoint's own list…</option>
                      {models.map((m) => <option key={m} value={m}>{m}</option>)}
                    </select>
                  ) : modelsError ? (
                    <Button size="sm" onClick={onFetchModels}>Retry</Button>
                  ) : null}
                </div>
              )}
            </Field>
            <Field label="API key"
                   hint={apiKey.trim()
                     ? "held in memory for this session only — never saved to disk"
                     : model.api_key_env
                       ? `empty: the key is read from $${model.api_key_env} in this machine's environment`
                       : "empty and no env var set: the endpoint is asked without a key"}>
              {(f) => <input {...f} type="password" value={apiKey} spellCheck={false} autoComplete="off"
                             placeholder={model.api_key_env ? `leave empty to use $${model.api_key_env}` : "paste a key for this session"}
                             onChange={(e) => setApiKey(e.target.value)} />}
            </Field>
            <Field label="Env var fallback"
                   hint={`advanced: which environment variable holds the key when the field above is empty`}>
              {(f) => <input {...f} type="text" value={model.api_key_env} spellCheck={false} placeholder="OPENAI_API_KEY"
                             onChange={(e) => setModel("api_key_env", e.target.value)} />}
            </Field>
          </div>
        </section>
      )}

      {fields.length > 0 ? (
        <section className="drawer-section">
          <h3 className="drawer-section-title">{current?.title ?? "World"}</h3>
          <div className="drawer-grid">
            {fields.map((f) => (
              f.kind === "checkbox" ? (
                <div className="field check" key={f.name}>
                  <input id={`f-${f.name}`} type="checkbox" checked={Boolean(values[f.name])}
                         onChange={(e) => set(f.name, e.target.checked)} />
                  <label className="field-label" htmlFor={`f-${f.name}`}>{f.label}</label>
                </div>
              ) : (
                <Field key={f.name} label={f.label}
                       hint={f.name === "seed" ? "the same seed rebuilds the same world — that is what makes two runs comparable" : undefined}>
                  {(props) => <input {...props} type="text" value={String(values[f.name] ?? "")} spellCheck={false}
                                      placeholder={f.placeholder ?? String(f.default ?? "")}
                                      onChange={(e) => set(f.name, e.target.value)} />}
                </Field>
              )
            ))}
            {fields.some((f) => f.name === "root" || f.name === "project") ? (
              <Fieldset label="Browse" hint="fills the directory field above">
                <Button onClick={onPick} size="sm">Choose a directory…</Button>
              </Fieldset>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="drawer-section">
        {/* The engine's own memory. Off by default for the app's whole life until now, which meant a
            model re-derived a world's affordances from scratch on every run — `benchmarks/bench.py`
            has the warm pass settling the same goals in 1 round and 3 probes against 2 and 6. Shown
            rather than silent because it makes two runs of the same goal non-identical, and Compare
            exists to hold two runs against each other. */}
        <div className="field check">
          <input id="f-remember" type="checkbox" checked={remember}
                 onChange={(e) => setRemember(e.target.checked)} />
          <label className="field-label" htmlFor="f-remember">
            {remember
              ? "Memory: this run starts with what earlier runs in this world learned, and adds to it"
              : "Memory: this run starts cold, and leaves the record untouched"}
          </label>
        </div>

        {/* Collapsed by default — steps/branching/ceiling/retreats are tuning knobs a run rarely needs
            touched, and showing all four open beside "which world" and "which model" was exactly the
            kind of undifferentiated field-dump that makes a settings screen feel like a config file
            rather than a decision someone is making. */}
        <details className="drawer-advanced">
          <summary>Search budget <span className="pane-sub">— how deep, how wide, how long</span></summary>
          <div className="drawer-grid">
            {BUDGET.fields.map((f) => (
              <Field key={f.name} label={f.label} hint={f.hint}>
                {(props) => <input {...props} type="number" min={1} max={999} value={budget[f.name]}
                                    onChange={(e) => setBudget(f.name, Math.max(1, Math.min(999, Number(e.target.value) || 1)))} />}
              </Field>
            ))}
          </div>
        </details>
      </section>

      <div className="drawer-foot">
        <span className="pane-sub">{current?.note ?? ""}</span>
        {headless ? (
          <span className="warn">
            no shell around this window — runs will not be saved
          </span>
        ) : null}
      </div>
    </div>
  );
}
