/*
 * Where a nav press lands — the view and the setup sheet, decided together.
 *
 * These two pieces of state are not independent, and treating them as though they were is what made
 * the rail misbehave. The setup sheet is only ever drawn on the run view, so `config` pressed from
 * Compare used to flip the button's caret to ▴, open nothing, and leave `configOpen` true — and then
 * the sheet sprang open on the *next* view change, so pressing Run got you the setup sheet. A button
 * that does nothing and a button that does something else are the same bug seen one click apart.
 *
 * So the transition is one function of (where you are, what you pressed), it lives here rather than
 * inside a click handler, and `nav.test.ts` holds it down. The rule it encodes: the sheet belongs to
 * the run view, and any move that cannot show it closes it rather than remembering it.
 */

export type View = "run" | "library" | "compare";

export interface Nav {
  view: View;
  configOpen: boolean;
}

/** Views that can actually draw the setup sheet. Compare has no run to configure. */
export const canConfigure = (view: View): boolean => view !== "compare";

/** A tab press. The sheet survives only where it can be seen. */
export function toView(state: Nav, next: View): Nav {
  return { view: next, configOpen: state.configOpen && canConfigure(next) };
}

/**
 * The config press. On a view that draws the sheet this is an ordinary toggle; anywhere else it means
 * "I want the setup", so it goes where the setup lives and opens it — one press, what you meant.
 */
export function toggleConfig(state: Nav): Nav {
  if (!canConfigure(state.view)) return { view: "run", configOpen: true };
  return { ...state, configOpen: !state.configOpen };
}

/** Starting a run: the sheet gets out of the way, and the run view is the one that shows it happening. */
export const toRunning = (_state: Nav): Nav => ({ view: "run", configOpen: false });

/**
 * Whether a bare-letter shortcut may fire. The confirmer blocks a run and must be answered, and the
 * setup sheet and the welcome own the screen while they are up — a view that changed behind one of
 * those reads as the nav firing on its own. Esc closes them; `l` and `c` do not.
 */
export function shortcutsLive(blocking: boolean, modifiers: { alt?: boolean; meta?: boolean; ctrl?: boolean }): boolean {
  return !blocking && !modifiers.alt && !modifiers.meta && !modifiers.ctrl;
}
