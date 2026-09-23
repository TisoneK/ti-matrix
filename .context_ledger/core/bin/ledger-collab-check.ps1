#!/usr/bin/env pwsh
# ledger-collab-check.ps1 -- Windows integration-readiness validator.
#
# SOURCE ENCODING - pure ASCII, on purpose. Windows PowerShell 5.1 decodes a
# BOM-less script with the *system codepage*, not UTF-8, so a non-ASCII byte
# here can fail the parse there (an em-dash decodes to U+201D, which the
# parser reads as a string terminator) while pwsh 7 parses it fine. Emit a
# character the sh port writes as a literal from its code point instead -
# [char]0x2014 em-dash, [char]0x2026 ellipsis - so both ports emit the same
# bytes. Enforced by `ledger-sync verify` and tests/run-tests.sh; rationale
# in core/CHANGELOG.md (2.0.4).

[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)] [string[]] $Arguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Say { param([string]$Message) Write-Output $Message }
function Fail { param([string]$Message) $script:Failures++; [Console]::Error.WriteLine("ledger-collab: check: $Message") }
function Die { param([string]$Message) [Console]::Error.WriteLine("ledger-collab: $Message"); exit 2 }
function Usage {
  @(
    'ledger-collab check [--session ID] [--issue ID]',
    '',
    'Validates event metadata, references, agreements, overlaps, resolutions, and releases.',
    'Notes (type: note) are informal and never gate integration.',
    'A claim counts as closed when a later release/handoff cites its event ID OR',
    'shares its session+issue and overlaps its paths (weak-agent / SHA-only case).',
    'Exit codes: 0 passed | 1 validation failure | 2 usage/error'
  ) | ForEach-Object { Say $_ }
  exit 2
}

$scriptDir = $PSScriptRoot
$coreDir = (Resolve-Path (Join-Path $scriptDir '..')).Path
$ledgerDir = Split-Path -Parent $coreDir
$eventDir = Join-Path $ledgerDir 'memory/collaboration/events'

