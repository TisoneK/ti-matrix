#!/usr/bin/env pwsh
# ledger-mem.ps1 - Windows port of ledger-mem (memory-registry hygiene).
#
# SOURCE ENCODING - pure ASCII, on purpose. Windows PowerShell 5.1 decodes a
# BOM-less script with the *system codepage*, not UTF-8, so a non-ASCII byte
# here can fail the parse there (an em-dash decodes to U+201D, which the
# parser reads as a string terminator) while pwsh 7 parses it fine. Emit a
# character the sh port writes as a literal from its code point instead -
# [char]0x2014 em-dash, [char]0x2026 ellipsis - so both ports emit the same
# bytes. Enforced by `ledger-sync verify` and tests/run-tests.sh; rationale
# in core/CHANGELOG.md (2.0.4).
#
# Update-in-place files hold ONE entry per key: correct an entry by editing
# its row/block, never by appending a second one (its prior value is in git
# history). This is the opposite of the append-only logs. 'check' flags
# duplicate keys in system/ai-models.md (key = Agent, Model) and
# system/environments.md (key = the "Identify by:" line).

[CmdletBinding()]
param(
  [Parameter(Position = 0)] [string] $Command = '',
  [Parameter(ValueFromRemainingArguments = $true)] [string[]] $RestArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Say { param([string]$Message) Write-Output $Message }
function ErrLine { param([string]$Message) [Console]::Error.WriteLine("ledger-mem: $Message") }
function Die { param([string]$Message) ErrLine $Message; exit 2 }

$scriptDir = $PSScriptRoot
$coreDir = (Resolve-Path (Join-Path $scriptDir '..')).Path
$ledgerDir = Split-Path -Parent $coreDir
$projectDir = Split-Path -Parent $ledgerDir
$memoryDir = Join-Path $ledgerDir 'memory'
$officeDir = Join-Path $memoryDir 'office'
$configFile = Join-Path $memoryDir 'workflows/history.conf'

function Get-Conf { param([string]$Key, [int]$Default)
  # same reader as ledger-history (numeric values only)
  if (Test-Path -LiteralPath $configFile) {
    foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $configFile) {
      $line = $raw.TrimEnd("`r")
      if ($line -match "^$Key=(\d+)\s*$") { return [int]$matches[1] }
    }
  }
  return $Default
}

function Usage {
  @(
    'ledger-mem - .context_ledger hygiene checks',
    '',
    '  check   duplicate keys in the update-in-place registries',
    '          (ai-models.md by Agent+Model, environments.md by Identify-by;',
    '          roster.md by Name and codename) plus warn-only audits: a',
    '          roster row with no Status cell (the at-a-glance column), a',
    '          roster row whose Session N is already in agents/sessions.md',
    '          means the session never clocked out, and a duplicated',
    '          Session N means a resumed session re-logged; plus warn-only',
    '          cap checks - backlog.md past backlog_cap (prune to',
    '          parking-lot.md), flaws/log.md and inefficiencies/log.md past',
    "          flaws_cap/inefficiencies_cap (run 'prune'/'prune --apply') -",
    '          all three keys in workflows/history.conf',
    '  lint    .context_ledger vocabulary (ADR-N, bug IDs, .context_ledger/ paths) leaking',
    '          into product artifacts - the staged diff by default; --tree',
    '          sweeps every tracked product file (strip leaks old sessions left)',
    '  prune   report log compaction: each append-only durable log''s size',
    '          (flaws, inefficiencies, decisions), which entries carry a',
    '          closed marker on their own Status line (resolved/',
    '          superseded/fixed - move them verbatim to the',
    "          log's archive.md), and which logs hold 3+ entries hitting",
    '          the same recurring thing (roll up into one Recurring entry,',
    "          instances archived verbatim); --list names them. Report",
    '          mode never moves or deletes; --apply performs the closed-',
    '          entry moves mechanically (creates archive.md if needed) -',
    '          it does NOT do the Recurring roll-up, which needs an',
    '          agent to compose the consolidated entry.',
    '  closeout delete finished backlog items (- [x] tombstones) from the',
    '          tasks/backlog.md work queue - open work stays. Dry run by',
    '          default (lists the tombstones); --confirm deletes. Every',
    '          deleted line stays recoverable in git history; the completion',
    "          record is the finishing session's entry + commit.",
    '',
    'Exit codes: check/lint 0 clean, 1 problem; prune/closeout always 0; 2 usage/error'
  ) | ForEach-Object { Say $_ }
  exit 2
}

