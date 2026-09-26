/* The rail's transitions — the view and the setup sheet, which are not independent.
 *
 * The bug these hold down: `config` pressed on Compare flipped the button's caret, opened nothing, and
 * left `configOpen` true, so the sheet sprang open on the next view change. Pressing **Run** got you
 * the setup sheet. Every case below is one press and the state it must leave behind.
 */
import { Nav, canConfigure, escapeDismisses, shortcutsLive, toRunning, toView, toggleConfig } from "./nav";

let pass = 0;
const failures: string[] = [];
const eq = (what: string, got: unknown, want: unknown) => {
  if (JSON.stringify(got) === JSON.stringify(want)) { pass++; return; }
  failures.push(`${what}\n    got  ${JSON.stringify(got)}\n    want ${JSON.stringify(want)}`);
};

const run: Nav = { view: "run", configOpen: false };
const runOpen: Nav = { view: "run", configOpen: true };
const compare: Nav = { view: "compare", configOpen: false };

/* ── the sheet belongs to the run view ──────────────────────────────────── */

eq("compare cannot draw the setup sheet",
   [canConfigure("run"), canConfigure("library"), canConfigure("compare")], [true, true, false]);

eq("config on the run view is an ordinary toggle", toggleConfig(run), { view: "run", configOpen: true });
eq("and toggles back", toggleConfig(runOpen), { view: "run", configOpen: false });

eq("config from compare goes where the sheet lives, and opens it",
   toggleConfig(compare), { view: "run", configOpen: true });

/* ── the stuck state that made Run open the setup sheet ─────────────────── */

{
  // The exact sequence from the report: sheet open on run, cross to compare, come back.
  const onCompare = toView(runOpen, "compare");
  eq("crossing to compare closes the sheet rather than remembering it",
     onCompare, { view: "compare", configOpen: false });
  eq("so coming back to run does not spring it open",
     toView(onCompare, "run"), { view: "run", configOpen: false });
}

eq("the sheet survives a move between views that can draw it",
   toView(runOpen, "library"), { view: "library", configOpen: true });

eq("starting a run clears the sheet and shows the run",
   toRunning(runOpen), { view: "run", configOpen: false });
eq("starting from compare also lands on the run",
   toRunning({ view: "compare", configOpen: true }), { view: "run", configOpen: false });

/* ── a press is never a no-op ───────────────────────────────────────────── */

for (const from of [run, runOpen, compare, { view: "library", configOpen: true } as Nav]) {
  const after = toggleConfig(from);
  const changed = after.view !== from.view || after.configOpen !== from.configOpen;
  eq(`config from ${from.view}/${from.configOpen} changes something`, changed, true);
  // And it never claims to be open on a view that cannot draw it — the caret lied about this before.
  eq(`config from ${from.view}/${from.configOpen} leaves a drawable state`,
     after.configOpen ? canConfigure(after.view) : true, true);
}

/* ── bare-letter shortcuts ──────────────────────────────────────────────── */

eq("a bare letter works with nothing in the way", shortcutsLive(false, {}), true);
eq("but not behind the confirmer, the sheet or the welcome", shortcutsLive(true, {}), false);
eq("and not as part of a chord",
   [shortcutsLive(false, { alt: true }), shortcutsLive(false, { meta: true }), shortcutsLive(false, { ctrl: true })],
   [false, false, false]);

/* ── Escape, which the sheet's own bar advertises as "close (Esc)" ───────── */

// The reported bug: the sheet could not be dismissed from the state you are in after typing into it,
// because Escape was ignored wholesale whenever the focus sat in a text field.
eq("Escape closes from a text field — the state you are in after typing",
   escapeDismisses(false, "INPUT"), true);
eq("and from a textarea", escapeDismisses(false, "TEXTAREA"), true);
eq("and from anything that is not a control", escapeDismisses(false, "BODY"), true);
eq("and when there is no target at all", escapeDismisses(false, null), true);
// The only two things that get Escape first.
eq("an open dropdown keeps it — the browser closes its popup first",
   escapeDismisses(false, "SELECT"), false);
eq("an IME mid-word keeps it — Escape abandons the composition, not the sheet",
   escapeDismisses(true, "INPUT"), false);
eq("the tag's own case is not part of the rule", escapeDismisses(false, "select"), false);

console.log(`\n${pass} passed, ${failures.length} failed`);
if (failures.length) throw new Error("nav checks failed:\n" + failures.map((f) => "  ✗ " + f).join("\n"));
