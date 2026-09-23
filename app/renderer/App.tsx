/*
 * The window, organized around the run rather than around the machinery.
 *
 * The bar carries the three things a run needs — world, goal, the button — and the vitals of the one in
 * flight. The stage then answers, in order: how did it end (if it has), what is the world doing, what has
 * it established, what shape is the search, and only then the raw event log, folded away, because that is
 * the implementation's view and not the product of a run.
 */

import { useEffect, useMemo, useState } from "react";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { EventStream } from "./components/EventStream";
import { Knowledge } from "./components/Knowledge";
import { Outcome } from "./components/Outcome";
import { SearchTree } from "./components/SearchTree";
import { SettingsDialog } from "./components/SettingsDialog";
import { Button } from "./ui/Controls";
import { Meters, Pill } from "./ui/Display";
import { formatElapsed, pct } from "./lib/format";
import { MODELS, modelSummary } from "./lib/models";
import { readVitals } from "./lib/vitals";
import { useSidecar } from "./lib/useSidecar";
import { WorldView } from "./worlds";

export function App() {
  const { status, worlds, events, settled, confirm, run, stop, answer, pickDirectory } = useSidecar();
  const [world, setWorld] = useState("maze");
  const [config, setConfig] = useState<Record<string, string | boolean>>({});
  const [goal, setGoal] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);

  // A world the registry no longer offers (or has not offered yet) falls back to the first one it does.
  useEffect(() => {
    if (worlds.length > 0 && !worlds.some((w) => w.name === world)) setWorld(worlds[0].name);
  }, [worlds, world]);

  const current = worlds.find((w) => w.name === world);
  const running = status === "running";
  const vitals = useMemo(() => readVitals(events), [events]);
  const lastMs = events.length > 0 ? events[events.length - 1].t_ms : 0;

  const set = (name: string, value: string | boolean) => setConfig((c) => ({ ...c, [name]: value }));

  const runConfig = useMemo(() => ({
    ...config,
    ...Object.fromEntries(Object.entries(MODELS.defaults).map(([k, v]) => [k, String(config[k] ?? v)])),
  }), [config]);

  const blocked = status === "crashed" ? "the sidecar is not running — restart the app"
    : status === "connecting" ? "connecting to the sidecar…"
      : running ? "a run is already in flight"
        : goal.trim() ? "" : "type a goal to run";

  const start = () => { if (!blocked) run(goal.trim(), world, runConfig); };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Ti Matrix</h1>
          <span className="tag">TM1</span>
        </div>
        <Pill status={status} />
        <span className="spacer" />
        <Meters items={[
          { label: "progress", value: pct(vitals.progress) },
          { label: "depth", value: vitals.depth },
          { label: "facts", value: vitals.facts.length },
          { label: "elapsed", value: formatElapsed(lastMs) },
        ]} />
        <button type="button" className="settings-btn" onClick={() => setSettingsOpen(true)}
                title="the world's settings and the model">
          <span className="gear" aria-hidden="true">⚙</span>
          {modelSummary(config)}
        </button>
      </header>

      <div className="controlbar">
        <div className="worlds" role="group" aria-label="world">
          {worlds.map((w) => (
            <button key={w.name} className={`world ${w.name === world ? "on" : ""}`}
                    aria-pressed={w.name === world} onClick={() => setWorld(w.name)}>
              {w.title}
            </button>
          ))}
        </div>

        <label className="goal-input">
          <span className="sr-only">Goal</span>
          <textarea id="goal" value={goal} rows={1} spellCheck={false}
                    placeholder={`what should the ${current?.title ?? "world"} find out or reach?`}
                    onChange={(e) => setGoal(e.target.value)}
                    onKeyDown={(e) => {
                      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); start(); }
                    }} />
        </label>

        <div className="run-buttons">
          <Button variant="primary" disabled={Boolean(blocked)} onClick={start} title={blocked}>Run</Button>
          <Button variant="ghost" disabled={!running} onClick={stop}>Stop</Button>
        </div>
      </div>

      <p className="underbar hint">
        {blocked || current?.note}
        {!blocked && !running ? <span className="dim"> · ⌘↵ to run</span> : null}
      </p>

      <main className="stage">
        {settled ? <div className="stage-item"><Outcome settled={settled} /></div> : null}
        <div className="world-view">
          <WorldView world={world} events={events} />
        </div>
        <Knowledge vitals={vitals} running={running} />
        <SearchTree events={events} />
        <EventStream events={events} running={running} collapsedByDefault />
      </main>

      {settingsOpen ? (
        <SettingsDialog world={current} config={config} set={set} onPick={pickDirectory}
                        onClose={() => setSettingsOpen(false)} />
      ) : null}
      <ConfirmDialog request={confirm} onAnswer={answer} />
    </div>
  );
}
