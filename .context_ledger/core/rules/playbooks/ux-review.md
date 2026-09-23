<!-- Loaded per kickoff.md Phase 4's routing table: a UI/UX change. Shared
by both editions. -->

# UX / UI Review

### Reference-driven design
When the user provides screenshots, use vision analysis to compare precisely — measure layout, column counts, card widths, spacing. Don't just describe what you see; identify the specific differences and fix them.

### Evaluate:
- Navigation, Discoverability, Visual hierarchy
- Accessibility (keyboard nav, focus indicators, ARIA labels, color contrast)
- Typography, Spacing, Color consistency
- Responsiveness (360px, 768px, 1280px)
- Empty states, Loading states, Error messages
- Mobile-specific issues (iOS Safari quirks, touch targets, safe-area insets)

### Dark mode / theme completeness (ONLY if the project supports multiple themes)

> **First, determine if the project supports theming.** Check:
> 1. Does `globals.css` define both light (`:root`) and dark (`.dark`) variables?
> 2. Is `.dark` ever applied to `<html>` (toggle, `prefers-color-scheme`, hardcoded)?
> 3. Do components use `dark:` variants or theme-aware CSS variables?
>
> **If single-theme** (dark-only, light-only): skip this section. Note "single-theme" in the report. **If the project has light + dark variables but never applies `.dark`**: that's a finding (theming infrastructure exists but is inactive) — flag it, don't try to "fix" every component.

**If multi-theme:** Every light-mode color class needs a `dark:` variant (except intentional theme-agnostic surfaces). Scan all components, fix every instance, document false positives.
