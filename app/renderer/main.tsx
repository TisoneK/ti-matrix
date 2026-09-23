import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Sidecar, WorldInfo, WorldField, EngineEventFrame, Frame } from "./protocol";
import "./styles.css";

const kindColor: Record<string, string> = {
  state: "#2f81f7", candidates: "#2f81f7", probe: "#3fb950", evaluation: "#a371f7",
  selected: "#d29922", backtrack: "#a371f7", confirmation: "#d29922",
  needs_confirmation: "#f85149", done: "#3fb950", stopped: "#f85149",
};

function useTm() {
  return (window as unknown as { tm: {
    onReady: (cb: (conn: { url: string }) => void) => void;
    onSidecarExit: (cb: (info: { code: number | null }) => void) => void;
    pickDirectory: () => Promise<string | null>;
    userDataPath: () => Promise<string>;
  } }).tm;
}

function MazeMap({ events }: { events: EngineEventFrame[] }) {
  // The world as the run actually knows it: facts are the probes' own text, and a cell is drawn
  // only once a probe entered it. No answer key — the fog clears exactly as fast as the search.
  const known = useMemo(() => {
    const cells = new Map<string, string>();
    for (const e of events) {
      if (e.kind !== "probe") continue;
      const ok = e["ok"] as boolean;
      const text = String(e["excerpt"] ?? "");
      const move = String(e["move"] ?? "");
      const m = /cell=(\d+),(\d+)/.exec(move);
      if (!m) continue;
      const at = `${m[1]},${m[2]}`;
      const dir = /direction=(\w+)/.exec(move)?.[1];
      const target = dir
        ? (dir === "north" ? [0, -1] : dir === "south" ? [0, 1] : dir === "east" ? [1, 0] : [-1, 0])
        : null;
      const stepped = move.startsWith("step(") && ok;
      cells.set(at, ok ? text : "wall");
      if (target && stepped) {
        const to = `${Number(m[1]) + target[0]},${Number(m[2]) + target[1]}`;
        if (!cells.has(to)) cells.set(to, "entered");
      }
    }
    return cells;
  }, [events]);

  if (known.size === 0) return null;
  const coords = [...known.keys()].map((k) => k.split(",").map(Number));
  const minX = Math.min(...coords.map((c) => c[0])) - 1;
  const maxX = Math.max(...coords.map((c) => c[0])) + 1;
  const minY = Math.min(...coords.map((c) => c[1])) - 1;
  const maxY = Math.max(...coords.map((c) => c[1])) + 1;
  const grid: React.ReactNode[] = [];
  for (let y = minY; y <= maxY; y++) {
    const row: React.ReactNode[] = [];
    for (let x = minX; x <= maxX; x++) {
      const v = known.get(`${x},${y}`);
      row.push(
        <span key={`${x},${y}`} title={v && v !== "wall" && v !== "entered" ? v : undefined}
              style={{ display: "inline-block", width: 18, textAlign: "center",
                        color: v === "wall" ? "#f85149" : v ? "#3fb950" : "#242a36" }}>
          {v === "wall" ? "▓" : v ? "·" : "░"}
        </span>,
      );
    }
    grid.push(<div key={y}>{row}</div>);
  }
  return (
    <div className="panel">
      <h2>maze, as far as the run has walked</h2>
      <pre className="mazemap">{grid}</pre>
    </div>
  );
}

function ConfirmDialog({ request, onAnswer }: {
  request: { id: string; action: { label: string }; reason: string } | null;
  onAnswer: (granted: boolean) => void;
}) {
  if (!request) return null;
  return (
    <div className="overlay">
      <div className="dialog">
        <h2>the engine wants to change something</h2>
        <pre className="action">{request.action.label}</pre>
        <p className="why">because: {request.reason || "—"}</p>
        <div className="row">
          <button className="allow" onClick={() => onAnswer(true)}>Allow this once</button>
          <button className="deny" onClick={() => onAnswer(false)}>Deny</button>
        </div>
      </div>
    </div>
  );
}