# Parse each event ONCE and cache it (keyed by full path). JSON documents
# (<id>.json, the current format) and legacy markdown frontmatter (<id>.md)
# normalize into the same hashtable: null/[] -> 'none', arrays -> comma-
# joined, so every downstream rule stays format-blind. TrimEnd("`r") keeps
# markdown parsing correct on CRLF (Windows) checkouts.
$script:FileFields = @{}
function Get-Fields { param([IO.FileInfo]$File)
  if ($script:FileFields.ContainsKey($File.FullName)) { return $script:FileFields[$File.FullName] }
  $h = @{}
  $first = [IO.File]::ReadLines($File.FullName) | Select-Object -First 1
  if ($null -ne $first -and $first.TrimEnd("`r") -match '^\{') {
    $obj = [IO.File]::ReadAllText($File.FullName) | ConvertFrom-Json
    foreach ($prop in $obj.PSObject.Properties) {
      if ($null -eq $prop.Value) { $h[$prop.Name] = 'none' }
      elseif ($prop.Value -is [System.Array]) {
        if ($prop.Value.Count -eq 0) { $h[$prop.Name] = 'none' }
        else { $h[$prop.Name] = (@($prop.Value | ForEach-Object { [string]$_ }) -join ',') }
      }
      else { $h[$prop.Name] = [string]$prop.Value }
    }
  } else {
    $dashes = 0
    foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $File.FullName) {
      $ln = $raw.TrimEnd("`r")
      if ($ln -eq '---') { $dashes++; if ($dashes -ge 2) { break }; continue }
      if ($dashes -eq 1 -and $ln -match '^([a-z]+): (.*)$') { $h[$matches[1]] = $matches[2] }
    }
  }
  $script:FileFields[$File.FullName] = $h
  return $h
}
function Get-Field { param([IO.FileInfo]$File, [string]$Name)
  $h = Get-Fields $File
  if ($h.ContainsKey($Name)) { return $h[$Name] } else { return '' }
}
function Valid-Id { param([string]$Value) return ($Value -match '^[A-Za-z0-9._:-]+$') }
function Valid-Sha { param([string]$Value) return ($Value -match '^[0-9A-Fa-f]{7,40}$') }
function In-Scope { param([IO.FileInfo]$File)
  return (($script:Session -eq '' -or (Get-Field $File 'session') -eq $script:Session) -and
          ($script:Issue -eq '' -or (Get-Field $File 'issue') -eq $script:Issue))
}
function Event-By-Id { param([string]$Id)
  return @($script:Files | Where-Object { (Get-Field $_ 'id') -eq $Id } | Select-Object -First 1)
}
function Refs { param([IO.FileInfo]$File)
  $value = Get-Field $File 'refs'
  if ($value -eq 'none' -or $value -eq '') { return @() }
  return @($value.Split(',') | Where-Object { $_ -ne '' })
}
function Has-Ref-Type { param([IO.FileInfo]$File, [string]$Type)
  foreach ($ref in (Refs $File)) {
    $target = @(Event-By-Id $ref)
    if ($target.Count -gt 0 -and (Get-Field $target[0] 'type') -eq $Type) { return $true }
  }
  return $false
}
function Referenced-By-Type { param([string]$Id, [string]$Type)
  $target = @(Event-By-Id $Id)
  if ($target.Count -eq 0) { return $false }
  $session = Get-Field $target[0] 'session'; $issue = Get-Field $target[0] 'issue'
  foreach ($file in $script:Files) {
    if ((Get-Field $file 'type') -eq $Type -and
        (Get-Field $file 'session') -eq $session -and
        (Get-Field $file 'issue') -eq $issue -and
        (Refs $file) -contains $Id) { return $true }
  }
  return $false
}
function Has-NonEventRef { param([IO.FileInfo]$File)
  foreach ($ref in (Refs $File)) { if (@(Event-By-Id $ref).Count -eq 0 -and (Valid-Sha $ref)) { return $true } }
  return $false
}
function Claim-Closed { param([string]$Id)
  # Split into named booleans: `Cmd a -or Cmd b` inside an if() does not
  # evaluate as two command calls in expression mode - every other call site
  # parenthesizes; this one now does too.
  $released = Referenced-By-Type $Id 'release'
  $handedOff = Referenced-By-Type $Id 'handoff'
  if ($released -or $handedOff) { return $true }
  # weak-agent fallback: a release/handoff sharing this claim's session+issue
  # and overlapping its paths closes it even when it cites only a commit SHA.
  $target = @(Event-By-Id $Id)
  if ($target.Count -eq 0) { return $false }
  $ses = Get-Field $target[0] 'session'; $iss = Get-Field $target[0] 'issue'; $paths = Get-Field $target[0] 'paths'
  foreach ($file in $script:Files) {
    if ((Get-Field $file 'type') -notin @('release','handoff')) { continue }
    if ((Get-Field $file 'session') -eq $ses -and (Get-Field $file 'issue') -eq $iss -and (Overlap $paths (Get-Field $file 'paths'))) { return $true }
  }
  return $false
}
# Does a claim exist that this release/handoff corresponds to (shared
# session+issue + path overlap)? The SHA-only / weak-agent case.
function Matches-Claim { param([IO.FileInfo]$File)
  $ses = Get-Field $File 'session'; $iss = Get-Field $File 'issue'; $paths = Get-Field $File 'paths'
  foreach ($f in $script:Files) {
    if ((Get-Field $f 'type') -ne 'claim') { continue }
    if ((Get-Field $f 'session') -eq $ses -and (Get-Field $f 'issue') -eq $iss -and (Overlap $paths (Get-Field $f 'paths'))) { return $true }
  }
  return $false
}
# Is this scope eventually released (by event-ID ref, or session+issue+paths)?
function Has-Release-For { param([IO.FileInfo]$File)
  if (Referenced-By-Type (Get-Field $File 'id') 'release') { return $true }
  $ses = Get-Field $File 'session'; $iss = Get-Field $File 'issue'; $paths = Get-Field $File 'paths'
  foreach ($f in $script:Files) {
    if ((Get-Field $f 'type') -ne 'release') { continue }
    if ((Get-Field $f 'session') -eq $ses -and (Get-Field $f 'issue') -eq $iss -and (Overlap $paths (Get-Field $f 'paths'))) { return $true }
  }
  return $false
}
function Csv-Contains { param([string]$Csv, [string]$Value)
  return ((',' + $Csv + ',') -like "*,$Value,*")
}
function Distinct-Count { param([string]$Csv)
  return @($Csv.Split(',') | Where-Object { $_ -and $_ -ne 'none' } | Sort-Object -Unique).Count
}
function Overlap { param([string]$Left, [string]$Right)
  $leftPaths = $Left.Split(','); $rightPaths = $Right.Split(',')
  foreach ($leftPath in $leftPaths) {
    if ($leftPath -ne 'none' -and $rightPaths -contains $leftPath) { return $true }
  }
  return $false
}

