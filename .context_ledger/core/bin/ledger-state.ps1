#!/usr/bin/env pwsh
# ledger-state.ps1 - Windows port of ledger-state (STATE.md digest generator).
#
# Regenerates memory/office/STATE.md, a single at-a-glance session digest,
# so kickoff Phase 3 reads one ~30-60 line file instead of 8+ separate ones.
# STATE.md is a DERIVED VIEW, never hand-edited - see ledger-state (sh) for
# the full rationale; this port must stay behaviorally identical.
#
# SOURCE ENCODING - pure ASCII, on purpose. Windows PowerShell 5.1 decodes a
# BOM-less script with the *system codepage*, not UTF-8, so a non-ASCII byte
# here can fail the parse there (an em-dash decodes to U+201D, which the
# parser reads as a string terminator) while pwsh 7 parses it fine. Emit a
# character the sh port writes as a literal from its code point instead -
# [char]0x2014 em-dash, [char]0x2026 ellipsis - so both ports emit the same
# bytes (see $EmDash/$Ellipsis below; STATE.md is byte-identical to the sh
# port's). Enforced by `ledger-sync verify` and tests/run-tests.sh;
# rationale in core/CHANGELOG.md (2.0.4).

[CmdletBinding()]
param(
  [Parameter(Position = 0)] [string] $Command = '',
  [Parameter(ValueFromRemainingArguments = $true)] [string[]] $RestArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Say { param([string]$Message) Write-Output $Message }
function ErrLine { param([string]$Message) [Console]::Error.WriteLine("ledger-state: $Message") }
function Die { param([string]$Message) ErrLine $Message; exit 2 }

$scriptDir = $PSScriptRoot
$coreDir = (Resolve-Path (Join-Path $scriptDir '..')).Path
$ledgerDir = Split-Path -Parent $coreDir
$memoryDir = Join-Path $ledgerDir 'memory'
$officeDir = Join-Path $memoryDir 'office'
$outFile = Join-Path $officeDir 'STATE.md'

# See SOURCE ENCODING above: these stand in for the literals the sh port uses.
$EmDash = [char]0x2014
$Ellipsis = [char]0x2026

function Usage {
  @(
    "ledger-state $EmDash regenerate the memory/office/STATE.md session digest",
    '',
    '  generate   read the underlying memory files and (re)write STATE.md.',
    '             Safe to run any time; it never touches anything but',
    '             STATE.md itself. Called at check-in (kickoff Phase 2)',
    '             and at exit (ledger-gates run exit).',
    '',
    'Exit codes: 0 ok; 2 usage/error'
  ) | ForEach-Object { Say $_ }
  exit 2
}

function Get-Lines { param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return @() }
  return @(Get-Content -Encoding UTF8 -LiteralPath $Path | ForEach-Object { $_.TrimEnd("`r") })
}

# one-line field grab: last "- **Label:** value" line (every source file
# here is overwrite/update-in-place, so the last match is the current
# one). Skips <!-- --> blocks: a key mentioned only in the file's own
# template comment (never given a real line yet, e.g. a freshly
# bootstrapped skeleton) must read as empty, not leak the comment's
# placeholder text as if it were live data.
function Get-Field { param([string]$Path, [string]$Label)
  $val = ''
  $intpl = $false
  foreach ($line in (Get-Lines $Path)) {
    if (-not $intpl -and $line -match '^<!--') { if ($line -notmatch '-->') { $intpl = $true }; continue }
    if ($intpl) { if ($line -match '-->') { $intpl = $false }; continue }
    # ${Label} not $Label: the following ':' would parse as a scope qualifier
    # (like $env:), which no PowerShell engine accepts.
    if ($line -match "^\s*[-*]\s*\*\*${Label}:\*\*\s*(.*)$") { $val = $Matches[1] }
  }
  return $val
}

function Truncate-Line { param([string]$Text, [int]$Max)
  if ($Text.Length -gt $Max) { return $Text.Substring(0, $Max - 1) + $Ellipsis }
  return $Text
}

