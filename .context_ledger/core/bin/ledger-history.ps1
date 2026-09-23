#!/usr/bin/env pwsh
# ledger-history.ps1 - Windows port of ledger-history (office lifecycle).
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
# The live office is the unnumbered directory memory/office/ (roster, session
# registry, session notes, tasks, plans, flaws, inefficiencies, reviews). Only
# one office is ever live, so its paths are stable. Closing NEVER condenses or
# resets anything: the directory is frozen verbatim and numbered at that
# moment (history/office-<NNN>/), and a permanent accomplishments record
# (history/office-<NNN>.md) is written - it stays in history/ forever, even
# after the frozen office is zipped into archive/office-<NNN>.tar.gz and
# eventually gc'd. The next office opens from empty skeletons; durable memory
# (workflows/, collaboration/, system/, user/, overrides/, core.lock,
# secrets/) lives at the memory/ root and never rotates.
#
#   status                 live office, session count, zone sizes, due?
#   close [--milestone L] [--confirm]   freeze the live office into history/,
#                          write the permanent record, open a fresh office,
#                          zip the oldest frozen office when history/ is full.
#                          Prints the checklist; only --confirm runs.
#   gc [--confirm]         delete oldest archive/ tarballs over the cap
#                          (git-recoverable). --confirm executes.
#
# Config: memory/workflows/history.conf - office_size=20 (legacy key
# group_size still read), history_keep=3, archive_keep=12 (defaults when
# absent); backlog_cap=20 sizes the work queue (read by ledger-mem check).
# Uses tar (Windows 10+ ships tar.exe) so archives are .tar.gz,
# matching the POSIX port.

[CmdletBinding()]
param(
  [Parameter(Position = 0)] [string] $Command = '',
  [Parameter(ValueFromRemainingArguments = $true)] [string[]] $RestArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Say { param([string]$Message) Write-Output $Message }
function Die { param([string]$Message) [Console]::Error.WriteLine("ledger-history: $Message"); exit 2 }

$scriptDir = $PSScriptRoot
$coreDir = (Resolve-Path (Join-Path $scriptDir '..')).Path
$ledgerDir = Split-Path -Parent $coreDir
$memoryDir = Join-Path $ledgerDir 'memory'
$officeDir = Join-Path $memoryDir 'office'
$historyDir = Join-Path $ledgerDir 'history'
$archiveDir = Join-Path $ledgerDir 'archive'
$sessionsMd = Join-Path $officeDir 'agents/sessions.md'
$configFile = Join-Path $memoryDir 'workflows/history.conf'
$officeTpl = Join-Path $coreDir 'templates/memory/office'

function Usage {
  @(
    'ledger-history - office lifecycle: open, work, close, freeze, archive',
    '  status                 live office, session count, zone sizes, due?',
    '  close [--milestone L] [--confirm]   freeze the live office into history/',
    '  gc [--confirm]         delete oldest archive/ tarballs over the cap',
    'Config: memory/workflows/history.conf (office_size, history_keep, archive_keep, backlog_cap).'
  ) | ForEach-Object { Say $_ }
  exit 2
}

function Get-Conf { param([string]$Key, [int]$Default)
  if (Test-Path -LiteralPath $configFile) {
    foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $configFile) {
      $line = $raw.TrimEnd("`r")
      if ($line -match "^$Key=(\d+)\s*$") { return [int]$matches[1] }
    }
  }
  return $Default
}

function Get-OfficeSize { Get-Conf 'office_size' (Get-Conf 'group_size' 20) }

function Get-SessionCount {
  if (-not (Test-Path -LiteralPath $sessionsMd)) { return 0 }
  $n = 0
  foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $sessionsMd) {
    if ($raw -match '^## \d{4}-\d{2}-\d{2}.*Session ') { $n++ }
  }
  return $n
}

function Get-OfficeOpened {
  if (-not (Test-Path -LiteralPath $sessionsMd)) { return '' }
  foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $sessionsMd) {
    if ($raw -match '^## (\d{4}-\d{2}-\d{2})') { return $matches[1] }
  }
  return ''
}

function Get-MaxOfficeNum {
  # highest office number on record; the records are permanent, so the
  # sequence is always derivable - no state file
  $max = 0
  $items = @()
  $items += @(Get-ChildItem -LiteralPath $historyDir -Filter 'office-*.md' -File -ErrorAction SilentlyContinue)
  $items += @(Get-ChildItem -LiteralPath $historyDir -Filter 'office-*' -Directory -ErrorAction SilentlyContinue)
  $items += @(Get-ChildItem -LiteralPath $archiveDir -Filter 'office-*.tar.gz' -File -ErrorAction SilentlyContinue)
  foreach ($f in $items) {
    if ($f.Name -match '^office-0*(\d+)') { $n = [int]$matches[1]; if ($n -gt $max) { $max = $n } }
  }
  return $max
}

