#!/usr/bin/env pwsh
# ledger-collab.ps1 -- PowerShell peer coordination helper.
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
# Coordination state is immutable, one-file-per-event under
# .context_ledger/memory/collaboration/events/. Product changes still belong on an
# isolated branch/worktree and are never merged by this helper.
#
# Events are JSON documents (schema: core/schemas/collab-event.schema.json)
# written in the same strict profile as the sh tool (one "key": value per
# line, UTF-8 without BOM) so both platforms produce identical bytes.
# Legacy markdown events (<id>.md) are still read by status and check.
#
# Usage:
#   .context_ledger/core/bin/ledger-collab.cmd emit claim `
#     --session ID --agent ID --issue ID --paths src/a.py `
#     --body-file C:\path\claim.md
#   .context_ledger/core/bin/ledger-collab.cmd status --session ID --issue ID
#   .context_ledger/core/bin/ledger-collab.cmd check --session ID --issue ID

[CmdletBinding()]
param(
  [Parameter(Position = 0)] [string] $Command = '',
  [Parameter(Position = 1)] [string] $Type = '',
  [Parameter(Position = 2, ValueFromRemainingArguments = $true)] [string[]] $Extra
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Say { param([string]$Message) Write-Output $Message }
function Die { param([string]$Message) [Console]::Error.WriteLine("ledger-collab: $Message"); exit 1 }
function Usage {
  @(
    'Commands:',
    '  emit TYPE --session ID --agent ID --issue ID [metadata] [--body-file FILE]',
    '  status [--session ID] [--issue ID]',
    '  check  [--session ID] [--issue ID]   integration-readiness gate',
    '',
    'Metadata: --paths CSV --refs/--re CSV --option ID --selected ID --owner ID',
    '          --participants CSV --to CSV (note recipients) --body TEXT --body-file FILE',
    '',
    'Event types: note claim proposal assessment agreement correction handoff release',
    '  note -- the office channel: an informal heads-up to peers. Only a body',
    '         is required; never gates integration. The proposal/assessment/',
    '         agreement ceremony is reserved for a genuine conflict.'
  ) | ForEach-Object { Say $_ }
  exit 2
}

$scriptDir = $PSScriptRoot
$coreDir = (Resolve-Path (Join-Path $scriptDir '..')).Path
$ledgerDir = Split-Path -Parent $coreDir
$eventDir = Join-Path $ledgerDir 'memory/collaboration/events'

function Validate-Value { param([string]$Name, [string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value) -or $Value.Contains("`n") -or $Value.Contains("`r")) {
    Die "$Name cannot be empty or contain a newline"
  }
}
function Validate-Id { param([string]$Name, [string]$Value)
  Validate-Value $Name $Value
  if ($Value -notmatch '^[A-Za-z0-9._:-]+$') { Die "$Name may contain only letters, numbers, '.', '_', ':' or '-'" }
}
function Metadata { param([string]$Name, [string]$Value)
  if ($Value -eq '') { return 'none' } else { return $Value }
}
# NOTE: never name a PowerShell parameter $Args - it collides with the
# automatic variable of the same name, and flag tokens (--session ...)
# are silently lost before the loop ever sees them.
function Parse-Options { param([string[]]$OptArgs)
  $result = @{
    session = ''; agent = ''; issue = ''; paths = 'none'; refs = 'none'; option = 'none'
    selected = 'none'; owner = 'none'; participants = 'none'; body = ''; bodyFile = ''
  }
  for ($i = 0; $i -lt $OptArgs.Count; $i++) {
    $key = $OptArgs[$i]
    if ($key -in @('--session','--agent','--issue','--paths','--refs','--re','--option','--selected','--owner','--participants','--to','--body','--body-file')) {
      if ($i + 1 -ge $OptArgs.Count) { Die "$key needs a value" }
      $name = switch ($key) {
        '--body-file' { 'bodyFile' }
        '--re' { 'refs' }        # informal alias, mainly for notes
        '--to' { 'participants' } # a note's addressed peer(s)
        default { $key.Substring(2) }
      }
      $result[$name] = $OptArgs[$i + 1]; $i++
    } elseif ($key -in @('-h','--help')) { Usage }
    else { Die "unknown argument '$key'" }
  }
  return $result
}
function ConvertTo-JsonEscaped { param([string]$Text)
  # Backslash first, then quote, then the escapable control chars.
  return $Text.Replace('\', '\\').Replace('"', '\"').Replace("`t", '\t').Replace("`r", '\r').Replace("`n", '\n')
}
function ConvertTo-JsonArray { param([string]$Csv)
  if (-not $Csv -or $Csv -eq 'none') { return '[]' }
  $items = @($Csv -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ } | ForEach-Object { '"' + (ConvertTo-JsonEscaped $_) + '"' })
  if ($items.Count -eq 0) { return '[]' }
  return '[' + ($items -join ', ') + ']'
}
function ConvertTo-JsonScalar { param([string]$Value)
  if (-not $Value -or $Value -eq 'none') { return 'null' }
  return '"' + (ConvertTo-JsonEscaped $Value) + '"'
}
function Test-JsonFile { param([IO.FileInfo]$File)
  $first = [IO.File]::ReadLines($File.FullName) | Select-Object -First 1
  return ($null -ne $first -and $first.TrimEnd("`r") -match '^\{')
}
# JSON value -> the same field value the markdown parser produces:
# null/[] -> 'none', arrays -> comma-joined, strings -> unescaped.
function Get-JsonField { param([IO.FileInfo]$File, [string]$Name)
  $obj = [IO.File]::ReadAllText($File.FullName) | ConvertFrom-Json
  $prop = $obj.PSObject.Properties[$Name]
  if ($null -eq $prop) { return '' }
  if ($null -eq $prop.Value) { return 'none' }
  if ($prop.Value -is [System.Array]) {
    if ($prop.Value.Count -eq 0) { return 'none' }
    return (@($prop.Value | ForEach-Object { [string]$_ }) -join ',')
  }
  return [string]$prop.Value
}
function Get-Field { param([IO.FileInfo]$File, [string]$Name)
  if (Test-JsonFile $File) { return Get-JsonField $File $Name }
  $pattern = "^${Name}: (.*)$"
  $line = Get-Content -Encoding UTF8 -LiteralPath $File.FullName | Where-Object { $_ -match $pattern } | Select-Object -First 1
  if ($null -eq $line) { return '' } else { return (($line -replace $pattern, '$1').TrimEnd("`r")) }
}
# First non-empty body line, for the chatter feed.
function Get-FirstBodyLine { param([IO.FileInfo]$File)
  if (Test-JsonFile $File) {
    $body = Get-JsonField $File 'body'
    if ($body -eq 'none' -or $body -eq '') { return '' }
    foreach ($ln in ($body -split "`n")) { if ($ln.Trim() -ne '') { return $ln } }
    return ''
  }
  $dashes = 0
  foreach ($raw in Get-Content -Encoding UTF8 -LiteralPath $File.FullName) {
    $ln = $raw.TrimEnd("`r")
    if ($ln -eq '---') { $dashes++; continue }
    if ($dashes -ge 2 -and $ln.Trim() -ne '') { return $ln }
  }
  return ''
}

function Emit { param([string]$EventType, [string[]]$EventArgs)
  if ($EventType -notin @('note','claim','proposal','assessment','agreement','correction','handoff','release')) {
    Die "unknown event type '$EventType'"
  }
  $o = Parse-Options $EventArgs
  Validate-Id 'session' $o.session; Validate-Id 'agent' $o.agent; Validate-Id 'issue' $o.issue
  Validate-Value 'paths' $o.paths; Validate-Value 'refs' $o.refs; Validate-Id 'option' $o.option
  Validate-Id 'selected' $o.selected; Validate-Id 'owner' $o.owner; Validate-Value 'participants' $o.participants
  if ($EventType -eq 'claim' -and $o.paths -eq 'none') { Die 'claim requires --paths' }
  if ($EventType -eq 'proposal' -and $o.option -eq 'none') { Die 'proposal requires --option' }
  if ($EventType -in @('assessment','correction','handoff','release') -and $o.refs -eq 'none') { Die "$EventType requires --refs" }
  if ($EventType -eq 'agreement') {
    if ($o.refs -eq 'none') { Die 'agreement requires --refs' }
    if ($o.selected -eq 'none') { Die 'agreement requires --selected' }
    if ($o.owner -eq 'none') { Die 'agreement requires --owner' }
    if ($o.participants -eq 'none') { Die 'agreement requires --participants' }
  }
  if ($o.bodyFile -and $o.body) { Die 'use either --body or --body-file, not both' }
  if ($o.bodyFile) {
    if (-not (Test-Path -LiteralPath $o.bodyFile -PathType Leaf)) { Die "body file not found: $($o.bodyFile)" }
    $body = Get-Content -Encoding UTF8 -LiteralPath $o.bodyFile -Raw
  } elseif ($o.body) { $body = $o.body }
  elseif ($EventType -eq 'claim') { $body = 'Intent and evidence: describe the intended change and why this scope is safe.' }
  elseif ($EventType -eq 'note') { Die 'note requires --body or --body-file -- say what you want your peers to know' }
  else { Die "$EventType requires --body-file or --body with evidence and reasoning" }

  New-Item -ItemType Directory -Path $eventDir -Force | Out-Null
  $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmss'Z'")
  $random = [Guid]::NewGuid().ToString('N').Substring(0, 8)
  $id = "$stamp-$($o.agent)-$random"
  $target = Join-Path $eventDir "$id.json"
  $temp = Join-Path $eventDir ".$id.$PID.tmp"
  $created = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
  $body = $body.TrimEnd("`r", "`n")
  if ($body -match '[\x00-\x08\x0B\x0C\x0E-\x1F]') {
    Die 'body contains control characters (tab, newline, and CR are the only ones allowed)'
  }
  # Strict profile: fixed key order, one "key": value per line, UTF-8
  # without BOM - byte-compatible with the sh writer.
  $json = @(
    '{',
    '  "schema": 1,',
    "  `"id`": `"$id`",",
    "  `"type`": `"$EventType`",",
    "  `"session`": `"$($o.session)`",",
    "  `"agent`": `"$($o.agent)`",",
    "  `"created`": `"$created`",",
    "  `"issue`": `"$($o.issue)`",",
    "  `"body`": `"$(ConvertTo-JsonEscaped $body)`",",
    "  `"paths`": $(ConvertTo-JsonArray $o.paths),",
    "  `"refs`": $(ConvertTo-JsonArray $o.refs),",
    "  `"option`": $(ConvertTo-JsonScalar $o.option),",
    "  `"selected`": $(ConvertTo-JsonScalar $o.selected),",
    "  `"owner`": $(ConvertTo-JsonScalar $o.owner),",
    "  `"participants`": $(ConvertTo-JsonArray $o.participants)",
    '}'
  ) -join "`n"
  # WriteAllText: UTF-8 without BOM (a BOM would break the sh reader).
  [IO.File]::WriteAllText($temp, $json)
  Move-Item -LiteralPath $temp -Destination $target
  Say "created collaboration event: .context_ledger/memory/collaboration/events/$id.json"
  if ($EventType -eq 'note') {
    Say 'publish it in a chore(ledger): commit so your peers see it -- a note carries no obligation'
  } else {
    Say 'publish it in a separate chore(ledger): commit before changing the claimed product scope'
  }
}

function Is-Released { param([IO.FileInfo]$ClaimFile, [IO.FileInfo[]]$Files)
  $cid = Get-Field $ClaimFile 'id'
  $cses = Get-Field $ClaimFile 'session'; $ciss = Get-Field $ClaimFile 'issue'
  $cpaths = Get-Field $ClaimFile 'paths'
  foreach ($file in $Files) {
    if ((Get-Field $file 'type') -notin @('release','handoff')) { continue }
    # (a) explicit event-ID linkage
    if (",$(Get-Field $file 'refs')," -like "*,$cid,*") { return $true }
    # (b) weak-agent fallback: SHA-only release/handoff that shares this
    #     claim's session+issue and overlaps its paths still closes it.
    if ((Get-Field $file 'session') -eq $cses -and (Get-Field $file 'issue') -eq $ciss -and
        (Overlap $cpaths (Get-Field $file 'paths'))) { return $true }
  }
  return $false
}
function Overlap { param([string]$Left, [string]$Right)
  $l = $Left.Split(','); $r = $Right.Split(',')
  foreach ($a in $l) { foreach ($b in $r) { if ($a -ne 'none' -and $a -eq $b) { return $true } } }
  return $false
}
function Status { param([string[]]$StatusArgs)
  $o = Parse-Options $StatusArgs
  $files = @(Get-ChildItem -LiteralPath $eventDir -File -ErrorAction SilentlyContinue |
    Where-Object { $_ -and ($_.Extension -eq '.md' -or $_.Extension -eq '.json') })
  if ($files.Count -eq 0) { Say 'no collaboration events yet'; return }
  $files = @($files | Where-Object {
    ($o.session -eq '' -or (Get-Field $_ 'session') -eq $o.session) -and
    ($o.issue -eq '' -or (Get-Field $_ 'issue') -eq $o.issue)
  })
  Say "Collaboration events$(if ($o.session) { " for session $($o.session)" })$(if ($o.issue) { " / issue $($o.issue)" }):"
  foreach ($file in $files) {
    Say "- $(Get-Field $file 'type') $(Get-Field $file 'id') -- agent=$(Get-Field $file 'agent') paths=$(Get-Field $file 'paths') refs=$(Get-Field $file 'refs')"
  }
  Say ''; Say 'Active claims and possible overlaps:'
  $claims = @($files | Where-Object { (Get-Field $_ 'type') -eq 'claim' -and -not (Is-Released $_ $files) })
  for ($a = 0; $a -lt $claims.Count; $a++) {
    $left = $claims[$a]
    Say "- $(Get-Field $left 'id') -- agent=$(Get-Field $left 'agent') paths=$(Get-Field $left 'paths')"
    for ($b = $a + 1; $b -lt $claims.Count; $b++) {
      $right = $claims[$b]
      if ((Get-Field $left 'session') -eq (Get-Field $right 'session') -and (Get-Field $left 'issue') -eq (Get-Field $right 'issue') -and (Overlap (Get-Field $left 'paths') (Get-Field $right 'paths'))) {
        Say "  POSSIBLE OVERLAP with $(Get-Field $right 'id') -- talk it through (a note), compare the two changes, and agree who takes it"
      }
    }
  }
  Say ''; Say 'Recent chatter (notes) -- read these first to catch up, like a team channel:'
  $notes = @($files | Where-Object { (Get-Field $_ 'type') -eq 'note' })
  if ($notes.Count -eq 0) {
    Say "  (none yet -- a quick 'note' is how you say what you're on or flag something to a peer)"
  } else {
    foreach ($n in $notes) {
      $to = Get-Field $n 'participants'; if ($to -eq 'none') { $to = '' }
      $re = Get-Field $n 'refs'; if ($re -eq 'none') { $re = '' }
      $arrow = if ($to) { " ->$to" } else { '' }
      $reSuffix = if ($re) { "  (re: $re)" } else { '' }
      Say "- $(Get-Field $n 'agent')${arrow}: $(Get-FirstBodyLine $n)$reSuffix"
    }
  }
  Say ''
  Say 'A genuine conflict (same paths, incompatible changes) escalates to proposal -> assessment -> agreement.'
  Say "Everything else is a note plus your own claim/release -- you're on the same team, not bidding against each other."
}

if ($Command -in @('', '-h', '--help', 'help')) { Usage }
switch ($Command) {
  'emit' {
    $emitArgs = @()
    if ($null -ne $Extra) { $emitArgs = @($Extra) }
    Emit $Type $emitArgs
  }
  'status' {
    $statusArgs = @()
    if ($Type) { $statusArgs += $Type }
    if ($null -ne $Extra) { $statusArgs += $Extra }
    Status $statusArgs
  }
  'check' {
    $checkArgs = @()
    if ($Type) { $checkArgs += $Type }
    if ($null -ne $Extra) { $checkArgs += $Extra }
    # A child .ps1's `exit N` does not reliably set $LASTEXITCODE on every
    # host (reading it unset trips StrictMode), so pre-seed it and fall
    # back to the child's success status.
    $global:LASTEXITCODE = $null
    & (Join-Path $scriptDir 'ledger-collab-check.ps1') @checkArgs
    if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }
    if ($?) { exit 0 } else { exit 1 }
  }
  default { Die "unknown command '$Command' (try: ledger-collab.ps1 help)" }
}
