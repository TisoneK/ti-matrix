/*
 * Settings, on demand.
 *
 * These are the things you set once per world and per endpoint — a root directory, a model, which env var
 * holds the key — and they have no business occupying the window while a run is being watched. They live
 * behind the settings button, grouped by what they configure: the world, then the model.
 */

import { MODELS } from "../lib/models";
import { WorldInfo } from "../protocol";
import { Button, Field } from "../ui/Controls";
import { Modal } from "../ui/Modal";

export function SettingsDialog({ world, config, set, onPick, onClose }: {
  world: WorldInfo | undefined;
  config: Record<string, string | boolean>;
  set: (name: string, value: string | boolean) => void;
  onPick: () => Promise<string | null>;
  onClose: () => void;
}) {
  return (
    <Modal title="Settings" onClose={onClose}
           footer={<Button variant="primary" onClick={onClose}>Done</Button>}>
      {world ? (
        <section className="settings-group">
          <h3>{world.title}</h3>
          <p className="hint">{world.note}</p>
          {world.fields.map((f) => (
            <Field key={f.name} field={f} value={config[f.name] ?? f.default}
                   onChange={(v) => set(f.name, v)}
                   onPick={async () => {
                     const dir = await onPick();
                     if (dir) set(f.name, dir);
                   }} />
          ))}
        </section>
      ) : null}

      <section className="settings-group">
        <h3>The model</h3>
        <p className="hint">
          Any OpenAI-compatible endpoint. The key itself is never typed here — only the name of the
          environment variable the sidecar should read it from.
        </p>
        {Object.keys(MODELS.defaults).map((name) => (
          <Field key={name}
                 field={{ name, label: MODELS.labels[name], default: MODELS.defaults[name] }}
                 value={config[name] ?? MODELS.defaults[name]}
                 onChange={(v) => set(name, v)}
                 onPick={() => {}} />
        ))}
      </section>
    </Modal>
  );
}