function Check-Event { param([IO.FileInfo]$File)
  if (-not (In-Scope $File)) { return }
  $id = Get-Field $File 'id'; $type = Get-Field $File 'type'
  foreach ($key in @('id','type','session','agent','created','issue','paths','refs','option','selected','owner','participants')) {
    if (-not (Get-Field $File $key)) { Fail "$($File.Name) is missing $key" }
  }
  if (-not (Valid-Id $id)) { Fail "$($File.Name) has invalid id '$id'" }
  if ($type -notin @('note','claim','proposal','assessment','agreement','correction','handoff','release')) {
    Fail "$($File.Name) has unknown type '$type'"; return
  }
  # Notes are informal -- their --re may be a path, URL, event, or commit, so
  # they are exempt from reference validation (and carry no requirements).
  if ($type -ne 'note') {
    foreach ($ref in (Refs $File)) {
      $target = @(Event-By-Id $ref)
      if ($target.Count -gt 0) {
        if ((Get-Field $target[0] 'session') -ne (Get-Field $File 'session')) { Fail "$id references event $ref from another session" }
        if ((Get-Field $target[0] 'issue') -ne (Get-Field $File 'issue')) { Fail "$id references event $ref from another issue" }
      } elseif (-not (Valid-Sha $ref)) {
        Fail "$id has unknown reference '$ref' (expected an event ID or commit SHA)"
      }
    }
  }
  switch ($type) {
    'claim' { if ((Get-Field $File 'paths') -eq 'none') { Fail "claim $id has no paths" } }
    'proposal' { if ((Get-Field $File 'option') -eq 'none') { Fail "proposal $id has no option" } }
    'assessment' { if (-not (Has-Ref-Type $File 'proposal')) { Fail "assessment $id does not reference a proposal" } }
    'agreement' {
      if (-not (Has-Ref-Type $File 'proposal')) { Fail "agreement $id does not reference a proposal" }
      if (-not (Has-Ref-Type $File 'assessment')) { Fail "agreement $id does not reference an assessment" }
      $selected = Get-Field $File 'selected'; $owner = Get-Field $File 'owner'; $participants = Get-Field $File 'participants'
      if ($selected -eq 'none') { Fail "agreement $id has no selected option" }
      if ($owner -eq 'none') { Fail "agreement $id has no owner" }
      if ($participants -eq 'none') { Fail "agreement $id has no participants" }
      if (-not (Csv-Contains $participants $owner)) { Fail "agreement $id owner is not a participant" }
      if ((Distinct-Count $participants) -lt 2) { Fail "agreement $id needs at least two distinct participants" }
      $selectedFound = $false
      foreach ($ref in (Refs $File)) {
        $target = @(Event-By-Id $ref)
        if ($target.Count -gt 0 -and (Get-Field $target[0] 'type') -eq 'proposal' -and (Get-Field $target[0] 'option') -eq $selected) { $selectedFound = $true }
      }
      if (-not $selectedFound) { Fail "agreement $id selects an option not present in its referenced proposals" }
    }
    'correction' { if (-not (Referenced-By-Type $id 'agreement')) { Fail "correction $id has no peer agreement" } }
    'handoff' {
      if ((Get-Field $File 'owner') -eq 'none') { Fail "handoff $id has no receiving owner" }
      if (-not (Has-Ref-Type $File 'claim') -and -not (Has-Ref-Type $File 'handoff') -and
          -not (Has-Ref-Type $File 'agreement') -and -not (Matches-Claim $File)) {
        Fail "handoff $id does not reference the scope being handed off (a claim, prior handoff, or agreement)"
      }
    }
    'release' {
      if (-not (Has-Ref-Type $File 'claim') -and -not (Has-Ref-Type $File 'handoff') -and -not (Matches-Claim $File)) {
        Fail "release $id does not correspond to a claim or handoff (reference it, or share its issue and paths)"
      }
      if (-not (Has-NonEventRef $File)) { Fail "release $id does not reference a product commit" }
    }
  }
}

