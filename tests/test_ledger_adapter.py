"""Adapter #3 — a repository's Context Ledger — must read the vault's real formats, and write back into
them without ever inventing a shape.

The fixture below is a small but *faithful* vault: every file keeps the `<!-- -->` template comment the
schema's templates carry, because those comments are where the traps are. A placeholder mentioned only
in a comment is not data (upstream, a `Status: accepted | superseded by ADR-M` placeholder leaking out of
a comment into a generated digest was a real shipped bug), and a file's fields are update-in-place, so
the last `- **Key:** value` is the current one. Both are asserted here.
"""
from __future__ import annotations

import json

import pytest

from ti_matrix import EngineBudget, Goal, LLMEvaluator, LLMMoveProposer, LLMSimulator, StateEngine
from ti_matrix.adapters.context_ledger import (
    LEDGER_ACTIONS,
    LEDGER_READ_ACTIONS,
    LEDGER_WRITE_ACTIONS,
    LedgerEnvironment,
    LedgerRecorder,
    LedgerVault,
)
from ti_matrix.protocols import Action

TODAY = "2026-09-22"

@pytest.fixture()
def env(project):
    return LedgerEnvironment(project)


async def look(env, tool, **args):
    return await env.probe(Action(tool, args))


# ─── the contract the engine relies on ──────────────────────────────────────


def test_the_read_actions_read_and_the_writes_are_declared_but_not_read_only(env):
    assert env.tools() and set(env.tools()) == set(LEDGER_ACTIONS)
    assert all(spec.read_only for spec in LEDGER_READ_ACTIONS.values())
    assert all(not spec.read_only for spec in LEDGER_WRITE_ACTIONS.values())
    assert set(LEDGER_ACTIONS) == set(LEDGER_READ_ACTIONS) | set(LEDGER_WRITE_ACTIONS)
    assert env.is_read_only(Action("brief", {})) is True
    assert env.is_read_only(Action("delete_everything", {})) is None  # not an action here


def test_a_vault_is_found_from_the_project_dir_or_the_ledger_dir(project):
    from_dir = LedgerVault(project)
    from_ledger = LedgerVault(project / ".context_ledger")
    assert from_dir.dir == from_ledger.dir and from_dir.exists()
    assert not LedgerVault(project / "elsewhere").exists()


# ─── reading: the parsers meet the real formats ─────────────────────────────


@pytest.mark.asyncio
async def test_brief_reports_the_live_office_and_leaks_no_template_placeholder(env):
    obs = await look(env, "brief")
    assert obs.ok and obs.predicted is False
    assert "protocol core 2.0.3" in obs.text
    assert "widen the beam" in obs.text  # the current task, from STATE.md
    assert "<name>" not in obs.text and "YYYY-MM-DD" not in obs.text  # the template stayed a template


@pytest.mark.asyncio
async def test_brief_falls_back_to_the_files_when_the_digest_was_never_generated(project):
    (project / ".context_ledger" / "memory" / "office" / "STATE.md").unlink()
    obs = await look(LedgerEnvironment(project), "brief")
    assert obs.ok and "STATE.md has not been generated" in obs.text
    assert "widen the beam" in obs.text and "Priya (S014, Working)" in obs.text


@pytest.mark.asyncio
async def test_open_tasks_keeps_the_priority_tables_apart_and_the_task_current(env):
    obs = await look(env, "open_tasks")
    assert obs.ok
    assert "the search strategy interface" in obs.text and "in-progress" in obs.text
    assert "Backlog — High (2):" in obs.text and "B-2026-09-21-4" in obs.text
    assert "Backlog — Medium (1):" in obs.text
    assert "Parking lot (not a queue): Findings 1" in obs.text


@pytest.mark.asyncio
async def test_the_decisions_report_keeps_the_real_status_not_the_comment_placeholder(env):
    listed = await look(env, "decisions")
    assert listed.ok and "2 decision(s) in force" in listed.text
    assert "ADR-7: Common Pitfalls stays inline (2026-09-18) — accepted" in listed.text
    assert "superseded by ADR-M" not in listed.text  # that line is a shape, not a status

    one = await look(env, "read_decision", number="7")
    assert one.ok and "keep the pitfalls inline" in one.text
    assert "**Status:** accepted" in one.text and "superseded by ADR-M" not in one.text

    missing = await look(env, "read_decision", number="99")
    assert missing.ok is False and "it holds: ADR-2, ADR-7" in missing.text