function CoreBlock {
  $verFile = Join-Path $coreDir 'VERSION'
  $lockFile = Join-Path $memoryDir 'core.lock'
  $installed = if (Test-Path -LiteralPath $verFile) { (Get-Content -Encoding UTF8 -LiteralPath $verFile | Select-Object -First 1).Trim() } else { 'unknown' }
  $locked = ''; $verified = ''
  if (Test-Path -LiteralPath $lockFile) {
    foreach ($line in (Get-Lines $lockFile)) {
      if ($line -match '^version=(.*)$') { $locked = $Matches[1] }
      if ($line -match '^verified=(.*)$') { $verified = $Matches[1] }
    }
  }
  if ($locked -ne '' -and $locked -ne $installed) {
    $drift = " $EmDash MISMATCH vs core.lock ($locked, verified $verified): run ``ledger-sync verify``"
  } elseif ($locked -ne '') {
    $drift = " (locked, verified $verified)"
  } else {
    $drift = ' (never locked ' + $EmDash + ' run `ledger-sync verify`)'
  }
  Say "- **Core:** $installed$drift"
}

function StandingParams {
  $f = Join-Path $memoryDir 'workflows/active.md'
  if (-not (Test-Path -LiteralPath $f)) { Say '- (no workflows/active.md)'; return }
  $push = Get-Field $f 'Push policy'
  $target = Get-Field $f 'Target'
  $scope = Get-Field $f 'Scope'
  if ($target -ne '') { Say "- **Target:** $target" }
  if ($scope -ne '') { Say "- **Scope:** $scope" }
  if ($push -ne '') { Say "- **Push policy:** $push" }
  Say '- Full params: `memory/workflows/active.md`'
}

function RosterBlock {
  $f = Join-Path $officeDir 'agents/roster.md'
  if (-not (Test-Path -LiteralPath $f)) { Say '(no roster.md)'; return }
  $rows = @()
  foreach ($line in (Get-Lines $f)) {
    if ($line -notmatch '^\s*\|') { continue }
    $c = $line.Split('|')
    if ($c.Count -lt 4) { continue }
    $name = $c[1].Trim(); $code = $c[2].Trim()
    if ($code -notmatch '^[Ss][0-9]+$') { continue }
    $doing = if ($c.Count -ge 5) { $c[4].Trim() } else { '' }
    $status = if ($c.Count -ge 6) { $c[5].Trim() } else { '' }
    $rows += [pscustomobject]@{ Name = $name; Code = $code; Status = $status; Doing = $doing }
  }
  if ($rows.Count -eq 0) { Say "(office empty $EmDash no live roster rows)"; return }
  foreach ($r in $rows) {
    Say "- **$($r.Name)** ($($r.Code)) $EmDash $($r.Status) $EmDash $(Truncate-Line $r.Doing 90)"
  }
}

function CurrentTaskBlock {
  $f = Join-Path $officeDir 'tasks/current.md'
  if (-not (Test-Path -LiteralPath $f)) { Say '(no tasks/current.md)'; return }
  $task = Get-Field $f 'Task'
  $status = Get-Field $f 'Status'
  $session = Get-Field $f 'Session'
  if ($task -eq '') { Say "(idle $EmDash no task recorded)"; return }
  Say "- **$session** $EmDash $(Truncate-Line $task 140) $EmDash *$status*"
}

function BacklogBlock {
  $f = Join-Path $officeDir 'tasks/backlog.md'
  if (-not (Test-Path -LiteralPath $f)) { Say '(no backlog.md)'; return }
  $sect = ''; $high = @(); $mn = 0; $ln = 0
  foreach ($line in (Get-Lines $f)) {
    if ($line -match '^### High Priority') { $sect = 'H'; continue }
    if ($line -match '^### Medium Priority') { $sect = 'M'; continue }
    if ($line -match '^### Low Priority') { $sect = 'L'; continue }
    if ($line -match '^## ') { $sect = '' }
    if ($sect -ne '' -and $line -match '^\s*\|\s*B-[0-9]') {
      if ($sect -eq 'H') { $high += $line } elseif ($sect -eq 'M') { $mn++ } elseif ($sect -eq 'L') { $ln++ }
    }
  }
  if ($high.Count -eq 0) { Say '(none)' } else { $high | ForEach-Object { Say $_ } }
  Say ''
  Say "_$mn medium, $ln low priority row(s) $EmDash see tasks/backlog.md_"
}

