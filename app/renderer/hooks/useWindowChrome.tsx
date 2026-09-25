/*
 * The window's chrome, as the rail draws it.
 *
 * The rail is the title bar — the name, the state and the way in are already there, so a second strip of
 * chrome above it would spend a strip of screen a run never gets back. The consequence is that dragging
 * and the window buttons are the rail's job now, and this hook is where the renderer learns how to do it:
 * which platform it is on (macOS keeps its traffic lights; everyone else gets the rail's own three
 * buttons) and whether the window is currently maximized, which decides whether the middle button means
 * maximize or restore.
 *
 * In a browser tab there is no window to control, so `available` is false and the rail draws no buttons.
 */

import { useCallback, useEffect, useState } from "react";
import { TmApi, WindowState } from "../protocol";

export interface WindowChrome {
  /** True when there is a real window behind this window — false when the renderer runs in a tab. */
  available: boolean;
  /** True on macOS, where the OS draws the controls and the rail only makes room for them. */
  nativeControls: boolean;
  maximized: boolean;
  minimize: () => void;
  toggleMaximize: () => void;
  close: () => void;
}

export function useWindowChrome(): WindowChrome {
  const tm = (window as unknown as { tm?: TmApi }).tm;
  const api = tm?.window;
  const nativeControls = tm?.platform === "darwin";
  const [state, setState] = useState<WindowState>({ maximized: false, fullScreen: false });

  useEffect(() => {
    if (!api) return;
    void api.state().then(setState);
    api.onState(setState);
  }, [api]);

  const minimize = useCallback(() => { void api?.minimize(); }, [api]);
  const toggleMaximize = useCallback(() => { void api?.toggleMaximize(); }, [api]);
  const close = useCallback(() => { void api?.close(); }, [api]);

  return { available: Boolean(api), nativeControls, maximized: state.maximized, minimize, toggleMaximize, close };
}

/**
 * The three glyphs, at 10×10 like every other mark in the app. Drawn rather than typed: a text "+" and a
 * text "–" do not line up, and the close cross is not a lowercase x.
 */
export function WindowGlyph({ kind }: { kind: "minimize" | "maximize" | "restore" | "close" }) {
  const common = { stroke: "currentColor", strokeWidth: 1.1, fill: "none", strokeLinecap: "round" as const };
  return (
    <svg width={10} height={10} viewBox="0 0 10 10" aria-hidden="true">
      {kind === "minimize" ? <path d="M2 5h6" {...common} /> : null}
      {kind === "maximize" ? <rect x={2.2} y={2.2} width={5.6} height={5.6} rx={0.8} {...common} /> : null}
      {kind === "restore" ? (
        <>
          <rect x={1.8} y={3.2} width={5} height={5} rx={0.8} {...common} />
          <path d="M3.6 3.2V2.4a0.8 0.8 0 0 1 0.8-0.8h3.4a0.8 0.8 0 0 1 0.8 0.8v3.4a0.8 0.8 0 0 1-0.8 0.8h-0.8" {...common} />
        </>
      ) : null}
      {kind === "close" ? <path d="M2.4 2.4l5.2 5.2M7.6 2.4l-5.2 5.2" {...common} /> : null}
    </svg>
  );
}