@pytest.mark.asyncio
async def test_recent_sessions_returns_the_newest_first_class_entries(env):
    obs = await look(env, "recent_sessions", limit=1)
    assert obs.ok and "The last 1 session(s)" in obs.text
    assert "Priya" in obs.text and "Amari" not in obs.text
    assert "partial — the interface is in" in obs.text


@pytest.mark.asyncio
async def test_friction_carries_the_workaround_and_says_so_when_a_log_is_clean(env):
    noise = await look(env, "friction", log="inefficiencies")
    assert noise.ok and "1 open inefficiencies entry" in noise.text
    assert "three PowerShell / Git-Bash traps" in noise.text
    assert "one variable at a time" in noise.text
    assert "~25 minutes lost" not in noise.text  # the cost is not what the next agent needs

    clean = await look(env, "friction", log="flaws")
    assert clean.ok and "no open flaws entries" in clean.text

    bad = await look(env, "friction", log="whatever")
    assert bad.ok is False and "unknown log" in bad.text


@pytest.mark.asyncio
async def test_search_finds_lines_and_keeps_closed_offices_out_of_the_default_scope(env):
    hits = await look(env, "search_memory", text="Git-Bash")
    assert hits.ok and "inefficiencies/log.md:" in hits.text

    default = await look(env, "search_memory", text="flaky")
    assert default.ok and "no line" in default.text  # history/ is out of the default scope
    deep = await look(env, "search_memory", text="flaky", scope="history")
    assert deep.ok and "history/office-001.md" in deep.text

    nothing = await look(env, "search_memory", text="zebra-quartz")
    assert nothing.ok and "no line" in nothing.text

    empty = await look(env, "search_memory", text="   ")
    assert empty.ok is False and "non-empty" in empty.text

    bad_scope = await look(env, "search_memory", text="x", scope="nowhere")
    assert bad_scope.ok is False and "unknown scope" in bad_scope.text


def test_an_entry_line_that_packs_several_fields_is_unpacked_and_bold_prose_is_not_a_field(project):
    """The registry packs Agent/Model/Platform/Core onto one bullet; a value ends at the next label.

    Found on the real vault: reading `- **Agent:** Omar | **Model:** …` as one field made `Agent` swallow
    the whole line. A `**bold phrase**` with no colon in it is prose, not a label.
    """
    sessions = project / ".context_ledger" / "memory" / "office" / "agents" / "sessions.md"
    sessions.write_text(
        "# Agent Sessions\n\n"
        "## 2026-09-19 — Session 15\n"
        "- **Agent:** Omar | **Model:** claude-sonnet-5 | **Platform:** macOS (local) | **Core:** 2.0.3\n"
        "- **Task:** audit the 2.0.0 pass\n"
        "- **Outcome:** done — and **Common Pitfalls** stays inline, because it is cross-referenced\n")

    entry = LedgerVault(project).sessions(1)[0]
    assert entry.get("Agent") == "Omar"
    assert entry.get("Model") == "claude-sonnet-5"
    assert entry.get("Platform") == "macOS (local)"
    assert entry.get("Core") == "2.0.3"
    assert entry.get("Task") == "audit the 2.0.0 pass"
    assert entry.get("Outcome") == "done — and **Common Pitfalls** stays inline, because it is cross-referenced"
    assert "Common Pitfalls" not in entry.fields  # prose, not a label


@pytest.mark.asyncio
async def test_list_and_read_memory_stay_inside_the_ledger(env):
    listing = await look(env, "list_memory")
    assert listing.ok and "memory/office/tasks/backlog.md" in listing.text

    read = await look(env, "read_memory", path="memory/user/preferences.md")
    assert read.ok and "terse reports" in read.text

    outside = await look(env, "read_memory", path="../../../../etc/passwd")
    assert outside.ok is False and "outside the ledger" in outside.text

    missing = await look(env, "read_memory", path="memory/nope.md")
    assert missing.ok is False and "not in this vault" in missing.text