# style: 'date' (## YYYY-MM-DD ...) or 'adr' (## ADR-N: ... (YYYY-MM-DD))
function LogDigest { param([string]$Rel, [string]$Label, [string]$Style)
  $f = Join-Path $officeDir $Rel
  if (-not (Test-Path -LiteralPath $f)) { Say "- ${Label}: (no file)"; return }
  $n = 0; $last = ''
  $intpl = $false
  foreach ($line in (Get-Lines $f)) {
    if (-not $intpl -and $line -match '^<!--') { if ($line -notmatch '-->') { $intpl = $true }; continue }
    if ($intpl) { if ($line -match '-->') { $intpl = $false }; continue }
    if ($Style -eq 'date' -and $line -match '^## (\d{4}-\d{2}-\d{2})') {
      $n++; if ($Matches[1] -gt $last) { $last = $Matches[1] }
    }
    if ($Style -eq 'adr' -and $line -match '^## ADR-[0-9]') {
      $n++
      if ($line -match '\((\d{4}-\d{2}-\d{2})\)\s*$') { if ($Matches[1] -gt $last) { $last = $Matches[1] } }
    }
  }
  if ($n -eq 0) { Say "- ${Label}: 0 entries" }
  elseif ($last -ne '') { Say "- ${Label}: $n entr$(if ($n -eq 1) {'y'} else {'ies'}), last added $last" }
  else { Say "- ${Label}: $n entr$(if ($n -eq 1) {'y'} else {'ies'})" }
}

function CollabBlock {
  $dir = Join-Path $memoryDir 'collaboration/events'
  if (-not (Test-Path -LiteralPath $dir)) { Say "(no collaboration/events $EmDash collaboration never used)"; return }
  $files = @(Get-ChildItem -LiteralPath $dir -Filter '*.json' -File -ErrorAction SilentlyContinue | Sort-Object Name)
  if ($files.Count -eq 0) { Say '(no events yet)'; return }
  $lastFile = $files[-1].Name
  Say "- $($files.Count) event(s) on file; most recent: ``$lastFile``"
  Say '- Full trail + rules: `memory/collaboration/README.md`; live status: `ledger-collab status --session <S> --issue <slug>`'
}

function Invoke-Generate {
  if (-not (Test-Path -LiteralPath $officeDir)) { Die "no memory/office/ directory $EmDash is this a bootstrapped project?" }
  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add("# STATE $EmDash session digest")
  $lines.Add('')
  $lines.Add('<!-- GENERATED by `ledger-state generate` ' + $EmDash + ' never hand-edit. Regenerated')
  $lines.Add('at check-in and at exit. This is a DERIVED VIEW for fast orientation;')
  $lines.Add('open the file a line points at when your task needs more than the')
  $lines.Add('line gives you. Full reading order: ledger-schema.md. -->')
  $lines.Add('')
  $lines.Add("_Regenerated: $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))_")
  $lines.Add('')
  $lines.Add('## Standing params')
  # capture each block function's Say/Write-Output lines into $lines
  function Capture { param([scriptblock]$Block)
    $out = & $Block
    foreach ($l in $out) { $lines.Add([string]$l) }
  }
  Capture { CoreBlock }
  Capture { StandingParams }
  $lines.Add('')
  $lines.Add("## Office $EmDash who's in, right now")
  Capture { RosterBlock }
  $lines.Add('')
  $lines.Add('## Current task')
  Capture { CurrentTaskBlock }
  $lines.Add('')
  $lines.Add("## Backlog $EmDash High priority (the top of the queue)")
  Capture { BacklogBlock }
  $lines.Add('')
  $lines.Add("## Logs at a glance $EmDash open only if your task touches these")
  Capture { LogDigest 'flaws/log.md' 'flaws/log.md (protocol/.context_ledger friction)' 'date' }
  Capture { LogDigest 'inefficiencies/log.md' 'inefficiencies/log.md (project code/env friction)' 'date' }
  Capture { LogDigest 'plans/decisions.md' "plans/decisions.md (ADRs in force $EmDash respected, not relitigated)" 'adr' }
  $lines.Add('')
  $lines.Add('## Collaboration')
  Capture { CollabBlock }

  $utf8 = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($outFile, ($lines -join "`n") + "`n", $utf8)
  Say 'ledger-state: wrote STATE.md'
}

switch ($Command) {
  'generate' {
    if ($RestArgs -contains '-h' -or $RestArgs -contains '--help') { Usage }
    if ($RestArgs.Count -gt 0) { Die "unknown argument '$($RestArgs[0])'" }
    Invoke-Generate
    exit 0
  }
  { $_ -in @('', '-h', '--help', 'help') } { Usage }
  default { Die "unknown command '$Command' (try: ledger-state.ps1 help)" }
}