function Count-Archives { @(Get-ChildItem -LiteralPath $archiveDir -Filter 'office-*.tar.gz' -File -ErrorAction SilentlyContinue).Count }
function Count-Records { @(Get-ChildItem -LiteralPath $historyDir -Filter 'office-*.md' -File -ErrorAction SilentlyContinue).Count }
function Count-OfficeDirs { @(Get-ChildItem -LiteralPath $historyDir -Filter 'office-*' -Directory -ErrorAction SilentlyContinue).Count }
function Today { (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd') }
function Pad { param([int]$N) '{0:000}' -f $N }

function Show-PrecloseChecklist {
  Say 'Before closing this office:'
  Say '  - the directory is frozen VERBATIM (roster, registry, notes, logs -'
  Say '    nothing is condensed, trimmed, or reset)'
  Say '  - after the freeze, fill the permanent record history/office-<NNN>.md:'
  Say '    Accomplished / Decisions still in force / Open threads'
  Say "  - re-seed open threads that still matter into the NEW office's files"
  Say '    (backlog / flaws / decisions) - the only carryover there is'
  Say '  - re-seed WORK, not knowledge: backlog.md rows only for actionable'
  Say '    items with an active owner or a clear next step; the old office''s'
  Say '    parking-lot findings/questions/someday items go in the permanent'
  Say '    record (Open threads), not into the fresh queue'
  Say '  - re-seeded entries describe the work in plain words: they never cite'
  Say "    this office's session numbers or codenames (S014, Session 12) -"
  Say '    those live in the frozen copy the new office never reads; the new'
  Say "    office's numbering starts clean (codenames from S001, entries from"
  Say '    Session 1)'
  Say 'The new office starts from empty skeletons; durable files do not rotate.'
}

function Roll-OldestOfficeToArchive {
  $keep = Get-Conf 'history_keep' 3
  while ((Count-OfficeDirs) -gt $keep) {
    $oldest = Get-ChildItem -LiteralPath $historyDir -Filter 'office-*' -Directory | Sort-Object Name | Select-Object -First 1
    if (-not $oldest) { break }
    New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
    # tar runs with the CWD inside history/ and a relative -f path: GNU tar
    # (MSYS, often first on PATH) parses "C:\..." in -f as remote host "C"
    # and dies; bsdtar (System32 tar.exe) and GNU tar both accept a relative
    # name. archive/ is always a sibling of history/ under .context_ledger/.
    Push-Location $historyDir
    try {
      & tar -czf ("../{0}/{1}.tar.gz" -f (Split-Path -Leaf $archiveDir), $oldest.Name) $oldest.Name
      if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine("ledger-history: could not archive $($oldest.Name) (need tar.exe)"); break }
      Remove-Item -LiteralPath $oldest.FullName -Recurse -Force
      Say "archived $($oldest.Name) -> archive/$($oldest.Name).tar.gz (its record stays in history/)"
    } finally { Pop-Location }
  }
}

function Cmd-Status {
  $c = Get-SessionCount
  $gs = Get-OfficeSize; $hk = Get-Conf 'history_keep' 3; $ak = Get-Conf 'archive_keep' 12
  $opened = Get-OfficeOpened; if (-not $opened) { $opened = '-' }
  if (Test-Path -LiteralPath $officeDir) {
    Say "Live office:     memory/office (opened $opened)"
    Say "Sessions in it:  $c / $gs"
  } else {
    Say 'Live office:     none - memory/office missing (run: ledger-sync migrate)'
  }
  Say "history/:        $(Count-OfficeDirs) frozen office(s) readable, $(Count-Records) permanent record(s) (keep $hk)"
  Say "archive/:        $(Count-Archives) tarball(s) (cap $ak)"
  if ($c -ge $gs) {
    Say ''
    Say 'A close is DUE (>= office_size). The next worker through the door runs it'
    Say 'before working: ledger-history close   (then --confirm)'
  }
  if ((Count-Archives) -gt $ak) { Say 'gc is DUE: archive/ over cap. Run: ledger-history gc --confirm' }
}

function Cmd-Close {
  $milestone = ''; $confirm = $false
  for ($i = 0; $i -lt $RestArgs.Count; $i++) {
    switch ($RestArgs[$i]) {
      '--milestone' { if ($i + 1 -ge $RestArgs.Count) { Die '--milestone needs a label' }; $milestone = $RestArgs[++$i] }
      '--confirm' { $confirm = $true }
      default { Die "unknown argument '$($RestArgs[$i])'" }
    }
  }
  if (-not (Test-Path -LiteralPath $officeDir)) { Die "no $officeDir - run: ledger-sync migrate" }
  if (-not (Test-Path -LiteralPath $officeTpl)) { Die "$officeTpl missing - core is too old for the office layout; update core first" }
  $c = Get-SessionCount
  $int = Get-MaxOfficeNum
  $n = Pad ($int + 1)
  $targetDir = Join-Path $historyDir "office-$n"
  $record = Join-Path $historyDir "office-$n.md"
  $opened = Get-OfficeOpened; if (-not $opened) { $opened = '-' }
  Say "== Closing the live office -> office-$n =="
  Say "sessions: $c   opened: $opened   closing: $(Today)$(if ($milestone) { "   milestone: $milestone" })"
  $dirty = & git -C (Split-Path -Parent $ledgerDir) status --porcelain 2>$null
  if ($dirty) { Say 'notice: uncommitted changes present - the closing commit should include the frozen office move + record' }
  Say ''; Show-PrecloseChecklist; Say ''
  Say 'Plan:'
  Say "  - freeze memory/office verbatim -> $targetDir (nothing trimmed)"
  Say "  - write $record (permanent accomplishments record)"
  Say '  - open a fresh empty office from core/templates/memory/office/'
  Say '  - zip the oldest frozen office into archive/ if history/ exceeds keep'
  if (-not $confirm) { Say ''; Say 'Dry run - nothing changed. Re-run with --confirm once the checklist is done.'; return }

  New-Item -ItemType Directory -Path $historyDir -Force | Out-Null
  Move-Item -LiteralPath $officeDir -Destination $targetDir
  Say "froze memory/office -> $targetDir (verbatim)"

  $lines = @("# Office $n - accomplishments record (permanent)", '',
    "- Opened: $opened", "- Closed: $(Today)", "- Sessions: $c")
  if ($milestone) { $lines += "- Milestone: $milestone" }
  $lines += @('', "The frozen office lives at history/office-$n/ until it is zipped into archive/office-$n.tar.gz. This record stays in history/ forever - even after the tarball is garbage-collected, the office is never forgotten. Not read at session start; deliberate lookback only.", '')
  $lines += @(
    "<!-- FILL IN before committing the close - this is the office's permanent memory:",
    '## Accomplished',
    '- <what this office achieved - releases, milestones, work worth remembering>',
    '',
    '## Decisions still in force',
    '- <ADRs / working agreements the next office must respect - or "none">',
    '',
    '## Open threads',
    '- <actionable items re-seeded into the new office''s backlog (owner / next step),',
    '  plus the parking-lot findings, questions, and someday items worth keeping -',
    '  this record is where knowledge survives a close; the fresh queue does not',
    '  inherit it - or "none">',
    '-->'
  )
  # WriteAllText with UTF-8 without BOM: Set-Content on Windows PowerShell
  # mangles non-ASCII and adds a BOM; the record is a permanent file whose
  # bytes must match what the POSIX port writes (same convention as the
  # collab-event JSON writers).
  [IO.File]::WriteAllText($record, ($lines -join "`n") + "`n", (New-Object System.Text.UTF8Encoding $false))
  Say "wrote $record (fill it in before committing)"

  Copy-Item -Path $officeTpl -Destination $officeDir -Recurse
  Say 'opened a fresh memory/office (empty skeletons)'

  Roll-OldestOfficeToArchive
  Say ''
  Say "Then, before committing: fill in $record and re-seed open threads into the"
  Say "new office's backlog / flaws / decisions - only what still matters, and"
  Say "into the backlog only actionable work with an owner or next step (the"
  Say "parking lot's findings/questions go in the record, not the new queue)."
  Say ''
  Say "Commit as: chore(ledger): close office-$n, open a fresh office"
}

function Cmd-Gc {
  $confirm = ($RestArgs -contains '--confirm')
  $ak = Get-Conf 'archive_keep' 12
  $tarballs = @(Get-ChildItem -LiteralPath $archiveDir -Filter 'office-*.tar.gz' -File -ErrorAction SilentlyContinue | Sort-Object Name)
  if ($tarballs.Count -le $ak) { Say "archive/ holds $($tarballs.Count) tarball(s), cap $ak - nothing to delete."; return }
  $over = $tarballs.Count - $ak
  $doomed = $tarballs | Select-Object -First $over
  Say "archive/ over cap ($($tarballs.Count) > $ak). Oldest-first, $over tarball(s) to delete:"
  $doomed | ForEach-Object { Say "  - $($_.Name)" }
  Say '(recoverable from git history after deletion; the permanent records in history/ stay)'
  if (-not $confirm) { Say 'Dry run - nothing deleted. Re-run with --confirm to delete.'; return }
  $doomed | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force; Say "deleted $($_.Name)" }
  Say "Commit as: chore(ledger): gc archive/ to the $ak-tarball cap"
}

switch ($Command) {
  'status' { Cmd-Status; exit 0 }
  'close' { Cmd-Close; exit 0 }
  'gc' { Cmd-Gc; exit 0 }
  { $_ -in @('', '-h', '--help', 'help') } { Usage }
  default { Die "unknown command '$Command' (try: ledger-history.ps1 help)" }
}
