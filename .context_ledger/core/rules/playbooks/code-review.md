<!-- Loaded per kickoff.md Phase 4's routing table: a new feature or a
substantial review. Shared by both editions — identical for local and
cloud/sandbox agents. -->

# Code Review Checklist

Evaluate:
- Architecture, Maintainability, Readability, Modularity
- Code duplication, SOLID principles, Design patterns
- Error handling, Logging, Testing coverage
- Configuration management, Input validation
- Authorization checks (every mutation checks ownership; every admin route is gated)
- Race conditions (especially on counters)
- Pagination hardening (guard against negative/NaN/huge values)
- Technical debt

**Deep-scan methodology:** when you find a bug, grep for the same pattern across the whole codebase. Fix all instances in one commit.
