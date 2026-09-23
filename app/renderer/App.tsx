/*
 * The window.
 *
 * Three views over one run: Run (a live or loaded run, driven by one cursor), Library (every run kept),
 * Compare (two of them at once). The rule the whole layout follows is that the visualization is the
 * product — map, tree and ledger take the screen, and the config that produced them is one toggle away.
 *
 * The cursor is the only piece of state shared between panels. Clicking a ledger row, a tree node or the
 * scrubber all move it, and the map, the tree, the ledger and the inspector are all projections of it, so
 * there is no such thing as a panel being "out of sync" with another. That is what makes playback
 * possible without a recording, and comparison possible without running anything twice.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArtifactMeta, RunArtifact } from "./core/types";
import { MODELS, modelSummary } from "./core/models";
import { project } from "./core/project";
import { useSidecar } from "./hooks/useSidecar";
import { usePlayback } from "./hooks/usePlayback";
import { ModelConfig } from "./shell/ConfigDrawer";
import { ConfigDrawer } from "./shell/ConfigDrawer";
import { CommandBar } from "./shell/CommandBar";
import { ConfirmDialog } from "./shell/ConfirmDialog";
import { TopRail, View } from "./shell/TopRail";
import { Transport } from "./shell/Transport";
import { ComparePanel } from "./panels/ComparePanel";
import { LibraryPanel } from "./panels/LibraryPanel";
import { LogPanel } from "./panels/LogPanel";
import { MapPanel } from "./panels/MapPanel";
import { TreePanel } from "./panels/TreePanel";
import { formatElapsed, pct } from "./core/format";

export function App() {
  const [view, setView] = useState<View>("run");
  const [world, setWorld] = useState("maze");
  const [goal, setGoal] = useState("");
  const [values, setValues] = useState<Record<string, string | boolean>>({});
  const [model, setModel] = useState<ModelConfig>({ ...MODELS.defaults });
  const [configOpen, setConfigOpen] = useState(false);

  const [library, setLibrary] = useState<ArtifactMeta[]>([]);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [left, setLeft] = useState<RunArtifact | null>(null);
  const [right, setRight] = useState<RunArtifact | null>(null);
  const [pendingSide, setPendingSide] = useState<"left" | "right" | null>(null);
  const [focus, setFocus] = useState<string | null>(null);

  // The playback hook needs the decision count before the run it belongs to exists; the run's events
  // arrive first and the count follows, so the hook is fed the count it currently has and clamps.
  const [bookmarks, setBookmarks] = useState<number[]>([]);
  const session = useSidecar(bookmarks);
  const { status, worlds, events, settled, confirm, headless } = session;

  const projection = useMemo(() => project(events, Number.MAX_SAFE_INTEGER), [events]);
  const playback = usePlayback(projection.decisions.length);
  const shown = useMemo(() => project(events, playback.cursor), [events, playback.cursor]);

  // A new run starts a new timeline: cursor at the end, no bookmarks carried over.
  const [timeline, setTimeline] = useState<string>("");
  useEffect(() => {
    const key = `${world}|${settled?.events ?? 0}|${events.length > 0 ? events[0].t_ms : 0}|${events[0]?.seq ?? -1}`;
    if (timeline === key) return;
    setTimeline(key);
    playback.reset(events.length === 0 ? [] : undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events.length, world, settled]);

  useEffect(() => {
    if (playback.bookmarks !== bookmarks) setBookmarks(playback.bookmarks);
  }, [playback.bookmarks, bookmarks]);

  const refreshLibrary = useCallback(async () => {
    setLoadingLibrary(true);
    try { setLibrary(await session.library.list()); } finally { setLoadingLibrary(false); }
  }, [session.library]);

  useEffect(() => { void refreshLibrary(); }, [refreshLibrary]);
  // A finished run lands in the library the moment it settles.
  useEffect(() => { if (settled) void refreshLibrary(); }, [settled, refreshLibrary]);

  useEffect(() => {
    if (worlds.length > 0 && !worlds.some((w) => w.name === world)) setWorld(worlds[0].name);
  }, [worlds, world]);

  const current = worlds.find((w) => w.name === world);
  const running = status === "running";

  // The world's own fields come from the sidecar's registry, so a new world in the server becomes a form
  // here without this file knowing anything about it.
  const worldValues = useMemo(() => {
    const out: Record<string, string | boolean> = {};
    for (const f of current?.fields ?? []) {
      out[f.name] = values[f.name] ?? f.default;
    }
    return out;
  }, [current, values]);

  const runConfig = useMemo(() => ({
    ...worldValues,
    base_url: model.base_url,
    model: model.model,
    api_key_env: model.api_key_env,
  }), [worldValues, model]);

  const blocked = status === "crashed" ? "the sidecar is not running — restart the app"
    : status === "connecting" ? "reaching the sidecar…"
      : running ? "a run is already in flight"
        : goal.trim() ? "" : "type a goal to run";

  const start = useCallback(() => {
    if (blocked) return;
    setConfigOpen(false);
    setView("run");
    setBookmarks([]);
    void session.run(goal.trim(), world, runConfig);
  }, [blocked, goal, session, world, runConfig]);

  // The keys a person actually reaches for. Global, so they work wherever the focus happens to be — except
  // in a text field, where the arrows and space belong to the cursor.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target !== null && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable);
      if (typing) return;
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); start(); return; }
      if (e.key === "l" && !e.metaKey && !e.ctrlKey) { setView((v) => (v === "library" ? "run" : "library")); }
      if (e.key === "c" && !e.metaKey && !e.ctrlKey) { setView((v) => (v === "compare" ? "run" : "compare")); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [start]);

  const openRun = useCallback(async (id: string) => {
    const artifact = await session.library.load(id);
    if (!artifact) return;
    session.open(artifact);
    setBookmarks(artifact.bookmarks);
    playback.reset(artifact.bookmarks);
    setView("run");
  }, [session, playback]);

  const deleteRun = useCallback(async (id: string) => {
    await session.library.remove(id);
    setPicked((p) => p.filter((x) => x !== id));
    await refreshLibrary();
  }, [session.library, refreshLibrary]);

  const pickForCompare = useCallback(async (side: "left" | "right") => {
    if (picked.length === 0) { setView("library"); setPendingSide(side); return; }
    const ids = picked.filter((id) => id !== (side === "left" ? left?.id : right?.id));
    const choice = ids[ids.length - 1] ?? picked[picked.length - 1];
    const artifact = await session.library.load(choice);
    if (!artifact) return;
    if (side === "left") setLeft(artifact); else setRight(artifact);
    setView("compare");
  }, [picked, left, right, session.library]);

  const startComparison = useCallback(async (ids: [string, string]) => {
    const a = await session.library.load(ids[0]);
    const b = await session.library.load(ids[1]);
    setLeft(a); setRight(b); setView("compare");
  }, [session.library]);

  // Selecting in the library while a compare slot is waiting fills it and leaves for the comparison.
  useEffect(() => {
    if (pendingSide === null || picked.length === 0) return;
    const side = pendingSide;
    setPendingSide(null);
    const id = picked[picked.length - 1];
    void session.library.load(id).then((artifact) => {
      if (!artifact) return;
      if (side === "left") setLeft(artifact); else setRight(artifact);
      setView("compare");
    });
  }, [pendingSide, picked, session.library]);

  const lastMs = events.length > 0 ? events[events.length - 1].t_ms : 0;

  return (
    <div className="app">
      <TopRail
        view={view}
        onView={(v) => { setView(v); if (v === "library") void refreshLibrary(); }}
        status={status}
        running={running}
        libraryCount={library.length}
        configOpen={configOpen}
        onConfig={() => setConfigOpen((v) => !v)}
        readouts={[
          { label: "step", value: projection.decisions.length === 0 ? "—" : `${Math.min(playback.cursor + 1, projection.decisions.length)}/${projection.decisions.length}` },
          { label: "progress", value: pct(shown.progress) },
          { label: "facts", value: shown.at?.facts.length ?? 0 },
          { label: "belief", value: shown.trust.points.length === 0 ? "—" : pct(shown.trust.mean) },
          { label: "elapsed", value: formatElapsed(lastMs) },
        ]}
      />

      {view !== "compare" ? (
        <CommandBar
          worlds={worlds} world={world} onWorld={setWorld}
          goal={goal} onGoal={setGoal}
          onRun={start} onStop={session.stop} running={running}
          blocked={blocked}
          hint={blocked || (running ? "streaming — the panels follow the newest step" : current?.note ?? "")}
          configOpen={configOpen}
        />
      ) : null}

      {configOpen && view !== "compare" ? (
        <ConfigDrawer
          worlds={worlds} world={world}
          fields={current?.fields ?? []}
          values={worldValues} set={(name, value) => setValues((v) => ({ ...v, [name]: value }))}
          model={model} setModel={(name, value) => setModel((m) => ({ ...m, [name]: value }))}
          modelLabels={MODELS.labels}
          onPick={async () => {
            const dir = await session.pickDirectory();
            if (!dir) return;
            const key = world === "ledger" ? "project" : "root";
            setValues((v) => ({ ...v, [key]: dir }));
          }}
          headless={headless}
        />
      ) : null}

      {view === "run" ? (
        <main className="stage">
          <MapPanel knowledge={shown.knowledge} decisions={shown.decisions} world={world} events={events}
                    liveStep={playback.cursor} focus={{ cell: focus, onFocus: setFocus, onPin: setFocus }} />

          <div className="pane right">
            <section className="pane" aria-label="search tree">
              <TreePanel tree={shown.tree} decisions={shown.decisions} cursor={playback.cursor} onSeek={playback.at} />
            </section>
            <section className="pane" aria-label="decision ledger">
              <LogPanel decisions={shown.decisions} trust={shown.trust} cursor={playback.cursor}
                        bookmarks={playback.bookmarks} onSeek={playback.at} onBookmark={playback.toggleBookmark} />
            </section>
          </div>
        </main>
      ) : view === "library" ? (
        <main className="stage" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
          <LibraryPanel
            metas={library} loading={loadingLibrary} persisted={!headless}
            selected={picked}
            onSelect={(id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id].slice(-2)))}
            onOpen={(id) => void openRun(id)}
            onDelete={(id) => void deleteRun(id)}
            onCompare={(ids) => void startComparison(ids)}
            onRefresh={() => void refreshLibrary()}
          />
        </main>
      ) : (
        <main className="stage" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
          <ComparePanel
            left={left} right={right}
            onPick={(side) => void pickForCompare(side)}
            onExit={() => setView("run")}
          />
        </main>
      )}

      {view === "run" ? (
        <Transport
          playback={playback}
          decisions={projection.decisions}
          durationMs={lastMs}
          live={running}
          label={`${world} · ${modelSummary({ ...model, ...worldValues })}`}
        />
      ) : null}

      <ConfirmDialog request={confirm} onAnswer={session.answer} />
    </div>
  );
}