function Check-AiModels {
  $f = Join-Path $memoryDir 'system/ai-models.md'
  if (-not (Test-Path -LiteralPath $f)) { return $true }
  $seen = @{}; $where = @{}; $ln = 0
  foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $f) {
    $ln++
    $line = $raw.TrimEnd("`r")
    if ($line -notmatch '^\s*\|') { continue }
    $cells = $line.Split('|')
    if ($cells.Count -lt 6) { continue }
    $a = $cells[1].Trim(); $m = $cells[2].Trim()
    $fs = $cells[3].Trim(); $ls = $cells[4].Trim(); $s = $cells[5].Trim()
    if ($fs -match '^\d{4}-\d{2}-\d{2}$' -and $ls -match '^\d{4}-\d{2}-\d{2}$' -and $s -match '^\d+$') {
      $key = "$a`t$m"
      if ($seen.ContainsKey($key)) { $seen[$key]++; $where[$key] += " $ln" }
      else { $seen[$key] = 1; $where[$key] = "$ln" }
    }
  }
  $dup = $false
  foreach ($k in $seen.Keys) {
    if ($seen[$k] -gt 1) {
      $parts = $k.Split("`t")
      ErrLine ('DUP ai-models.md: {0} rows for agent="{1}" model="{2}" (lines {3}) - merge into one row; sessions accumulate, old values are in git history' -f $seen[$k], $parts[0], $parts[1], $where[$k].Trim())
      $dup = $true
    }
  }
  return (-not $dup)
}

function Check-Environments {
  $f = Join-Path $memoryDir 'system/environments.md'
  if (-not (Test-Path -LiteralPath $f)) { return $true }
  $seen = @{}; $where = @{}; $ln = 0
  foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $f) {
    $ln++
    $line = $raw.TrimEnd("`r")
    if ($line -notmatch '^\s*-\s*\*\*Identify by:\*\*') { continue }
    $v = ($line -replace '^\s*-\s*\*\*Identify by:\*\*\s*', '').Trim()
    if ($v -eq '' -or $v -match '^<') { continue }
    if ($seen.ContainsKey($v)) { $seen[$v]++; $where[$v] += " $ln" }
    else { $seen[$v] = 1; $where[$v] = "$ln" }
  }
  $dup = $false
  foreach ($k in $seen.Keys) {
    if ($seen[$k] -gt 1) {
      ErrLine ('DUP environments.md: {0} blocks with Identify by="{1}" (lines {2}) - merge into one block; keep the latest facts, old ones are in git history' -f $seen[$k], $k, $where[$k].Trim())
      $dup = $true
    }
  }
  return (-not $dup)
}