@pytest.mark.asyncio
async def test_a_probe_never_raises_even_when_there_is_no_vault_at_all(tmp_path):
    blind = LedgerEnvironment(tmp_path / "not-a-project")
    for obs in [await look(blind, "brief"), await look(blind, "open_tasks"),
                await look(blind, "search_memory", text="x")]:
        assert obs.ok is False and "no bootstrapped Context Ledger" in obs.text
    bad_args = await look(blind, "brief", wrong_argument=1)
    assert bad_args.ok is False and "bad arguments" in bad_args.text


# ─── the loop: a run that reads the ledger and writes back what it learned ──


class ScriptedPort:
    """A ModelPort standing in for an endpoint: proposer JSON per round, then evaluator or simulator JSON."""

    def __init__(self, *rounds):
        self.rounds, self.i, self.prompts = list(rounds), 0, []

    async def complete(self, prompt: str, *, max_chars: int = 4000) -> str:
        self.prompts.append(prompt)
        moves, evals = self.rounds[min(self.i, len(self.rounds) - 1)]
        if '"ok": true, "result"' in prompt:  # the simulator's own instruction
            return json.dumps({"ok": True, "result": "a backlog row would be added", "why": "predicted"})
        if '"evals"' in prompt:
            self.i += 1
            return json.dumps({"evals": evals})
        return json.dumps({"moves": moves})


async def drive(env, goal, *rounds):
    """Run a real StateEngine — the real proposer, evaluator and JSON parsing — over the environment."""
    port = ScriptedPort(*rounds)
    engine = StateEngine(
        env,
        proposer=LLMMoveProposer(port, env.tools()),
        evaluator=LLMEvaluator(port),
        budget=EngineBudget(max_model_calls=8),
    )
    recorder = LedgerRecorder(env.vault, model="qwen2.5:7b")
    events = []
    async for ev in engine.run(Goal(goal)):
        recorder.observe(ev)
        events.append(ev)
    return events, recorder, engine


@pytest.mark.asyncio
async def test_a_run_orients_from_the_ledger_and_its_facts_survive_into_the_next_run(project):
    env = LedgerEnvironment(project)
    goal = "how many high-priority backlog rows are open right now?"
    events, recorder, _ = await drive(
        env, goal,
        ([{"tool": "open_tasks", "args": {}, "why": "the queue holds the answer"}],
         [{"i": 0, "progress": 1.0, "done": True,
           "answer": "2 high-priority rows: B-2026-09-14-1 and B-2026-09-21-4", "reason": "the queue"}]),
    )
    kinds = [e.kind for e in events]
    assert kinds[-1] == "done" and "candidates" in kinds and "probe" in kinds
    done = events[-1].data
    assert done["answer"].startswith("2 high-priority rows")
    assert not any(e.kind == "backtrack" for e in events)

    write = recorder.record()
    assert write.run_notes and not write.skipped
    assert write.findings  # the run's real facts were promoted
    assert "Dead ends, do not retry (0)" in recorder.run_block()  # nothing was tried and abandoned

    # The next run — a fresh environment, a fresh model — finds what this one established.
    later = LedgerEnvironment(project)
    found = await look(later, "search_memory", text=goal)
    assert found.ok and "sessions/notes.md" in found.text and "parking-lot.md" in found.text
    rows = later.vault.parking_lot()
    assert any("open_tasks()" in r.summary for r in rows if r.ident.startswith("P-"))


@pytest.mark.asyncio
async def test_a_fan_that_nothing_improves_ends_honestly_and_records_its_dead_ends(project):
    env = LedgerEnvironment(project)
    goal = "what colour is the bike shed?"
    events, recorder, _ = await drive(
        env, goal,
        ([{"tool": "open_tasks", "args": {}, "why": "look"}],
         [{"i": 0, "progress": 0.0, "done": False, "reason": "unrelated"}]),
    )
    last = events[-1]
    assert last.kind == "stopped" and last.data["settled"] is False
    write = recorder.record()
    assert write.run_notes

    block = recorder.run_block()
    assert "NOT settled" in block and f"stopped ({last.data['reason']})" in block
    assert "open_tasks()" in block  # the dead end names the action, not a fingerprint