function Check-Duplicates {
  for ($i = 0; $i -lt $script:Files.Count; $i++) {
    if (-not (In-Scope $script:Files[$i])) { continue }
    for ($j = 0; $j -lt $i; $j++) {
      if ((In-Scope $script:Files[$j]) -and (Get-Field $script:Files[$i] 'id') -eq (Get-Field $script:Files[$j] 'id')) {
        Fail "duplicate event id $(Get-Field $script:Files[$i] 'id')"
      }
    }
  }
}
function Check-Overlaps {
  $claims = @($script:Files | Where-Object { (In-Scope $_) -and (Get-Field $_ 'type') -eq 'claim' -and -not (Claim-Closed (Get-Field $_ 'id')) })
  for ($i = 0; $i -lt $claims.Count; $i++) {
    for ($j = $i + 1; $j -lt $claims.Count; $j++) {
      if ((Get-Field $claims[$i] 'session') -eq (Get-Field $claims[$j] 'session') -and
          (Get-Field $claims[$i] 'issue') -eq (Get-Field $claims[$j] 'issue') -and
          (Overlap (Get-Field $claims[$i] 'paths') (Get-Field $claims[$j] 'paths'))) {
        Fail "active claims overlap: $(Get-Field $claims[$i] 'id') and $(Get-Field $claims[$j] 'id') -- talk it through and agree who takes it"
      }
    }
  }
}
function Check-Resolutions {
  foreach ($file in $script:Files) {
    if (-not (In-Scope $file)) { continue }
    $id = Get-Field $file 'id'; $type = Get-Field $file 'type'
    switch ($type) {
      'claim' { if (-not (Claim-Closed $id)) { Fail "claim $id is not released or handed off" } }
      { $_ -in @('proposal','assessment') } { if (-not (Referenced-By-Type $id 'agreement')) { Fail "$type $id is not resolved by an agreement" } }
      'handoff' { if (-not (Has-Release-For $file)) { Fail "handoff $id is not released" } }
    }
  }
}

$script:Session = ''; $script:Issue = ''
# Not $args: assigning the automatic variable fails under StrictMode, and an
# @() emitted by an if-expression unwraps to $null -- so build the array by
# direct assignment and guard the read against .Count on $null.
$positional = @()
if ($null -ne $Arguments) { $positional = @($Arguments) }
for ($i = 0; $i -lt $positional.Count; $i++) {
  switch ($positional[$i]) {
    '--session' { if ($i + 1 -ge $positional.Count) { Die '--session needs a value' }; $script:Session = $positional[++$i] }
    '--issue' { if ($i + 1 -ge $positional.Count) { Die '--issue needs a value' }; $script:Issue = $positional[++$i] }
    '-h' { Usage }
    '--help' { Usage }
    default { Die "unknown argument '$($positional[$i])'" }
  }
}
if ($script:Session -and -not (Valid-Id $script:Session)) { Die "invalid session id: $($script:Session)" }
if ($script:Issue -and -not (Valid-Id $script:Issue)) { Die "invalid issue id: $($script:Issue)" }

$script:Files = @(Get-ChildItem -LiteralPath $eventDir -File -ErrorAction SilentlyContinue |
  Where-Object { $_ -and ($_.Extension -eq '.md' -or $_.Extension -eq '.json') })
if (-not $script:Files -or $script:Files.Count -eq 0) { Say 'collaboration check: no events (nothing to check)'; exit 0 }
$script:Failures = 0
foreach ($file in $script:Files) { Check-Event $file }
Check-Duplicates
Check-Overlaps
Check-Resolutions
if ($script:Failures -gt 0) {
  [Console]::Error.WriteLine("ledger-collab: collaboration check failed: $($script:Failures) problem(s)")
  exit 1
}
Say "collaboration check passed: $($script:Files.Count) event(s), all claims resolved and agreements/releases complete"