function Check-Roster {
  # Rows are | Name | Codename | Model | Doing | Status | Status detail |.
  # Name + codename must be unique in the office; a real row (codename
  # S<NNN>) with an empty or missing Status cell draws a warn-only nudge
  # (legacy pre-1.1.0 four-column rows warn too; they fail nothing).
  $f = Join-Path $officeDir 'agents/roster.md'
  if (-not (Test-Path -LiteralPath $f)) { return $true }
  $nseen = @{}; $nwhere = @{}; $cseen = @{}; $cwhere = @{}; $nostat = @{}; $ln = 0
  foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $f) {
    $ln++
    $line = $raw.TrimEnd("`r")
    if ($line -notmatch '^\s*\|') { continue }
    $cells = $line.Split('|')
    if ($cells.Count -lt 4) { continue }
    $name = $cells[1].Trim(); $code = $cells[2].Trim()
    if ($code -notmatch '^[Ss][0-9]+$') { continue }
    if ($nseen.ContainsKey($name)) { $nseen[$name]++; $nwhere[$name] += " $ln" } else { $nseen[$name] = 1; $nwhere[$name] = "$ln" }
    if ($cseen.ContainsKey($code)) { $cseen[$code]++; $cwhere[$code] += " $ln" } else { $cseen[$code] = 1; $cwhere[$code] = "$ln" }
    $st = if ($cells.Count -ge 8) { $cells[5].Trim() } else { '' }
    if ($st -eq '') { $nostat[$code] = "$ln" }
  }
  $dup = $false
  foreach ($k in $nseen.Keys) { if ($nseen[$k] -gt 1) { ErrLine ('DUP roster.md: name "{0}" used by {1} rows (lines {2}) - one name per office; pick another, or edit your own row' -f $k, $nseen[$k], $nwhere[$k].Trim()); $dup = $true } }
  foreach ($k in $cseen.Keys) { if ($cseen[$k] -gt 1) { ErrLine ('DUP roster.md: codename "{0}" on {1} rows (lines {2}) - one row per session codename; edit your row instead of adding a second' -f $k, $cseen[$k], $cwhere[$k].Trim()); $dup = $true } }
  # The warn goes straight to the console, not Say/Write-Output: the check
  # dispatcher captures this function's output into $ok3, which would
  # silently swallow any Write-Output warning (the DUP errors above survive
  # because ErrLine writes to stderr).
  foreach ($k in $nostat.Keys) { [Console]::Out.WriteLine(('WARN roster.md: codename {0} has no Status - the board''s at-a-glance column (Working/Done/Blocked + a status-detail line) is empty; edit your row' -f $k)) }
  return (-not $dup)
}

function Check-RosterStale {
  # Board vs duty log: sessions.md entries are appended at wrap-up (Step 17),
  # so a "Session N" entry whose roster row S<N> is still on the board means
  # the session logged itself done without clocking out. Warns only.
  $r = Join-Path $officeDir 'agents/roster.md'
  $s = Join-Path $officeDir 'agents/sessions.md'
  if (-not (Test-Path -LiteralPath $r) -or -not (Test-Path -LiteralPath $s)) { return }
  $nums = @()
  foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $r) {
    $line = $raw.TrimEnd("`r")
    if ($line -notmatch '^\s*\|') { continue }
    $cells = $line.Split('|')
    if ($cells.Count -lt 4) { continue }
    $code = $cells[2].Trim()
    if ($code -match '^[Ss]([0-9]+)$') { $nums += $Matches[1] }
  }
  if ($nums.Count -eq 0) { return }
  $heads = @(Get-Content -Encoding UTF8 -LiteralPath $s | Where-Object { $_ -match '^## ' })
  foreach ($num in ($nums | Sort-Object -Unique)) {
    foreach ($h in $heads) {
      if ($h -match ("Session {0}([^0-9]|`$)" -f $num)) {
        Say ('WARN roster.md: codename S{0} is still on the board, but a Session {0} entry already exists in agents/sessions.md - the session logged itself done without clocking out; remove the row' -f $num)
        break
      }
    }
  }
}