@pytest.mark.asyncio
async def test_a_write_action_is_never_performed_however_it_is_reached(project, env):
    # Offered, and honestly marked as changing the vault — a real write is a host's move, not the search's.
    assert env.is_read_only(Action("add_backlog_row", {"summary": "x"})) is False
    assert env.tools()["add_backlog_row"].read_only is False

    direct = await env.probe(Action("add_backlog_row", {"summary": "x"}))
    assert direct.ok is False and "only reads" in direct.text

    before = {p: p.read_text() for p in (project / ".context_ledger").rglob("*.md")}
    goal, moves = "file a backlog row for the flaky test", [
        {"tool": "add_backlog_row", "args": {"summary": "flaky test"}, "why": "it has to be written"}]

    # Without a simulator the engine surfaces the action for confirmation and probes nothing.
    events, _, _ = await drive(env, goal, (moves, []))
    confirms = [e for e in events if e.kind == "needs_confirmation"]
    assert len(confirms) == 1 and confirms[0].data["move"] == "add_backlog_row(summary=flaky test)"
    assert not any(e.kind == "probe" for e in events)
    assert events[-1].kind == "stopped" and events[-1].data["settled"] is False

    # With one, the write is predicted and scored, and the run stops naming what it would need.
    port = ScriptedPort((moves, []))
    engine = StateEngine(env, proposer=LLMMoveProposer(port, env.tools()), evaluator=LLMEvaluator(port),
                         simulator=LLMSimulator(port), budget=EngineBudget(max_model_calls=6))
    seen = [ev async for ev in engine.run(Goal(goal))]
    last = seen[-1]
    assert last.kind == "stopped" and last.data["reason"] == "needs_action"
    assert last.data["needs"] == "add_backlog_row(summary=flaky test)"
    assert last.data["settled"] is False and last.data["predicted"]["ok"] is True

    assert {p: p.read_text() for p in (project / ".context_ledger").rglob("*.md")} == before


# ─── writing: append-only, deduped, and honest about what it could not do ────


@pytest.mark.asyncio
async def test_recording_appends_and_never_edits_what_the_office_already_had(project, tmp_path):
    env = LedgerEnvironment(project)
    notes = project / ".context_ledger" / "memory" / "office" / "sessions" / "notes.md"
    before = notes.read_text()
    _, recorder, _ = await drive(
        env, "how many decisions are in force?",
        ([{"tool": "decisions", "args": {}, "why": "count them"}],
         [{"i": 0, "progress": 1.0, "done": True, "answer": "2", "reason": "counted"}]),
    )
    write = recorder.record(day=TODAY)
    after = notes.read_text()
    assert write.run_notes.endswith("sessions/notes.md")
    assert after.startswith(before)  # append-only: what was there is untouched
    assert "(engine run)" in after and f"## {TODAY} — Ti Matrix / qwen2.5:7b (engine run)" in after
    assert "decision(s) in force" in after  # the observation is what got recorded


@pytest.mark.asyncio
async def test_findings_land_in_the_findings_table_and_continue_the_days_sequence(project):
    env = LedgerEnvironment(project)
    _, recorder, _ = await drive(
        env, "what is in flight?",
        ([{"tool": "open_tasks", "args": {}, "why": "read the queue"}],
         [{"i": 0, "progress": 1.0, "done": True, "answer": "the beam", "reason": "read"}]),
    )
    rows = recorder.finding_rows(day=TODAY)
    assert len(rows) == 1 and rows[0].startswith(f"| P-{TODAY}-2 |")  # -1 was already in the file
    write = recorder.record(day=TODAY)
    assert write.findings == (f"P-{TODAY}-2",)

    text = (project / ".context_ledger" / "memory" / "office" / "tasks" / "parking-lot.md").read_text()
    findings, questions = text.split("## Open questions")
    assert f"P-{TODAY}-2" in findings and "from the \"what is in flight?\"" in findings
    assert "P-" not in questions.split("## Deferred")[0]  # the other tables were left alone
    assert text.index(f"P-{TODAY}-2") < text.index("## Open questions")  # inside Findings, not after it


