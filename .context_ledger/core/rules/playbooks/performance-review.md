<!-- Loaded per kickoff.md Phase 4's routing table: performance-sensitive
code. Shared by both editions. -->

# Performance Review

Look for:
- Slow rendering, Expensive computations
- N+1 queries, Missing indexes, Unbounded result sets
- Excessive API calls, No caching
- Large bundle sizes
- Unnecessary re-renders (missing `useMemo`/`useCallback`, wrong deps)
- Memory leaks (event listeners not cleaned up, intervals not cleared)
- Image optimization, Lazy loading, CDN caching
- Algorithmic complexity (e.g., `Array.find()` inside a sort → use Map)

Implement safe optimizations. Always typecheck before committing.
