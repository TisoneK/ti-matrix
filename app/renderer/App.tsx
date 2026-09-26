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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArtifactMeta, RunArtifact } from "./core/types";
import { Budget, MODELS, budgetFor, isBuiltin, modelSummary } from "./core/models";
import { project } from "./core/project";
import { useSidecar } from "./hooks/useSidecar";
import { usePlayback } from "./hooks/usePlayback";
import { useWindowChrome } from "./hooks/useWindowChrome";
import { ModelConfig } from "./shell/ConfigDrawer";
import { ConfigDrawer } from "./shell/ConfigDrawer";
import { CommandBar } from "./shell/CommandBar";
import { ConfirmDialog } from "./shell/ConfirmDialog";
import { TopRail } from "./shell/TopRail";
import { View, toRunning, toView, toggleConfig, shortcutsLive } from "./core/nav";
import { Welcome } from "./shell/Welcome";
import { Transport } from "./shell/Transport";
import { ComparePanel } from "./panels/ComparePanel";
import { LibraryPanel } from "./panels/LibraryPanel";
import { LogPanel } from "./panels/LogPanel";
import { MapPanel } from "./panels/MapPanel";
import { TreePanel } from "./panels/TreePanel";
import { formatElapsed, formatTokens, outcomeLabel, outcomeTone, pct } from "./core/format";
import { loadSettings, saveSettings } from "./core/settings";

/** Below this, a run finished faster than anyone could have watched it stream — see the timeline effect. */
const AUTO_REPLAY_MS = 1500;