@pytest.mark.asyncio
async def test_a_fact_already_parked_is_not_parked_twice(project):
    env = LedgerEnvironment(project)
    _, recorder, _ = await drive(
        env, "what is in flight?",
        ([{"tool": "open_tasks", "args": {}, "why": "read the queue"}],
         [{"i": 0, "progress": 1.0, "done": True, "answer": "the beam", "reason": "read"}]),
    )
    first = recorder.record(day=TODAY)
    assert first.findings

    again = LedgerRecorder(env.vault, model="qwen2.5:7b")
    again.run.facts = list(recorder.run.facts)
    again.run.goal = recorder.run.goal
    assert again.finding_rows(day=TODAY) == []  # the same fact is already in the Findings table


def test_a_dry_run_writes_nothing(project):
    recorder = LedgerRecorder(project)
    recorder.run.goal, recorder.run.facts = "a goal", ["open_tasks() -> ok: 2 rows"]
    notes = project / ".context_ledger" / "memory" / "office" / "sessions" / "notes.md"
    before = notes.read_text()
    write = recorder.record(day=TODAY, dry_run=True)
    assert write.dry_run and not write.skipped and "a goal" in write.preview
    assert notes.read_text() == before
    recorder.record(day=TODAY)  # a dry run does not spend the recorder
    assert "a goal" in notes.read_text()


def test_one_recorder_records_one_run(project):
    """Appending the same block twice is the one thing the ledger's compaction rules exist to clean up."""
    recorder = LedgerRecorder(project)
    recorder.run.goal, recorder.run.facts = "a goal", ["open_tasks() -> ok: 2 rows"]
    assert recorder.record(day=TODAY).run_notes
    notes = project / ".context_ledger" / "memory" / "office" / "sessions" / "notes.md"
    after_first = notes.read_text()
    second = recorder.record(day=TODAY)
    assert second.run_notes == "" and "already recorded" in second.skipped[0]
    assert notes.read_text() == after_first


def test_a_fact_that_contains_a_table_is_not_allowed_to_split_the_row(project):
    recorder = LedgerRecorder(project)
    recorder.run.goal = "read the parking lot"
    recorder.run.facts = ["read_memory(path=x) -> ok: | ID | Summary |\n| P-1 | a thing |"]
    row = recorder.finding_rows(day=TODAY)[0]
    assert row.count("|") == 3  # the row's own three delimiters, and nothing the fact smuggled in
    assert "ID / Summary" in row and "\n" not in row
    write = recorder.record(day=TODAY)
    assert write.findings and len(project.joinpath(
        ".context_ledger/memory/office/tasks/parking-lot.md").read_text().splitlines()) > 0
    # and the vault's own parser still sees exactly one new row, with its summary intact
    rows = {r.ident: r.summary for r in LedgerVault(project).parking_lot()}
    assert "ID / Summary" in rows[f"P-{TODAY}-2"]


@pytest.mark.asyncio
async def test_record_reports_what_it_could_not_write_instead_of_creating_files(tmp_path):
    empty = tmp_path / "not-a-project"
    empty.mkdir()
    recorder = LedgerRecorder(empty)
    recorder.run.goal, recorder.run.facts = "a goal", ["brief() -> ok: something"]
    write = recorder.record()
    assert write.skipped and "not a bootstrapped Context Ledger" in write.skipped[0]
    assert "nothing was written" in write.to_text()
    assert not (empty / ".context_ledger").exists()  # a vault's file shapes are not ours to invent


def test_a_vault_without_the_notes_file_reports_that_rather_than_inventing_one(project):
    (project / ".context_ledger" / "memory" / "office" / "sessions" / "notes.md").unlink()
    recorder = LedgerRecorder(project)
    recorder.run.goal, recorder.run.facts = "a goal", ["brief() -> ok: something"]
    write = recorder.record(day=TODAY)
    assert write.run_notes == "" and any("notes.md" in s for s in write.skipped)
    assert not (project / ".context_ledger" / "memory" / "office" / "sessions" / "notes.md").exists()
    assert write.findings  # the findings still had a home
