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

/**
 * Whether Escape, pressed here, dismisses what is up.
 *
 * This file already said "Esc closes them" about the sheet and the welcome. The handler did not keep that
 * promise: it ignored Escape whenever the focus was in a text field, which is exactly where the focus is
 * after you type into the sheet — so the keyboard exit was dead in the one state a person is in when they
 * want out, while the sheet's own bar went on offering "close (Esc)" as the tooltip on its ✕. The comment
 * there said "mid-word", which reads as IME composition; the code was a tag-name test, and those are not
 * the same rule.
 *
 * Two things legitimately take Escape before the sheet does, and only two. An IME mid-composition, where
 * Escape abandons the composition rather than the sheet. And an open dropdown: the browser closes a
 * `select`'s popup first, so a `select` is the one control that owns the key here. Everything else — every
 * text field included — belongs to the sheet.
 */
export function escapeDismisses(composing: boolean, tagName: string | null): boolean {
  if (composing) return false;
  return (tagName ?? "").toUpperCase() !== "SELECT";
}