function Check-DupSessions {
  # sessions.md holds one entry per session codename S<N> (Step 17). Two
  # "Session N" headers for the same N mean a resumed session re-logged
  # instead of extending its entry (the ghost-editor flaw). Warns only.
  $s = Join-Path $officeDir 'agents/sessions.md'
  if (-not (Test-Path -LiteralPath $s)) { return }
  $seen = @{}; $where = @{}
  $ln = 0
  foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $s) {
    $ln++
    $line = $raw.TrimEnd("`r")
    if ($line -match '^##\s+.*[Ss]ession\s+([0-9]+)') {
      $num = [int]$Matches[1]
      if ($seen.ContainsKey($num)) { $seen[$num]++; $where[$num] += " $ln" }
      else { $seen[$num] = 1; $where[$num] = "$ln" }
    }
  }
  foreach ($num in ($seen.Keys | Sort-Object)) {
    if ($seen[$num] -gt 1) {
      Say ('WARN sessions.md: Session {0} has {1} entries (lines {2}) - one entry per codename S<N>; a resumed session should extend its entry, not add a second. Merge them.' -f $num, $seen[$num], $where[$num])
    }
  }
}

function Check-BacklogTombstones {
  # The backlog is a live queue of open work (core 0.21.0) - a checked-off
  # "- [x]" line means the item finished but the line was never deleted.
  # Warns only; the sweep is `ledger-mem closeout`.
  $f = Join-Path $officeDir 'tasks/backlog.md'
  if (-not (Test-Path -LiteralPath $f)) { return }
  $n = @(Get-Content -Encoding UTF8 -LiteralPath $f | Where-Object { $_ -match '^\s*[-*+]\s+\[[xX]\]' }).Count
  if ($n -gt 0) {
    Say ('WARN backlog.md: {0} finished item(s) still sit checked off (- [x]) - the backlog holds open work only; run ledger-mem closeout to sweep them (git history keeps the lines)' -f $n)
  }
}

function Check-LogCap {
  # Warn-only cap check for an append-only durable log (flaws/inefficiencies):
  # counts real entries (## YYYY-MM-DD headers outside <!-- --> blocks, the
  # same scoping Invoke-Prune/ledger-state use) against a history.conf key.
  # Going over does not mean "stop adding" - it means "run ledger-mem prune".
  param([string]$Rel, [string]$Key, [int]$Default)
  $f = Join-Path $officeDir $Rel
  if (-not (Test-Path -LiteralPath $f)) { return }
  $cap = Get-Conf $Key $Default
  $n = 0; $intpl = $false
  foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $f) {
    $line = $raw.TrimEnd("`r")
    if (-not $intpl -and $line -match '^<!--') { if ($line -notmatch '-->') { $intpl = $true }; continue }
    if ($intpl) { if ($line -match '-->') { $intpl = $false }; continue }
    if ($line -match '^## \d{4}-\d{2}-\d{2}') { $n++ }
  }
  if ($n -gt $cap) {
    Say ("WARN {0}: {1} entries past the cap of {2} ({3} in workflows/history.conf) - run 'ledger-mem prune' to see what's archive-eligible, 'prune --apply' to move the closed ones" -f $Rel, $n, $cap, $Key)
  }
}

function Check-BacklogCap {
  # The backlog is a capped WORK QUEUE (core 1.2.0) - actionable items only,
  # default ~20 rows (backlog_cap in workflows/history.conf). Past the cap the
  # add-a-row rule becomes prune-a-row: the lowest-value open row goes to
  # parking-lot.md (still valuable) or is deleted (not). Warns only - the
  # queue is a working set, not a hard limit. Counted as table rows carrying
  # a B-<date> ID (headers, separators, and template comments are not rows).
  $f = Join-Path $officeDir 'tasks/backlog.md'
  if (-not (Test-Path -LiteralPath $f)) { return }
  $cap = Get-Conf 'backlog_cap' 20
  $n = @(Get-Content -Encoding UTF8 -LiteralPath $f | Where-Object { $_ -match '^\s*\|\s*B-[0-9]' }).Count
  if ($n -gt $cap) {
    Say ('WARN backlog.md: {0} actionable rows past the cap of {1} - the queue is a working set, not an archive; prune the lowest-value open row to tasks/parking-lot.md (or delete it) before adding another (raise backlog_cap in workflows/history.conf only by intent)' -f $n, $cap)
  }
}

