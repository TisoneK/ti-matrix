"""The read half: what the engine may look at, and the writes it may only reason about.

Every read action is a question about a project's memory — what is in flight, what was decided, what the last
sessions hit, what a search turns up — and every answer is parsed and clipped rather than dumped, because a
model reads it inside one fan and pays for it out of the same budget as any other probe.

The writes are declared too, and deliberately marked `read_only=False`: a faithful picture of the vault
includes the actions that would change it, and the engine routes those to a Simulator or to
`needs_confirmation` — it never performs one. A host that wants a write to happen performs it itself, through
`LedgerRecorder`, on the run's own events.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from ti_matrix.adapters.context_ledger.parsing import _clip, _fields, _strip_comments
from ti_matrix.adapters.context_ledger.vault import SCOPES, LedgerVault, _CLIP, _OBS_MAX_CHARS
from ti_matrix.protocols import Action, ActionSpec, Observation

LEDGER_READ_ACTIONS: dict[str, ActionSpec] = {
    s.name: s
    for s in (
        ActionSpec("brief", "The project's orientation digest: standing params, who is working now, the "
                            "task in flight, open traps. Read this first.", "{}"),
        ActionSpec("open_tasks", "The work queue: the task in progress, the backlog by priority, and how "
                                 "much is parked.", "{}"),
        ActionSpec("decisions", "The architectural decisions in force (ADR number, title, date, status).",
                   '{"limit": 8}'),
        ActionSpec("read_decision", "One decision in full, by its ADR number.", '{"number": "7"}'),
        ActionSpec("recent_sessions", "What the last sessions did: agent, model, task, outcome, open items.",
                   '{"limit": 5}'),
        ActionSpec("friction", "Known traps and their workarounds: log 'flaws' (protocol friction) or "
                               "'inefficiencies' (project friction).", '{"log": "inefficiencies", "limit": 6}'),
        ActionSpec("search_memory", "Search the project's memory for a word or phrase; returns file:line "
                                    "hits. scope: memory | office | history | all.",
                   '{"text": "<phrase>", "scope": "memory"}'),
        ActionSpec("list_memory", "Which files this project's memory holds.", '{"scope": "memory"}'),
        ActionSpec("read_memory", "Read one ledger file (any path under the ledger directory).",
                   '{"path": "memory/user/preferences.md"}'),
    )
}

# Declared, never performed: these are what a person or a host would do afterwards.
LEDGER_WRITE_ACTIONS: dict[str, ActionSpec] = {
    s.name: s
    for s in (
        ActionSpec("add_backlog_row", "Add an actionable row to the work queue.",
                   '{"summary": "<what to do>"}', read_only=False),
        ActionSpec("log_inefficiency", "Log friction with this project's code, environment or dependencies.",
                   '{"problem": "...", "cost": "...", "workaround": "...", "prevent": "..."}', read_only=False),
        ActionSpec("record_decision", "Append an architectural decision (ADR) to the plans.",
                   '{"title": "...", "context": "...", "decision": "...", "consequences": "..."}',
                   read_only=False),
        ActionSpec("append_note", "Append a note to the office's session notes.", '{"text": "..."}',
                   read_only=False),
    )
}

LEDGER_ACTIONS: dict[str, ActionSpec] = {**LEDGER_READ_ACTIONS, **LEDGER_WRITE_ACTIONS}


class LedgerEnvironment:
    """Every action reads a Context Ledger vault. Nothing here can change one — including the writes it
    declares, which exist so the engine can reason about them and stop rather than perform one."""

    name = "context-ledger"

    def __init__(self, root: str | Path, actions: Optional[dict[str, ActionSpec]] = None) -> None:
        self.vault = LedgerVault(root)
        self._actions = actions if actions is not None else LEDGER_ACTIONS

    def tools(self) -> dict[str, ActionSpec]:
        return self._actions

    def is_read_only(self, action: Action) -> Optional[bool]:
        spec = self._actions.get(action.tool)
        return None if spec is None else spec.read_only

    async def probe(self, action: Action) -> Observation:
        spec = self._actions.get(action.tool)
        if spec is not None and not spec.read_only:  # defence in depth: never a write, whatever calls us
            return Observation(action, False,
                               f"{action.tool} would change the ledger, and this environment only reads "
                               f"(a host writes, from the run's own events)")
        try:
            return Observation(action, *getattr(self, f"_{action.tool}")(**action.args))
        except TypeError as exc:  # wrong or missing arguments — a failure the search can use
            return Observation(action, False, f"bad arguments for {action.tool}: {exc}")
        except Exception as exc:  # noqa: BLE001 — a failed probe is an observation, never a crash
            return Observation(action, False, f"{type(exc).__name__}: {exc}"[:400])

    # ── helpers ──

    @staticmethod
    def _int(value: Any, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(value)))
        except (TypeError, ValueError):
            return default

    def _unbootstrapped(self) -> tuple[bool, str]:
        return False, (f"no bootstrapped Context Ledger at {self.vault} — this needs "
                       f"`.context_ledger/memory/office/` to exist")

    def _missing(self, what: str) -> tuple[bool, str]:
        return False, f"{what} is not in this vault"

    def _scope(self, scope: Any) -> Optional[tuple[bool, str]]:
        return None if str(scope).strip().lower() in SCOPES else (
            False, f"unknown scope {str(scope)!r} — use one of: {', '.join(SCOPES)}")

    # ── the actions ──

    def _brief(self) -> tuple[bool, str]:
        if not self.vault.exists():
            return self._unbootstrapped()
        parts = [f"Context Ledger at {self.vault} — protocol core {self.vault.core_version() or 'unknown'}"]
        digest = self.vault.digest()
        if digest:
            parts.append(_strip_comments(digest).strip())
        else:
            # STATE.md is generated by the vault's own tooling; a vault without it still has the files.
            parts.append("(STATE.md has not been generated — reading the files directly)")
            task = self.vault.current_task()
            parts.append(f"Current task: {_clip(task.get('Task', 'unknown'), 240)} — {task.get('Status', '')}")
            backlog = self.vault.backlog()
            highs = [r for r in backlog if r.section.lower().startswith("high")]
            parts.append(f"Backlog: {len(backlog)} open, {len(highs)} high priority")
            parts.append("Live office: " + (", ".join(f"{r.name} ({r.codename}, {r.status})"
                                                      for r in self.vault.roster()) or "empty"))
        files = len(self.vault._files("memory"))
        closed = len(list(self.vault.history.glob("office-*.md"))) if self.vault.history.is_dir() else 0
        parts.append(f"(memory: {files} files; {closed} closed office record(s) in history/)")
        return True, "\n\n".join(parts)[:_OBS_MAX_CHARS]

    def _open_tasks(self) -> tuple[bool, str]:
        if not self.vault.exists():
            return self._unbootstrapped()
        task = self.vault.current_task()
        lines = [f"Current task: {_clip(task.get('Task', 'none recorded'), 240)} — {task.get('Status', '')}"]
        if task.get("Session"):
            lines.append(f"  session: {_clip(task['Session'], 120)}")
        backlog = self.vault.backlog()
        if not backlog:
            lines.append("Backlog: no open rows (or no backlog.md in this vault)")
        for section in ("High", "Medium", "Low"):
            rows = [r for r in backlog if r.section.lower().startswith(section.lower())]
            if rows:
                lines.append(f"Backlog — {section} ({len(rows)}):")
                lines += [f"  - {r.ident}: {_clip(r.summary, _CLIP)}" for r in rows[:6]]
        parked = self.vault.parking_lot()
        if parked:
            counts = ", ".join(f"{s} {len([r for r in parked if r.section == s])}"
                               for s in dict.fromkeys(r.section for r in parked))
            lines.append(f"Parking lot (not a queue): {counts}")
        return True, "\n".join(lines)[:_OBS_MAX_CHARS]

    def _decisions(self, limit: Any = 8) -> tuple[bool, str]:
        if not self.vault.exists():
            return self._unbootstrapped()
        found = self.vault.decisions()
        if not found:
            return self._missing("a decisions record (memory/office/plans/decisions.md)")
        lines = [f"{len(found)} decision(s) in force — respected, not relitigated:"]
        lines += [f"- ADR-{d.number}: {_clip(d.title, 120)} ({d.date}) — {d.status or 'no status line'}"
                  for d in found[-self._int(limit, 8, 1, 40):]]
        lines.append('Full text of one: read_decision {"number": "<n>"}')
        return True, "\n".join(lines)[:_OBS_MAX_CHARS]

    def _read_decision(self, number: Any = "") -> tuple[bool, str]:
        if not self.vault.exists():
            return self._unbootstrapped()
        want = re.sub(r"^[Aa][Dd][Rr][\s-]*", "", str(number).strip())
        found = self.vault.decisions()
        for d in found:
            if d.number == want:
                lines = [f"ADR-{d.number}: {d.title} ({d.date})"]
                lines += [f"- **{k}:** {v}" for k, v in _fields(_strip_comments(d.body)).items()]
                return True, "\n".join(lines)[:_OBS_MAX_CHARS]
        known = ", ".join("ADR-" + d.number for d in found) or "none"
        return False, f"no ADR {want!r} in this vault (it holds: {known})"

    def _recent_sessions(self, limit: Any = 5) -> tuple[bool, str]:
        if not self.vault.exists():
            return self._unbootstrapped()
        entries = self.vault.sessions(self._int(limit, 5, 1, 20))
        if not entries:
            return self._missing("a session registry (memory/office/agents/sessions.md)")
        lines = [f"The last {len(entries)} session(s) here:"]
        for e in entries:
            lines.append(f"- {e.heading}")
            for key in ("Agent", "Model", "Task", "Outcome", "Open items"):
                if e.get(key):
                    lines.append(f"    {key}: {_clip(e.get(key), _CLIP)}")
        return True, "\n".join(lines)[:_OBS_MAX_CHARS]

    def _friction(self, log: Any = "inefficiencies", limit: Any = 6) -> tuple[bool, str]:
        if not self.vault.exists():
            return self._unbootstrapped()
        which = str(log).strip().lower()
        if which not in ("flaws", "inefficiencies"):
            return False, f"unknown log {which!r} — use 'flaws' (protocol friction) or 'inefficiencies'"
        entries = self.vault.log_entries(which)
        if not entries:
            return True, f"no open {which} entries — the last sessions hit no logged friction there"
        shown = entries[-self._int(limit, 6, 1, 20):]
        lines = [f"{len(entries)} open {which} entr{'y' if len(entries) == 1 else 'ies'} "
                 f"(showing {len(shown)}):"]
        for e in shown:
            lines.append(f"- {e.date} — {e.who}")
            for key in ("Problem", "Workaround / fix", "Prevent next time"):
                if e.get(key):
                    lines.append(f"    {key}: {_clip(e.get(key), _CLIP)}")
        return True, "\n".join(lines)[:_OBS_MAX_CHARS]

    def _search_memory(self, text: Any = "", scope: Any = "memory") -> tuple[bool, str]:
        if not self.vault.exists():
            return self._unbootstrapped()
        if (bad := self._scope(scope)) is not None:
            return bad
        needle = str(text).strip()
        if not needle:
            return False, "search_memory needs a non-empty 'text' to look for"
        where = str(scope).strip().lower()
        hits, total = self.vault.search(needle, scope=where)
        if not hits:
            return True, f"no line in scope {where!r} contains {needle!r}"
        lines = [f"{total} line(s) in scope {where!r} contain {needle!r}"
                 + (f" (showing {len(hits)}):" if total > len(hits) else ":")]
        lines += [f"{rel}:{n}: {line}" for rel, n, line in hits]
        if where == "memory":
            lines.append("(closed offices under history/ are outside this scope — use scope='history')")
        return True, "\n".join(lines)[:_OBS_MAX_CHARS]

    def _list_memory(self, scope: Any = "memory") -> tuple[bool, str]:
        if not self.vault.exists():
            return self._unbootstrapped()
        if (bad := self._scope(scope)) is not None:
            return bad
        where = str(scope).strip().lower()
        files = self.vault._files(where)
        if not files:
            return False, f"nothing readable under scope {where!r} in this vault"
        lines = [f"{len(files)} file(s) in scope {where!r}:"]
        lines += [f"- {rel} ({p.stat().st_size} B)" for rel, p in files[:60]]
        if len(files) > 60:
            lines.append(f"… (+{len(files) - 60} more)")
        return True, "\n".join(lines)[:_OBS_MAX_CHARS]

    def _read_memory(self, path: Any = "") -> tuple[bool, str]:
        if not self.vault.exists():
            return self._unbootstrapped()
        rel = str(path).strip().lstrip("/")
        if not rel:
            return False, "read_memory needs a 'path' relative to the ledger directory"
        if self.vault.path(rel) is None:
            return False, f"{rel!r} points outside the ledger directory — refused"
        text = self.vault.read(rel)
        if text is None:
            return self._missing(f"{rel!r}")
        return True, f"{rel}:\n{text}"



def environment_for(root: str | Path) -> LedgerEnvironment:
    """The one-liner a host wants: the Context Ledger at ``root`` as an environment."""
    return LedgerEnvironment(root)


__all__ = [
    "LEDGER_ACTIONS",
    "LEDGER_READ_ACTIONS",
    "LEDGER_WRITE_ACTIONS",
    "LedgerEnvironment",
    "environment_for",
]