export function App() {
  const [view, setView] = useState<View>("run");
  const [world, setWorld] = useState("maze");
  const [goal, setGoal] = useState("");
  const [values, setValues] = useState<Record<string, string | boolean>>({});
  const [model, setModel] = useState<ModelConfig>({ ...MODELS.defaults });
  const [budget, setBudgetState] = useState<Budget>(budgetFor(MODELS.defaults.model));
  const [configOpen, setConfigOpen] = useState(false);
  /** The pasted key, for this session only — never saved, never sent anywhere but the sidecar. */
  const [apiKey, setApiKey] = useState("");
  /** True once stored settings have been read, so hydration does not race the first save. */
  const [hydrated, setHydrated] = useState(false);
  /** The first-run welcome: shown until dismissed (or a run exists), and never again after that. */
  const [welcomeSeen, setWelcomeSeen] = useState(false);
  // On by default: the benchmark has a warm run settling the same goals in half the rounds.
  const [remember, setRemember] = useState(true);

  const [library, setLibrary] = useState<ArtifactMeta[]>([]);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [left, setLeft] = useState<RunArtifact | null>(null);
  const [right, setRight] = useState<RunArtifact | null>(null);
  const [pendingSide, setPendingSide] = useState<"left" | "right" | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  /** The shared cursor: hover a ledger row, a tree node, or a map cell, and all three answer.
   * One string, one meaning — the decision index under the pointer — null when nowhere. */
  const [hover, setHover] = useState<number | null>(null);

  // The playback hook needs the decision count before the run it belongs to exists; the run's events
  // arrive first and the count follows, so the hook is fed the count it currently has and clamps.
  const [bookmarks, setBookmarks] = useState<number[]>([]);
  const session = useSidecar(bookmarks);
  const { status, worlds, events, settled, confirm, headless } = session;
  const chrome = useWindowChrome();

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
    // A run that settles before a person could watch it stream live — `builtin` routinely finishes a
    // whole maze in under half a second — lands with the map, tree and ledger already at their final
    // state. That is indistinguishable, to someone who just clicked Run, from nothing having happened:
    // this is what "the button changes and goes back to Run, but nothing happens" turned out to be, live
    // over the app's own window, not a report. Below the threshold, autoplay the recorded decisions once
    // at a watchable pace instead of silently landing at the end; a run slow enough to have been watched
    // live (any real network call reliably clears it) is left where it is, since replaying it would only
    // repeat what they already saw happen.
    const finishedMs = events.length > 0 ? events[events.length - 1].t_ms : 0;
    if (settled && !settled.error && events.length > 0 && finishedMs > 0 && finishedMs < AUTO_REPLAY_MS) {
      playback.toggle();
    }
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

  // What the user set last time is what they see this time: hydrate once, before anything is saved.
  useEffect(() => {
    void loadSettings().then((s) => {
      if (s) {
        if (s.model) setModel((m) => ({ ...m, ...s.model }));
        if (s.world) setWorld(s.world);
        if (s.values) setValues(s.values);
        if (s.goal) setGoal(s.goal);
        if (s.budget) setBudgetState((b) => ({ ...b, ...s.budget }));
        if (s.welcomeSeen) setWelcomeSeen(true);
        if (typeof s.remember === "boolean") setRemember(s.remember);
      }
      setHydrated(true);
    });
  }, []);

  // The budget belongs to whoever is deciding. Rules run eighty steps in a blink; the same eighty against
  // a paid endpoint is twenty minutes and a bill, so crossing between the two carries the budget with it
  // rather than leaving the other one's numbers in the box. Only the crossing does this — a number typed
  // by hand stays typed, because this fires on the change of seat, not on every render.
  const seat = isBuiltin(model.model);
  const lastSeat = useRef<boolean | null>(null);
  useEffect(() => {
    if (!hydrated) return;
    if (lastSeat.current === null) { lastSeat.current = seat; return; }
    if (lastSeat.current === seat) return;
    lastSeat.current = seat;
    setBudgetState(budgetFor(model.model));
  }, [seat, hydrated, model.model]);

  // And every change is kept — debounced, so typing writes one file, not one per keystroke.
  useEffect(() => {
    if (!hydrated) return;
    const t = window.setTimeout(() => {
      saveSettings({ model, world, values, goal, budget, welcomeSeen, remember });
    }, 500);
    return () => window.clearTimeout(t);
  }, [hydrated, model, world, values, goal, budget, welcomeSeen, remember]);

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
    // A key pasted for this session rides with the run config; it is never written to settings and is
    // stripped from the saved artifact (see useSidecar). Absent, the env-var name above is what counts.
    ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
  }), [worldValues, model, apiKey]);

  // Why the button is unavailable, said as precisely as the app actually knows. `session.trouble` is the
  // reason main or the socket gave — a missing python, an engine that exited, a page opened outside the
  // app — and it beats the old blanket "restart the app", which was wrong for most of those.
  const blocked = status === "crashed"
    ? (session.trouble ?? "the engine is not running")
    : status === "reconnecting" ? "the engine dropped — reconnecting…"
      : status === "connecting" ? "starting the engine…"
        : running ? "a run is already in flight"
          : !goal.trim() ? "type a goal to run"
            // Builtin needs no endpoint at all; anything else does, and the sidecar rejects a run with
            // neither — but only after zero events, which used to look identical to never having clicked
            // Run (see the lamp fix above). Catching it here means the common slip (picking "a language
            // model" and never typing one in) never reaches the sidecar to be silent about at all.
            : !isBuiltin(model.model) && !model.model.trim() ? "type a model name (or switch to Built-in rules)"
              : "";
  // Trying again only helps when there is something to try: inside the app, with the socket down.
  const retryable = (status === "crashed" || status === "reconnecting") && !session.headless;

  const start = useCallback(() => {
    if (blocked) return;
    const next = toRunning({ view, configOpen });
    setConfigOpen(next.configOpen);
    setView(next.view);
    setBookmarks([]);
    void session.run(goal.trim(), world, runConfig, { ...budget }, remember);
  }, [blocked, goal, session, world, runConfig, budget, view, configOpen, remember]);

  // The keys a person actually reaches for. Global, so they work wherever the focus happens to be — except
  // in a text field, where the arrows and space belong to the cursor.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target !== null && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable);
      if (typing) return;
      // A single unmodified letter is a cheap shortcut, which makes it a cheap way to change the view
      // out from under something that is waiting for an answer: the confirmer blocks a run and must be
      // answered, the setup sheet and the welcome own the screen while they are up. Esc is how those
      // close; `l` and `c` are not, and a view that changed behind one of them reads as the nav firing
      // on its own.
      const blocking = document.querySelector(".scrim, .drawer, .welcome") !== null;
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); start(); return; }
      if (!shortcutsLive(blocking, { alt: e.altKey, meta: e.metaKey, ctrl: e.ctrlKey })) return;
      if (e.key === "l") { setView((v) => (v === "library" ? "run" : "library")); }
      if (e.key === "c") { setView((v) => (v === "compare" ? "run" : "compare")); }
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

  /**
   * What the rail's lamp says. The socket's `ready` covers four different situations — nothing run
   * yet, a run that just answered, a run that gave up, and a saved run opened from the library — and
   * it used to render all four as "idle", which is a machine's word for "no work queued" and told a
   * person nothing. Once there is a run on screen, the lamp reports how *it* ended.
   */
  const lamp = useMemo((): { detail?: string; tone?: "ok" | "warn" | "bad" } => {
    if (running) return { detail: "running" };
    if (status !== "ready") return {};
    const done = session.settled;
    if (!done) return {};
    // A config the sidecar rejects outright (an empty model name, say) never reaches a single event —
    // engine.run() never starts — so the events.length gate below must not swallow it: that gate exists
    // to hide a PREVIOUS run's stale lamp before the next run's first event arrives, not to hide a
    // rejection that has no events to wait for in the first place. Showing only "failed" for it (the
    // previous behavior) was indistinguishable from the idle, never-run state — the actual reason is
    // the one thing worth a person's time here.
    if (done.error) return { detail: done.error, tone: "bad" };
    if (events.length === 0) return {};
    const settledOk = done.answer !== null && done.reason === null;
    return { detail: outcomeLabel(settledOk, done.reason), tone: outcomeTone(settledOk, done.reason) };
  }, [running, status, events.length, session.settled]);

  const lastMs = events.length > 0 ? events[events.length - 1].t_ms : 0;

  return (
    <div className="app">
      <TopRail
        view={view}
        onView={(v) => {
          const next = toView({ view, configOpen }, v);
          setView(next.view);
          setConfigOpen(next.configOpen);
          if (next.view === "library") void refreshLibrary();
        }}
        status={status}
        running={running}
        lamp={lamp}
        libraryCount={library.length}
        configOpen={configOpen}
        onConfig={() => {
          const next = toggleConfig({ view, configOpen });
          setView(next.view);
          setConfigOpen(next.configOpen);
        }}
        chrome={chrome}
        // The readouts describe *the* run — one cursor, one map, one belief. On Compare there are two
        // runs and no single answer to "step", and on an empty Run view there is no run at all, so a
        // rail reading `step — · progress 0% · elapsed 0ms` is five slots of furniture claiming to be
        // measurements. They appear when there is something to measure.
        readouts={view === "compare" || events.length === 0 ? [] : [
          { label: "step", value: projection.decisions.length === 0 ? "—" : `${Math.min(playback.cursor + 1, projection.decisions.length)}/${projection.decisions.length}` },
          { label: "progress", value: pct(shown.progress) },
          { label: "facts", value: shown.at?.facts.length ?? 0 },
          { label: "belief", value: shown.trust.points.length === 0 ? "—" : pct(shown.trust.mean) },
          { label: "elapsed", value: formatElapsed(lastMs) },
          // Only a hosted run has anything to report — `builtin` spends no tokens, and it shows up
          // once the run has settled, the same moment the other readouts stop moving.
          ...(session.settled?.usage ? [{ label: "tokens", value: formatTokens(session.settled.usage.total_tokens) }] : []),
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
          onRetry={session.retry} retryable={retryable}
        />
      ) : null}

      {/* `view !== "compare"` is belt and braces: onConfig/onView above keep the two in step, and this
          makes the invariant local to where the sheet is actually drawn. */}
      {configOpen && view !== "compare" ? (
        <ConfigDrawer
          worlds={worlds} world={world}
          fields={current?.fields ?? []}
          values={worldValues} set={(name, value) => setValues((v) => ({ ...v, [name]: value }))}
          model={model} setModel={(name, value) => setModel((m) => ({ ...m, [name]: value }))}
          modelLabels={MODELS.labels}
          apiKey={apiKey} setApiKey={setApiKey}
          budget={budget} setBudget={(name, value) => setBudgetState((b) => ({ ...b, [name]: value }))}
          remember={remember} setRemember={setRemember}
          onPick={async () => {
            const dir = await session.pickDirectory();
            if (!dir) return;
            const key = "root";
            setValues((v) => ({ ...v, [key]: dir }));
          }}
          headless={headless}
          onClose={() => setConfigOpen(false)}
          models={session.models} modelsLoading={session.modelsLoading} modelsError={session.modelsError}
          onFetchModels={() => session.fetchModels(model.base_url, apiKey, model.api_key_env)}
          onClearModels={session.clearModels}
        />
      ) : null}

      {view === "run" ? (
        <main className="stage">
          {projection.decisions.length === 0 && status !== "running" && !welcomeSeen ? (
            <Welcome onConfigure={() => { setWelcomeSeen(true); setConfigOpen(true); }} onDismiss={() => setWelcomeSeen(true)} />
          ) : (
            <>
              <MapPanel knowledge={shown.knowledge} decisions={shown.decisions} world={world} events={events}
                        liveStep={playback.cursor} focus={{ cell: focus, onFocus: setFocus, onPin: setFocus }}
                        hoverCell={hover === null ? null : shown.decisions[hover]?.cell ?? null} />

          <div className="pane right">
            <section className="pane" aria-label="search tree">
              <TreePanel tree={shown.tree} decisions={shown.decisions} cursor={playback.cursor} onSeek={playback.at}
                         onHover={setHover} peek={hover} />
            </section>
            <section className="pane" aria-label="decisions">
              <LogPanel decisions={shown.decisions} trust={shown.trust} cursor={playback.cursor}
                        bookmarks={playback.bookmarks} onSeek={playback.at} onBookmark={playback.toggleBookmark}
                        onHover={setHover} peek={hover} />
            </section>
            </div>
            </>
          )}
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