function Invoke-Closeout {
  param([bool]$Confirm)
  $f = Join-Path $officeDir 'tasks/backlog.md'
  if (-not (Test-Path -LiteralPath $f)) { Say 'ledger-mem: no tasks/backlog.md (nothing to close out)'; return }
  $raw = [IO.File]::ReadAllText($f)
  $eol = if ($raw.Contains("`r`n")) { "`r`n" } else { "`n" }
  # split on the EOL string only: a trailing newline yields a final empty
  # element, so rejoining reproduces the file byte-for-byte
  $lines = $raw -split [regex]::Escape($eol)
  $tomb = @(); $keep = @()
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*[-*+]\s+\[[xX]\]') { $tomb += "line $($i + 1): $($lines[$i])" }
    else { $keep += $lines[$i] }
  }
  if ($tomb.Count -eq 0) {
    Say 'backlog closeout: no finished tombstones - tasks/backlog.md already holds only open work.'
    return
  }
  if (-not $Confirm) {
    Say ('backlog closeout (dry run): {0} finished item(s) would be deleted from tasks/backlog.md:' -f $tomb.Count)
    foreach ($t in $tomb) { Say ('  - {0}' -f $t) }
    Say ''
    Say 'Open items stay untouched, and the deleted lines remain in git history.'
    Say 'Re-run with --confirm to delete.'
    return
  }
  $utf8 = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($f, $keep -join $eol, $utf8)
  Say ('backlog closeout: deleted {0} finished item(s) from tasks/backlog.md (git history keeps them).' -f $tomb.Count)
  $open = @(Get-Content -Encoding UTF8 -LiteralPath $f | Where-Object { $_ -match '^\s*[-*+]\s+\[ \]' }).Count
  Say ('backlog now holds {0} open item(s).' -f $open)
  Say 'Commit as: chore(ledger): close out finished backlog items'
}

function Invoke-Lint {
  param([switch]$Tree)
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Die 'lint needs git on PATH' }
  $root = (& git -C $projectDir rev-parse --show-toplevel 2>$null)
  if (-not $root) { Die 'lint must run inside the project git repo' }
  $n = 0
  if ($Tree) {
    # sweep every tracked file outside .context_ledger/ (leaks an old session left)
    $files = @(@(& git -C $root ls-files 2>$null) | Where-Object { $_ -and $_ -notmatch '^\.context_ledger/' })
    if ($files.Count -eq 0) { Say 'lint passed: no tracked product files to sweep'; return $true }
    foreach ($rel in $files) {
      $full = Join-Path $root $rel
      if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { continue }
      $ln = 0
      foreach ($s in Get-Content -Encoding UTF8 -LiteralPath $full) {
        $ln++
        $pat = ''
        if ($s -match 'ADR-[0-9]') { $pat = 'an ADR reference' }
        elseif ($s -match 'B-[0-9]{4}-[0-9]{2}-[0-9]') { $pat = 'a bug-ID reference' }
        elseif ($s -match '\.context_ledger/') { $pat = 'a .context_ledger/ path' }
        elseif ($s.ToLower() -match 'per adr') { $pat = '"per ADR"' }
        if ($pat -ne '') { ErrLine ('LEAK: {0}:{1} cites {2}: {3}' -f ($rel -replace '\\','/'), $ln, $pat, $s); $n++ }
      }
    }
  } else {
    $diff = @(& git -C $root diff --cached -U0 --no-color 2>$null)
    $file = ''
    foreach ($line in $diff) {
      if ($line -match '^\+\+\+ ') { $file = $line -replace '^\+\+\+ b/', '' -replace '^\+\+\+ ', ''; continue }
      if ($line -match '^\+' -and $line -notmatch '^\+\+\+') {
        if ($file -match '^\.context_ledger/' -or $file -eq '/dev/null') { continue }
        $s = $line.Substring(1)
        $pat = ''
        if ($s -match 'ADR-[0-9]') { $pat = 'an ADR reference' }
        elseif ($s -match 'B-[0-9]{4}-[0-9]{2}-[0-9]') { $pat = 'a bug-ID reference' }
        elseif ($s -match '\.context_ledger/') { $pat = 'a .context_ledger/ path' }
        elseif ($s.ToLower() -match 'per adr') { $pat = '"per ADR"' }
        if ($pat -ne '') { ErrLine ('LEAK: {0} cites {1}: {2}' -f $file, $pat, $s); $n++ }
      }
    }
  }
  if ($n -eq 0) {
    if ($Tree) { Say 'lint passed: no .context_ledger vocabulary (ADR-N, bug IDs, .context_ledger/ paths) in any tracked product file' }
    else { Say 'lint passed: no .context_ledger vocabulary (ADR-N, bug IDs, .context_ledger/ paths) in the staged product diff' }
    return $true
  }
  ErrLine 'lint failed: product code must stand on its own. State the reason in plain words; the ADR or bug-ID link belongs in .context_ledger/memory, not the source. Memory references code, never the reverse. Stripping a found leak is a safe fix - do it, then continue.'
  return $false
}

