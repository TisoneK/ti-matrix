<!-- Loaded per kickoff.md Phase 4's routing table: security-sensitive
code. Shared by both editions — the two secrets-management bullets below
cover the local and cloud/sandbox cases in one line each. -->

# Security Review

Evaluate:
- Authentication, Authorization (every route checks auth; every mutation checks ownership)
- Input validation (length limits, type checks, format validation)
- Output encoding (never `dangerouslySetInnerHTML` without sanitization)
- Sensitive data exposure (never serialize password hashes; never leak internals in errors)
- API security (rate limiting on auth, upload, mutation routes)
- File uploads (content-type allowlist, max size, URL protocol validation)
- **SSRF protection** (if the project fetches URLs: check for redirect-following bypass, private IP filtering, metadata endpoint blocking)
- Secrets management: `.env*` in `.gitignore`; never commit secrets; if you see one already committed, flag it. A cloud/sandbox session's PAT lives in the env var only, never a tracked file, and is stripped from `.git/config` after each clone/push. **No secret values in tracked `.context_ledger/` files, ever — values only in `.context_ledger/memory/secrets/`.**
- Session handling
- Dependency vulnerabilities (run the project's audit tool if available — `npm audit`, `bun audit`, `pip audit` — verified against actual installed versions)

**Critical:** never put security vulnerability mechanics in a public changelog — only in the internal report.
