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

import { useEffect } from "react";
import { WorldField, WorldInfo } from "../protocol";
import { Button } from "../ui/controls";
import { Budget, BUDGET } from "../core/models";
import { Field, Fieldset } from "../ui/atoms";

export interface ModelConfig {
  base_url: string;
  model: string;
  api_key_env: string;
}

export function ConfigDrawer({ worlds, world, fields, values, set, model, setModel, modelLabels, budget, setBudget, onPick, headless, apiKey, setApiKey, onClose }: {
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
  onPick: () => void;
  headless: boolean;
  /** The pasted key: session memory only, sent with the run, never saved anywhere. */
  apiKey: string;
  setApiKey: (value: string) => void;
  /** Closes the sheet — Esc does the same. A surface the user cannot dismiss is a trap. */
  onClose: () => void;
}) {
  const current = worlds.find((w) => w.name === world);
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
      <div className="drawer-grid">
        <Field label={modelLabels["base_url"] ?? "Endpoint"} hint="any OpenAI-compatible base URL">
          {(f) => <input {...f} type="text" value={model.base_url} spellCheck={false}
                         onChange={(e) => setModel("base_url", e.target.value)} />}
        </Field>
        <Field label={modelLabels["model"] ?? "Model"} hint="the name the endpoint knows it by">
          {(f) => <input {...f} type="text" value={model.model} spellCheck={false}
                         onChange={(e) => setModel("model", e.target.value)} />}
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

        {BUDGET.fields.map((f) => (
          <Field key={f.name} label={f.label} hint={f.hint}>
            {(props) => <input {...props} type="number" min={1} max={999} value={budget[f.name]}
                                onChange={(e) => setBudget(f.name, Math.max(1, Math.min(999, Number(e.target.value) || 1)))} />}
          </Field>
        ))}

        {fields.some((f) => f.name === "root" || f.name === "project") ? (
          <Fieldset label="Browse" hint="fills the directory field above">
            <Button onClick={onPick} size="sm">Choose a directory…</Button>
          </Fieldset>
        ) : null}
      </div>

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