function Get-ArchiveTitle { param([string]$Rel)
  switch ($Rel) {
    'flaws/log.md' { return 'Flaws Log' }
    'inefficiencies/log.md' { return 'Inefficiencies Log' }
    'plans/decisions.md' { return 'Architectural Decisions' }
    default { return 'Log' }
  }
}

# Invoke-PruneApply mirrors ledger-mem's prune_apply_one: cut every entry
# whose OWN Status/Fixed-in-package line carries a closed marker
# (resolved/superseded/fixed/no longer) out of the log, verbatim, into the
# log's companion archive.md (created with a header if missing). Does NOT
# perform the 3+-repeat roll-up -- that still needs an agent's judgment
# to compose the consolidated entry (report mode below still flags it).
function Invoke-PruneApply {
  foreach ($rel in @('flaws/log.md', 'inefficiencies/log.md', 'plans/decisions.md')) {
    $f = Join-Path $officeDir $rel
    if (-not (Test-Path -LiteralPath $f)) { continue }
    $dir = ($rel -split '/')[0]
    $archive = Join-Path $officeDir "$dir/archive.md"
    $preamble = New-Object System.Collections.Generic.List[string]
    $segments = New-Object System.Collections.Generic.List[object]
    $inseg = $false; $intpl = $false; $curClosed = $false
    $curBuf = New-Object System.Collections.Generic.List[string]
    foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $f) {
      $line = $raw.TrimEnd("`r")
      if (-not $inseg -and $line -match '^<!--') {
        $preamble.Add($line)
        if ($line -notmatch '-->') { $intpl = $true }
        continue
      }
      if ($intpl) { $preamble.Add($line); if ($line -match '-->') { $intpl = $false }; continue }
      if ($line -match '^## ') {
        if ($inseg) { $segments.Add([pscustomobject]@{ Lines = $curBuf; Closed = $curClosed }) }
        $inseg = $true; $curClosed = $false; $curBuf = New-Object System.Collections.Generic.List[string]
        $curBuf.Add($line)
        continue
      }
      if ($inseg) {
        $curBuf.Add($line)
        if ($line -match '^\s*[-*]?\s*\*\*Status:\*\*' -and $line -match 'RESOLVED|[Ss]uperseded|[Ff]ixed in package|no longer (a )?(flaw|issue)') { $curClosed = $true }
        if ($line -match '^\s*[-*]?\s*\*\*Fixed in package:\*\*') { $curClosed = $true }
        continue
      }
      $preamble.Add($line)
    }
    if ($inseg) { $segments.Add([pscustomobject]@{ Lines = $curBuf; Closed = $curClosed }) }

    $kept = New-Object System.Collections.Generic.List[string]
    $moved = New-Object System.Collections.Generic.List[string]
    $kept.AddRange($preamble)
    $movedCount = 0
    foreach ($seg in $segments) {
      if ($seg.Closed) { $moved.AddRange($seg.Lines); $movedCount++ }
      else { $kept.AddRange($seg.Lines) }
    }
    if ($movedCount -gt 0) {
      if (-not (Test-Path -LiteralPath $archive)) {
        $title = Get-ArchiveTitle $rel
        # [char]0x2014, not a literal: this file is pure ASCII on purpose so
        # Windows PowerShell 5.1 (which decodes a BOM-less script with the
        # system codepage) parses it on any locale - an em-dash byte pair
        # decodes to U+201D, which the parser reads as a string terminator.
        $header = @(
          "# $title $([char]0x2014) archive (verbatim moves from log.md)",
          '',
          'Entries below were explicitly marked `RESOLVED` / `superseded` / fixed in',
          "the live log and moved here verbatim (no edits), per the log's pruning",
          'rule (`ledger-mem prune --apply`). Startup reads only the live log; this',
          'archive stays in git, grep-able.'
        )
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($archive, ($header -join "`n") + "`n", $utf8)
      }
      $utf8 = New-Object System.Text.UTF8Encoding($false)
      $existing = [IO.File]::ReadAllText($archive)
      [IO.File]::WriteAllText($archive, $existing + "`n" + ($moved -join "`n") + "`n", $utf8)
      [IO.File]::WriteAllText($f, ($kept -join "`n") + "`n", $utf8)
      $plural = if ($movedCount -eq 1) { 'entry' } else { 'entries' }
      Say "${rel}: moved $movedCount $plural to $dir/archive.md"
    } else {
      Say "${rel}: nothing marked resolved/superseded - nothing moved"
    }
  }
  Say ''
  Say 'memory prune --apply: closed entries moved verbatim to their archive.md;'
  Say 'every moved line survives unchanged there and in git history. Recurring'
  Say 'roll-ups (3+ entries on the same thing) are still a manual edit - re-run'
  Say 'without --apply to see if any are eligible.'
}