function App() {
  const tm = useTm();
  const sidecarRef = useRef<Sidecar | null>(null);
  const [status, setStatus] = useState<"connecting" | "ready" | "running" | "crashed">("connecting");
  const [worlds, setWorlds] = useState<WorldInfo[]>([]);
  const [world, setWorld] = useState<string>("maze");
  const [config, setConfig] = useState<Record<string, string | boolean>>({});
  const [goal, setGoal] = useState("");
  const [events, setEvents] = useState<EngineEventFrame[]>([]);
  const [confirm, setConfirm] = useState<{ id: string; action: { label: string }; reason: string } | null>(null);
  const [settled, setSettled] = useState<Record<string, unknown> | null>(null);

  const current = worlds.find((w) => w.name === world);

  useEffect(() => {
    tm.onReady(({ url }) => {
      const sidecar = new Sidecar(url);
      sidecarRef.current = sidecar;
      sidecar.onFrame((frame: Frame) => {
        if (frame.type === "worlds") {
          setWorlds(frame.worlds);
          setStatus((s) => (s === "running" ? s : "ready"));
        } else if (frame.type === "event") {
          setEvents((prev) => [...prev, frame as unknown as EngineEventFrame]);
        } else if (frame.type === "confirm-request") {
          setConfirm(frame);
        } else if (frame.type === "settled") {
          setSettled(frame as unknown as Record<string, unknown>);
          setStatus("ready");
        } else if (frame.type === "error") {
          setSettled({ error: frame.message });
          setStatus("ready");
        }
      });
      sidecar.connect();
    });
    tm.onSidecarExit(() => setStatus("crashed"));
  }, []);

  useEffect(() => { setConfig({}); }, [world]);

  const run = () => {
    if (!goal.trim()) return;
    setEvents([]);
    setSettled(null);
    setConfirm(null);
    setStatus("running");
    sidecarRef.current?.goal(goal.trim(), world, {
      ...config,
      base_url: (config["base_url"] as string) || "http://localhost:11434/v1",
      model: (config["model"] as string) || "qwen2.5:7b",
      api_key_env: (config["api_key_env"] as string) || "OPENAI_API_KEY",
    });
  };

  const stop = () => sidecarRef.current?.stop();
  const answer = (granted: boolean) => {
    if (!confirm) return;
    sidecarRef.current?.confirm(confirm.id, granted);
    setConfirm(null);
  };

  const pickDir = async (field: string) => {
    const dir = await tm.pickDirectory();
    if (dir) setConfig((c) => ({ ...c, [field]: dir }));
  };

  return (
    <div className="wrap">
      <header>
        <h1>Ti Matrix</h1>
        <span className={`status s-${status}`}>{status}</span>
      </header>
      <main>
        <aside>
          <h2>world</h2>
          <div className="worlds">
            {worlds.map((w) => (
              <button key={w.name} className={`world ${w.name === world ? "on" : ""}`}
                      onClick={() => setWorld(w.name)}>{w.title}</button>
            ))}
          </div>
          {current && <p className="note">{current.note}</p>}

          <h2>settings</h2>
          {(current?.fields ?? []).map((f: WorldField) => (
            <label key={f.name}>
              {f.label}
              {f.kind === "checkbox"
                ? <input type="checkbox" checked={Boolean(config[f.name] ?? f.default)}
                         onChange={(e) => setConfig((c) => ({ ...c, [f.name]: e.target.checked }))} />
                : <span className="fieldrow">
                    <input type="text" value={String(config[f.name] ?? f.default ?? "")}
                           placeholder={f.placeholder ?? ""}
                           onChange={(e) => setConfig((c) => ({ ...c, [f.name]: e.target.value }))} />
                    {f.name === "root" || f.name === "project"
                      ? <button className="mini" onClick={() => pickDir(f.name)}>…</button>
                      : null}
                  </span>}
            </label>
          ))}

          <label>
            Model endpoint (any OpenAI-compatible one)
            <input type="text" value={String(config["base_url"] ?? "http://localhost:11434/v1")}
                   onChange={(e) => setConfig((c) => ({ ...c, base_url: e.target.value }))} />
          </label>
          <label>
            Model
            <input type="text" value={String(config["model"] ?? "qwen2.5:7b")}
                   onChange={(e) => setConfig((c) => ({ ...c, model: e.target.value }))} />
          </label>
          <label>
            API key: the NAME of the env var holding it
            <input type="text" value={String(config["api_key_env"] ?? "OPENAI_API_KEY")}
                   onChange={(e) => setConfig((c) => ({ ...c, api_key_env: e.target.value }))} />
          </label>

          <label className="goal-label">Goal</label>
          <textarea value={goal} placeholder="what should the engine find out or reach?"
                    onChange={(e) => setGoal(e.target.value)} />
          <div className="row">
            <button className="run" disabled={status !== "ready" || !goal.trim()} onClick={run}>Run</button>
            <button className="deny" disabled={status !== "running"} onClick={stop}>Stop</button>
          </div>
        </aside>

        <section>
          {settled && (
            <div className="panel" id="outcome">
              <h2>{settled["error"] ? "error" : settled["answer"] ? "settled" : "stopped"}</h2>
              <pre>{String(settled["answer"] ?? settled["reason"] ?? settled["error"] ?? "")}</pre>
              <pre className="summary">{String(settled["summary"] ?? "")}</pre>
              {settled["learned"] ? <pre className="summary">{String(settled["learned"])}</pre> : null}
              {settled["record"] ? <details><pre className="summary">{String(settled["record"])}</pre></details> : null}
            </div>
          )}
          <MazeMap events={events} />
          <div className="panel grow">
            <h2>the run, event by event</h2>
            <div className="stream">
              {events.length === 0 && status === "running" ? <p className="note">thinking…</p> : null}
              {events.map((e, i) => (
                <div key={i} className={`ev k-${e.kind}`}
                     style={{ borderLeftColor: kindColor[e.kind] ?? "#242a36" }}>
                  <span className="h">#{e.seq} · {e.t_ms}ms · {e.kind}</span>
                  {"\n"}
                  {e.kind === "candidates"
                    ? (e["moves"] as { label: string; why: string }[])?.map((m, j) =>
                        <div key={j}>{m.label}{m.why ? ` — ${m.why}` : ""}</div>)
                    : e.kind === "probe"
                      ? `${e["ok"] ? "ok" : "FAILED"} ${e["move"]}${e["predicted"] ? " (predicted)" : ""}\n${String(e["excerpt"] ?? "")}`
                      : String(e["reason"] ?? e["answer"] ?? e["move"] ?? "")}
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
      <ConfirmDialog request={confirm} onAnswer={answer} />
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
