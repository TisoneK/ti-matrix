<!-- Loaded per kickoff.md Phase 4's routing table: a new feature or a
substantial review. Local and cloud/sandbox agents differ here (a local
agent has a machine to run a dev server on; a cloud/sandbox agent
usually doesn't) — read your own subsection. -->

# Functional Testing

## Local agent

Per the Pre-Flight "Functional testing" parameter. Default: start the dev server if possible; skip if it needs special env vars.

### Option A: Start the dev server yourself (default)
```bash
<discover from package.json scripts: bun run dev / npm run dev / etc.>
```
- Tell the user: "Starting the dev server on http://localhost:XXXX — you can open it in your browser."
- Remember to stop it when done (session exit).
- If the dev server needs special env vars (e.g., `DATABASE_URL`, `STRIPE_API_KEY`) that aren't set, skip to Option C.

### Option B: User already has it running
If the user mentions the app is already running (or "Live Application" is filled in), use that URL. Don't start a second server.

### Option C: Skip functional testing
If the dev server can't be started (missing env vars, port conflict, complex setup), skip functional testing. Note in the report: "Functional testing skipped — dev server requires <X>." Focus on code-level review instead. Log the setup friction in `.context_ledger/memory/office/inefficiencies/log.md` so the next agent knows before trying.

## Cloud/sandbox agent

Only if a live app is available (check the "Live Application" field — if "N/A", skip and note it in the report).

Test normal workflows and edge cases. Think like: end user, admin, developer, QA, power user, first-time visitor. Verify existing functionality before modifying it. Reproduce bugs before fixing them.

## Both

### Test like:
- End user (browse, interact, core flows)
- Administrator (management, moderation, analytics)
- QA engineer (edge cases, error states, permission boundaries)
- Malicious user (try to access other users' data, bypass auth, submit invalid input)

### Verify before modifying
Always verify existing functionality before changing it. If you're fixing a bug, reproduce it first to confirm it's real.