function Invoke-Prune {
  param([bool]$List)
  if (-not (Test-Path -LiteralPath $memoryDir)) { Say 'ledger-mem: no memory dir (nothing to prune)'; return }
  $eligible = $false
  foreach ($rel in @('flaws/log.md', 'inefficiencies/log.md', 'plans/decisions.md')) {
    $f = Join-Path $officeDir $rel
    if (-not (Test-Path -LiteralPath $f)) { continue }
    $total = 0; $lines = 0
    $segs = @()
    $inseg = $false; $closed = $false; $heading = ''; $fp = ''; $intpl = $false
    foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $f) {
      $lines++
      $line = $raw.TrimEnd("`r")
      if (-not $inseg -and $line -match '^<!--') { if ($line -notmatch '-->') { $intpl = $true }; continue }
      if ($intpl) { if ($line -match '-->') { $intpl = $false }; continue }
      if ($line -match '^## ') {
        if ($inseg) { $segs += [pscustomobject]@{ Heading = $heading; Closed = $closed; Fp = $fp } }
        $inseg = $true; $closed = $false; $heading = $line; $total++; $fp = ''
        continue
      }
      if ($inseg -and ($line -match '^[ ]*[-*]?[ ]*[*][*]Status:[*][*]') -and ($line -match 'RESOLVED|[Ss]uperseded|[Ff]ixed in package|no longer (a )?(flaw|issue)')) { $closed = $true }
      if ($inseg -and ($line -match '^[ ]*[-*]?[ ]*[*][*]Fixed in package:[*][*]')) { $closed = $true }
      if ($inseg -and $fp -eq '' -and $line -match '^[ ]*[-*]?[ ]*[*][*](Problem|Flaw):[*][*][ ]*(.+)$') {
        $t = $Matches[2].Trim().ToLower().Replace("`t", ' ')
        while ($t.Contains('  ')) { $t = $t.Replace('  ', ' ') }
        $fp = $t
      }
    }
    if ($inseg) { $segs += [pscustomobject]@{ Heading = $heading; Closed = $closed; Fp = $fp } }
    $cand = @($segs | Where-Object { $_.Closed } | ForEach-Object { $_.Heading })
    $c = $cand.Count
    $fpseen = @{}; $fpwhere = @{}
    foreach ($seg in $segs) {
      if ($seg.Fp -eq '') { continue }
      if ($fpseen.ContainsKey($seg.Fp)) { $fpseen[$seg.Fp]++; $fpwhere[$seg.Fp] += (' || ' + $seg.Heading) }
      else { $fpseen[$seg.Fp] = 1; $fpwhere[$seg.Fp] = (' || ' + $seg.Heading) }
    }
    Say ('{0} - {1} entries ({2} lines); {3} marked resolved/superseded -> archive-eligible.' -f $rel, $total, $lines, $c)
    $dir = $rel -replace '[^/]*$', ''
    if ($c -gt 0) {
      Say ('  move the resolved entries to {0}archive.md; startup then reads only the active log.' -f $dir)
      if ($List) { foreach ($h in $cand) { Say ('    - {0}' -f $h) } }
      $eligible = $true
    }
    foreach ($k in $fpseen.Keys) {
      if ($fpseen[$k] -ge 3) {
        $short = $k; if ($short.Length -gt 70) { $short = $short.Substring(0, 70) }
        Say ('  roll-up: {0} entries hit the same recurring thing ({1}) - append one Recurring entry, move the instances to {2}archive.md.' -f $fpseen[$k], $short, $dir)
        if ($List) { Say ('    - {0}' -f $fpwhere[$k]) }
      }
    }
  }
  if ($eligible) {
    Say ''
    Say 'memory prune: advisory only - nothing was moved. Archiving is a manual edit'
    Say '(cut the resolved entries into archive.md); they stay grep-able and out of the'
    Say 'startup read. Re-run with --list to see the eligible entries.'
  } else {
    Say 'memory prune: durable logs are lean - nothing archive-eligible.'
  }
}

