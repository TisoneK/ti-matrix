/*
 * The config drawer: the instrument panel, kept out of the way.
 *
 * Endpoint, model, key and the world's own fields are all real configuration — but they are not the
 * product, and a window that gives them half its area has decided the wrong thing is interesting. So they
 * live behind one toggle, they start closed, and they close themselves when a run begins.
 *
 * The key is never held here: the field asks for the *name* of the environment variable that holds it, and
 * what travels to the sidecar is the name. There is nothing secret in this window's state to leak.
 */

import { WorldField, WorldInfo } from "../protocol";
import { Button } from "../ui/controls";
import { Budget, BUDGET } from "../core/models";
import { Field, Fieldset } from "../ui/atoms";

export interface ModelConfig {
  base_url: string;
  model: string;
  api_key_env: string;
}

export function ConfigDrawer({ worlds, world, fields, values, set, model, setModel, modelLabels, budget, setBudget, onPick, headless }: {
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
}) {
  const current = worlds.find((w) => w.name === world);
  return (
    <div className="drawer">
      <div className="drawer-grid">
        <Field label={modelLabels["base_url"] ?? "Endpoint"} hint="any OpenAI-compatible base URL">
          {(f) => <input {...f} type="text" value={model.base_url} spellCheck={false}
                         onChange={(e) => setModel("base_url", e.target.value)} />}
        </Field>
        <Field label={modelLabels["model"] ?? "Model"} hint="the name the endpoint knows it by">
          {(f) => <input {...f} type="text" value={model.model} spellCheck={false}
                         onChange={(e) => setModel("model", e.target.value)} />}
        </Field>
        <Field label="API key env var"
               hint={model.api_key_env ? `reads $${model.api_key_env} — the value never enters this window` : "no key: the endpoint is asked without one"}>
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