switch ($Command) {
  'check' {
    if (-not (Test-Path -LiteralPath $memoryDir)) { Say 'ledger-mem: no memory dir (nothing to check)'; exit 0 }
    $ok1 = Check-AiModels
    $ok2 = Check-Environments
    $ok3 = Check-Roster
    Check-RosterStale
    Check-DupSessions
    Check-BacklogTombstones
    Check-BacklogCap
    Check-LogCap 'flaws/log.md' 'flaws_cap' 15
    Check-LogCap 'inefficiencies/log.md' 'inefficiencies_cap' 15
    if ($ok1 -and $ok2 -and $ok3) { Say 'memory check passed: no duplicate keys in the update-in-place registries'; exit 0 }
    ErrLine 'memory check failed: a registry has more than one entry for a key - correct in place (edit the entry), do not append a duplicate'
    exit 1
  }
  'lint' {
    foreach ($a in $RestArgs) {
      if ($a -notin @('--tree', '-h', '--help')) { Die "unknown argument '$a'" }
    }
    if ($RestArgs -contains '-h' -or $RestArgs -contains '--help') { Usage }
    if (Invoke-Lint -Tree:($RestArgs -contains '--tree')) { exit 0 } else { exit 1 }
  }
  'prune' {
    if ($RestArgs -contains '--apply') { Invoke-PruneApply } else { Invoke-Prune -List:($RestArgs -contains '--list') }
    exit 0
  }
  'closeout' {
    foreach ($a in $RestArgs) {
      if ($a -notin @('--confirm', '-h', '--help')) { Die "unknown argument '$a'" }
    }
    if ($RestArgs -contains '-h' -or $RestArgs -contains '--help') { Usage }
    Invoke-Closeout -Confirm:($RestArgs -contains '--confirm')
    exit 0
  }
  { $_ -in @('', '-h', '--help', 'help') } { Usage }
  default { Die "unknown command '$Command' (try: ledger-mem.ps1 help)" }
}
