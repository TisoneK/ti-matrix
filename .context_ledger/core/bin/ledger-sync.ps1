#!/usr/bin/env pwsh
# ledger-sync.ps1 -- Windows/PowerShell port of core/bin/ledger-sync.
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
# The POSIX sh script (core/bin/ledger-sync) is the reference implementation
# and runs on macOS/Linux. This port covers the commands a Windows agent hits
# inside a session; it is byte-compatible with the sh script's MANIFEST.sha256
# (same hashes, same forward-slash paths), so a core verified here verifies
# there and vice-versa. Never touches .context_ledger/memory/ except
# memory/core.lock and one deliberate exception: backfill/migrate group a
# legacy flat memory layout into the live memory/office/ directory (core
# 1.0.0) and seed a missing office skeleton from templates. Durable memory
# files are never altered.
#
# Requires PowerShell 5.1+ (Windows PowerShell or PowerShell 7 `pwsh`) and,
# for `rollback`, git on PATH.
#
# Commands (project mode -- run the launcher, no execution-policy setup:
#     .context_ledger/core/bin/ledger-sync.cmd <cmd>):
#   status               local core version + best reachable update source
#   verify               check every core file against core/MANIFEST.sha256
#   update [SOURCE]      replace core/ from SOURCE (package clone / unpacked
#                        archive). Same-MAJOR updates apply directly; a MAJOR
#                        bump needs -Major. Then migrate -BackfillOnly runs,
#                        which groups a legacy flat layout into memory/office/.
#   migrate [SOURCE]     ONE-COMMAND bring-current: update core to newest,
#                        backfill every missing zone/file, normalize, relock,
#                        verify. Idempotent. Leaves only "fill the facts".
#   rollback [VERSION]   restore core/ from this project's git history
#                        (default VERSION: the one in memory/core.lock)
#   lock                 record the current verified core version in
#                        memory/core.lock (update/verify call this for you)
#   rename               one-time 0.18 migration: git mv a legacy .context/
#                        project directory to .context_ledger/ and update
#                        the generated entry points. Requires a clean tree.
#
# Package-mode commands (manifest, bootstrap, harvest) are NOT ported --
# run them with the sh script on macOS/Linux.
#
# Exit codes: 0 ok | 1 failure | 2 usage | 3 verify mismatch

[CmdletBinding()]
param(
  [Parameter(Position = 0)]                     [string]   $Command = '',
  [Parameter(Position = 1, ValueFromRemainingArguments = $true)] [string[]] $Rest,
  [switch] $Major
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Say  { param([string]$m) Write-Output $m }
function Err  { param([string]$m) [Console]::Error.WriteLine("ledger-sync: $m") }
function Die  { param([string]$m) Err $m; exit 1 }

# --- locate ourselves -------------------------------------------------------
$SCRIPT_DIR = $PSScriptRoot
$CORE_DIR   = (Resolve-Path (Join-Path $SCRIPT_DIR '..')).Path
$PARENT_DIR = Split-Path -Parent $CORE_DIR

# Mode detection accepts both layouts: .context_ledger/ (1.0+) and the
# legacy .context/ (pre-1.0 projects mid-migration -- finish with `rename`).
$leaf = Split-Path -Leaf $PARENT_DIR
if ($leaf -eq '.context_ledger' -or $leaf -eq '.context') {
  $script:MODE        = 'project'
  $script:LEDGER_DIR = $PARENT_DIR
  $script:PROJECT_DIR = Split-Path -Parent $LEDGER_DIR
  $script:MEMORY_DIR  = Join-Path $LEDGER_DIR 'memory'
} else {
  $script:MODE        = 'package'   # running from a package clone
  $script:PACKAGE_DIR = $PARENT_DIR
}

# --- helpers ----------------------------------------------------------------
function Core-Version { # $dir -> version string
  param([string]$dir)
  $vf = Join-Path $dir 'VERSION'
  if (-not (Test-Path -LiteralPath $vf)) { return '0.0.0' }
  $line = (Get-Content -Encoding UTF8 -LiteralPath $vf -TotalCount 1)
  if ($null -eq $line) { return '0.0.0' }
  return ($line -replace '\s', '')
}

function Ver-Part { # $version $index(1..3) -> integer part
  param([string]$v, [int]$i)
  $parts = $v.Split('.')
  $p = if ($i -le $parts.Count) { $parts[$i - 1] } else { '' }
  $p = ($p -replace '[^0-9]', '')
  if ($p -eq '') { return 0 } else { return [int]$p }
}

function Ver-Cmp { # $a $b -> 'newer'|'same'|'older'  ($a relative to $b)
  param([string]$a, [string]$b)
  foreach ($i in 1, 2, 3) {
    $x = Ver-Part $a $i; $y = Ver-Part $b $i
    if ($x -gt $y) { return 'newer' }
    if ($x -lt $y) { return 'older' }
  }
  return 'same'
}

# a directory is a core source if it's a package clone (has core/) or an
# already-unpacked core (has VERSION + rules/). Returns the core dir, or $null.
function Source-Core-Dir {
  param([string]$path)
  if ((Test-Path -LiteralPath (Join-Path $path 'core/rules') -PathType Container) -and
      (Test-Path -LiteralPath (Join-Path $path 'core/VERSION') -PathType Leaf)) {
    return (Resolve-Path (Join-Path $path 'core')).Path
  }
  if ((Test-Path -LiteralPath (Join-Path $path 'rules') -PathType Container) -and
      (Test-Path -LiteralPath (Join-Path $path 'VERSION') -PathType Leaf)) {
    return (Resolve-Path $path).Path
  }
  return $null
}

function Find-Source { # $explicit -> core dir or $null
  param([string]$explicit)
  if ($explicit) {
    $d = Source-Core-Dir $explicit
    if (-not $d) { Die "not a package clone or core tree: $explicit" }
    return $d
  }
  if ($env:LEDGER_PKG) {
    $d = Source-Core-Dir $env:LEDGER_PKG
    if ($d) { return $d }
  }
  foreach ($rel in '../context-ledger', '../context', '../.context') {
    $cand = Join-Path $PROJECT_DIR $rel
    if (Test-Path -LiteralPath $cand) {
      $d = Source-Core-Dir $cand
      if ($d) { return $d }
    }
  }
  return $null
}

# Parse a MANIFEST.sha256 line into @{ Hash; Path } or $null.
# Format (sha256sum / shasum -a 256): "<64 hex>  <relpath>" -- one separator
# space plus a mode char (space for text, '*' for binary).
function Parse-Manifest-Line {
  param([string]$line)
  if ($line -match '^([0-9a-fA-F]{64}) [ *](.+)$') {
    return @{ Hash = $matches[1].ToLower(); Path = $matches[2] }
  }
  return $null
}

# Hash the CR-stripped content of $path (lowercase hex). One manifest stays
# byte-compatible across LF checkouts (macOS/Linux) and CRLF copies (files
# copied outside git on Windows, where .gitattributes does not reach);
# LF-only files hash identically, so manifest values never change.
function Get-LfHash {
  param([string]$Path)
  $ms = New-Object IO.MemoryStream
  foreach ($b in [IO.File]::ReadAllBytes($Path)) { if ($b -ne 13) { $ms.WriteByte($b) } }
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try { ([BitConverter]::ToString($sha.ComputeHash($ms.ToArray())) -replace '-', '').ToLower() }
  finally { $sha.Dispose(); $ms.Dispose() }
}

# Rewrite $path in place to LF (CR bytes removed).
function Convert-ToLf {
  param([string]$Path)
  $ms = New-Object IO.MemoryStream
  foreach ($b in [IO.File]::ReadAllBytes($Path)) { if ($b -ne 13) { $ms.WriteByte($b) } }
  [IO.File]::WriteAllBytes($Path, $ms.ToArray())
  $ms.Dispose()
}

# $dir -> $true clean, $false mismatch. Prints up to 20 problems to stderr.
function Verify-Tree {
  param([string]$dir)
  $manifest = Join-Path $dir 'MANIFEST.sha256'
  if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
    Err "no MANIFEST.sha256 in $dir"; return $false
  }
  $problems = @()
  foreach ($line in Get-Content -Encoding UTF8 -LiteralPath $manifest) {
    $entry = Parse-Manifest-Line $line
    if (-not $entry) { continue }
    $file = Join-Path $dir ($entry.Path.Replace('/', [IO.Path]::DirectorySeparatorChar))
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
      $problems += "$($entry.Path): FAILED open or read"; continue
    }
    $got = Get-LfHash $file
    if ($got -ne $entry.Hash) { $problems += "$($entry.Path): FAILED" }
  }
  if ($problems.Count -eq 0) { return $true }
  $problems | Select-Object -First 20 | ForEach-Object { [Console]::Error.WriteLine($_) }
  return $false
}

function Write-Lock { # $version
  param([string]$version)
  if ($MODE -ne 'project') { return }
  if (-not (Test-Path -LiteralPath $MEMORY_DIR)) {
    New-Item -ItemType Directory -Path $MEMORY_DIR -Force | Out-Null
  }
  $today = Get-Date -Format 'yyyy-MM-dd'
  # The em-dash matches the sh port byte-for-byte. Two traps here: PS 5.1
  # writes ANSI via Set-Content, AND it *parses* BOM-less .ps1 source as
  # cp1252 -- so the em-dash must come from a code point, never a literal in
  # this file (ps1 string literals stay pure ASCII). WriteAllText keeps UTF-8
  # without a BOM.
  $em = [string][char]0x2014
  $body = @(
    "# written by ledger-sync $em the last-known-good core version."
    '# Do not edit by hand. If core fails verify, `ledger-sync rollback`'
    '# restores the version recorded here from git history.'
    "version=$version"
    "verified=$today"
  ) -join "`n"
  [IO.File]::WriteAllText((Join-Path $MEMORY_DIR 'core.lock'), $body + "`n", (New-Object System.Text.UTF8Encoding $false))
}

function Lock-Version {
  $lf = Join-Path $MEMORY_DIR 'core.lock'
  if (-not (Test-Path -LiteralPath $lf)) { return '' }
  foreach ($line in Get-Content -Encoding UTF8 -LiteralPath $lf) {
    if ($line -match '^version=(.*)$') { return $matches[1] }
  }
  return ''
}

function Need-Project {
  param([string]$name)
  if ($MODE -ne 'project') {
    Die "'$name' runs inside a project (.context_ledger/core/bin/ledger-sync.ps1), not the package clone"
  }
}

# --- commands ----------------------------------------------------------------
function Cmd-Status {
  param([string]$srcArg)
  Need-Project 'status'
  $localV = Core-Version $CORE_DIR
  Say "core:   $localV  ($LEDGER_DIR/core)"
  $locked = Lock-Version
  if ($locked -eq '') { $locked = '(no core.lock yet)' }
  Say "locked: $locked"
  $src = Find-Source $srcArg
  if ($src) {
    $srcV = Core-Version $src
    switch (Ver-Cmp $srcV $localV) {
      'newer' {
        if ((Ver-Part $srcV 1) -eq (Ver-Part $localV 1)) {
          Say "source: $srcV  ($src) -- UPDATE AVAILABLE (same MAJOR: safe to 'update')"
        } else {
          Say "source: $srcV  ($src) -- MAJOR update: read its CHANGELOG.md, then 'update -Major' with the user's go-ahead"
        }
      }
      'same'  { Say "source: $srcV  ($src) -- up to date" }
      'older' { Say "source: $srcV  ($src) -- source is OLDER than local; nothing to do" }
    }
  } else {
    Say "source: none reachable (no sibling package clone; set LEDGER_PKG or pass a path) -- skipping, this is fine"
  }
}

# Port parse check (core 1.0.1): hashing catches a corrupted file, not a port
# that shipped unable to run. This edition ParseFiles every ps1 port natively
# and, when a POSIX sh is on PATH (Git Bash on Windows), `sh -n`s every sh
# port; the sh edition is the mirror image (its ps1 half is skipped where no
# PowerShell engine exists). The encoding guard (core 2.0.4) is engine-free:
# ParseFile here runs under *this* engine, so on pwsh 7 it would accept a
# non-ASCII port that Windows PowerShell 5.1 cannot decode (it reads a
# BOM-less script with the system codepage; an em-dash becomes U+201D, a
# string terminator). Ports stay pure ASCII. Returns $true clean, $false bad.
function Parse-Ports { param([string]$dir)
  $bad = $false
  foreach ($f in (Get-ChildItem -LiteralPath (Join-Path $dir 'bin') -Filter 'ledger-*.ps1' -File)) {
    $bytes = [IO.File]::ReadAllBytes($f.FullName)
    if (@($bytes | Where-Object { $_ -gt 126 -or ($_ -lt 32 -and $_ -ne 9 -and $_ -ne 10 -and $_ -ne 13) }).Count -gt 0) {
      Err ("ps1 encoding: {0} holds non-ASCII bytes -- Windows PowerShell 5.1 will mis-decode it; keep the port pure ASCII" -f $f.Name)
      $bad = $true
    }
    $tok = $null; $errs = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tok, [ref]$errs)
    if ($errs -and $errs.Count -gt 0) {
      foreach ($e in $errs) { Err ("{0}: {1}" -f $f.Name, $e.Message) }
      $bad = $true
    }
  }
  if (Get-Command sh -ErrorAction SilentlyContinue) {
    foreach ($f in (Get-ChildItem -LiteralPath (Join-Path $dir 'bin') -File)) {
      if ($f.Name -like '*.ps1' -or $f.Name -like '*.cmd') { continue }
      $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
      try { $out = @(& sh -n $f.FullName 2>&1); $code = $LASTEXITCODE }
      finally { $ErrorActionPreference = $eap }
      if ($code -ne 0) { Err ("sh parse: {0}: {1}" -f $f.Name, ($out -join ' ')); $bad = $true }
    }
  }
  return (-not $bad)
}

function Cmd-Verify {
  param([string]$target)
  if (-not $target) { $target = $CORE_DIR }
  if (-not (Verify-Tree $target)) {
    Err 'CORE INTEGRITY FAILURE -- core/ does not match its manifest.'
    Err 'Do not ''fix'' core in place. Run: ledger-sync rollback'
    Err 'Then log the incident in memory/office/flaws/log.md and continue.'
    exit 3
  }
  if (-not (Parse-Ports $target)) {
    Err 'PORT PARSE FAILURE -- a script in core/bin cannot be parsed.'
    Err 'If this core just arrived from a release: ledger-sync rollback <previous-version>, and report it upstream.'
    Err 'Do not ''fix'' core in place.'
    exit 3
  }
  Say "core OK: every file matches MANIFEST.sha256 and every port parses ($(Core-Version $target))"
  if ($target -eq $CORE_DIR) { Write-Lock (Core-Version $target) }
  exit 0
}

# One-time layout migration (core 1.0.0): group a legacy flat memory layout
# into the live office directory. The live office is memory/office/ -- roster,
# session registry and notes, tasks, plans, flaw and inefficiency logs,
# reviews -- everything session-produced, frozen verbatim when the office
# closes. Durable files (workflows/, collaboration/, system/, user/,
# overrides/, core.lock, secrets/) stay at the memory/ root and never move.
# Idempotent: no office dir + flat dirs present = migrate; otherwise no-op.
# Runs at the top of Backfill-Project, so every update and migrate performs
# it -- the old architecture becomes an office during sync.
function Migrate-OfficeLayout {
  if (Test-Path -LiteralPath (Join-Path $MEMORY_DIR 'office')) { return }
  if (-not (Test-Path -LiteralPath (Join-Path $MEMORY_DIR 'agents'))) { return }  # not a flat-layout install
  Say 'office migration: grouping the flat memory layout into memory/office/'
  New-Item -ItemType Directory -Path (Join-Path $MEMORY_DIR 'office') -Force | Out-Null
  foreach ($d in @('agents', 'sessions', 'tasks', 'plans', 'flaws', 'inefficiencies', 'reviews')) {
    $src = Join-Path $MEMORY_DIR $d
    if (Test-Path -LiteralPath $src) { Move-Item -LiteralPath $src -Destination (Join-Path $MEMORY_DIR "office/$d") }
  }
  $grp = Join-Path $MEMORY_DIR 'office/agents/GROUP'
  if (Test-Path -LiteralPath $grp) { Remove-Item -LiteralPath $grp -Force }  # counter retired: office numbers are derived at close
  $hc = Join-Path $MEMORY_DIR 'workflows/history.conf'
  if ((Test-Path -LiteralPath $hc) -and (Select-String -LiteralPath $hc -Pattern '^group_size=' -Quiet)) {
    $lines = Get-Content -Encoding UTF8 -LiteralPath $hc | ForEach-Object { $_ -replace '^group_size=', 'office_size=' }
    [IO.File]::WriteAllText($hc, ($lines -join "`n") + "`n", (New-Object System.Text.UTF8Encoding $false))
  }
  Say 'office migration: done -- the old layout is now the live office.'
  Say 'Commit as: chore(ledger): group memory into the live office (core 1.0.0)'
}

# Install every current-version scaffolding file the project may be missing.
# Idempotent; never clobbers existing files. Reads the CURRENT core/templates,
# so it is the single definition of what a fully-migrated project contains.
# The office layout migration runs first, so a legacy install is regrouped
# before this checks what is missing.
function Backfill-Project {
  Migrate-OfficeLayout
  $readme = Join-Path $CORE_DIR 'templates/ledger-README.md'
  if (Test-Path -LiteralPath $readme) { Copy-Item -LiteralPath $readme -Destination (Join-Path $LEDGER_DIR 'README.md') -Force -ErrorAction SilentlyContinue }
  $attrs = Join-Path $LEDGER_DIR '.gitattributes'
  if (-not (Test-Path -LiteralPath $attrs)) { Copy-Item -LiteralPath (Join-Path $CORE_DIR 'templates/.gitattributes') -Destination $attrs -ErrorAction SilentlyContinue }
  $claude = Join-Path $PROJECT_DIR 'CLAUDE.md'
  if (-not (Test-Path -LiteralPath $claude)) { Copy-Item -LiteralPath (Join-Path $CORE_DIR 'templates/CLAUDE.md') -Destination $claude -ErrorAction SilentlyContinue }
  $hist = Join-Path $LEDGER_DIR 'history'
  if (-not (Test-Path -LiteralPath $hist)) { Copy-Item -LiteralPath (Join-Path $CORE_DIR 'templates/history') -Destination $hist -Recurse -ErrorAction SilentlyContinue }
  $arch = Join-Path $LEDGER_DIR 'archive'
  if (-not (Test-Path -LiteralPath $arch)) { Copy-Item -LiteralPath (Join-Path $CORE_DIR 'templates/archive') -Destination $arch -Recurse -ErrorAction SilentlyContinue }
  $wf = Join-Path $MEMORY_DIR 'workflows'
  New-Item -ItemType Directory -Path $wf -Force -ErrorAction SilentlyContinue | Out-Null
  $hc = Join-Path $wf 'history.conf'
  if (-not (Test-Path -LiteralPath $hc)) { Copy-Item -LiteralPath (Join-Path $CORE_DIR 'templates/memory/workflows/history.conf') -Destination $hc -ErrorAction SilentlyContinue }
  # the live office -- seeded from templates when absent, topped up when
  # partial (a migrated install may never have created every directory)
  $office = Join-Path $MEMORY_DIR 'office'
  $officeTpl = Join-Path $CORE_DIR 'templates/memory/office'
  if (Test-Path -LiteralPath $officeTpl) {
    if (-not (Test-Path -LiteralPath $office)) {
      New-Item -ItemType Directory -Path $office -Force | Out-Null
      Copy-Item -LiteralPath $officeTpl -Destination $office -Recurse -ErrorAction SilentlyContinue
    } else {
      Get-ChildItem -LiteralPath $officeTpl -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($officeTpl.Length).TrimStart('\', '/')
        $dest = Join-Path $office $rel
        if (-not (Test-Path -LiteralPath $dest)) {
          New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force -ErrorAction SilentlyContinue | Out-Null
          Copy-Item -LiteralPath $_.FullName -Destination $dest -ErrorAction SilentlyContinue
        }
      }
    }
  }
}

# Replace .context_ledger/core with the source tree, LF-normalized and re-verified.
function Swap-Core {
  param([string]$src, [string]$srcV)
  if (-not (Verify-Tree $src)) { Die 'update source fails its own manifest -- refusing to install a corrupt core' }
  $stage = Join-Path $LEDGER_DIR 'core.new'
  if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
  Copy-Item -LiteralPath $src -Destination $stage -Recurse -Force
  Get-ChildItem -LiteralPath $stage -Recurse -File | ForEach-Object { Convert-ToLf $_.FullName }
  if (-not (Verify-Tree $stage)) { Remove-Item -LiteralPath $stage -Recurse -Force; Die 'staged copy fails verify -- aborting, core untouched' }
  try { Remove-Item -LiteralPath $CORE_DIR -Recurse -Force; Move-Item -LiteralPath $stage -Destination $CORE_DIR }
  catch { Die 'swap failed -- restore .context_ledger/core from git (git checkout -- .context_ledger/core)' }
  Write-Lock $srcV
}

function Cmd-Update {
  param([string[]]$uArgs)
  Need-Project 'update'
  Backfill-Project
  $srcArg = ''
  foreach ($a in $uArgs) { if ($a -eq '--major') { $script:Major = $true } else { $srcArg = $a } }
  $src = Find-Source $srcArg
  if (-not $src) { Die 'no update source found (sibling clone, LEDGER_PKG, or a path argument)' }
  $srcV = Core-Version $src; $localV = Core-Version $CORE_DIR
  switch (Ver-Cmp $srcV $localV) {
    'same'  { Say "already at $localV -- nothing to do"; exit 0 }
    'older' { Say "source ($srcV) is older than local ($localV) -- refusing to downgrade"; exit 0 }
  }
  if (((Ver-Part $srcV 1) -ne (Ver-Part $localV 1)) -and (-not $Major)) {
    Die "MAJOR version bump ($localV -> $srcV): read CHANGELOG.md migration notes, get the user's go-ahead, re-run with -Major"
  }
  Swap-Core $src $srcV
  Say "core updated: $localV -> $srcV"
  # hand off to the just-installed script so backfill knows every new file
  & (Join-Path $CORE_DIR 'bin/ledger-sync.ps1') migrate --backfill-only
  exit $LASTEXITCODE
}

# migrate -- one-command bring-current: update core to the newest reachable
# version, then backfill every missing file, LF-normalize, relock, verify.
# Idempotent. Leaves only "fill the project facts".
function Cmd-Migrate {
  param([string[]]$mArgs)
  Need-Project 'migrate'
  $backfillOnly = $false; $srcArg = ''
  foreach ($a in $mArgs) {
    if ($a -eq '--backfill-only') { $backfillOnly = $true }
    elseif ($a -eq '--major') { $script:Major = $true }
    else { $srcArg = $a }
  }
  if (-not $backfillOnly) {
    $src = Find-Source $srcArg
    if ($src) {
      $srcV = Core-Version $src; $localV = Core-Version $CORE_DIR
      if ((Ver-Cmp $srcV $localV) -eq 'newer') {
        if (((Ver-Part $srcV 1) -ne (Ver-Part $localV 1)) -and (-not $Major)) {
          Die "MAJOR bump ($localV -> $srcV): read CHANGELOG.md, then re-run with -Major"
        }
        Say "updating core: $localV -> $srcV"
        Swap-Core $src $srcV
        & (Join-Path $CORE_DIR 'bin/ledger-sync.ps1') migrate --backfill-only
        exit $LASTEXITCODE
      }
    }
  }
  Backfill-Project
  Get-ChildItem -LiteralPath $CORE_DIR -Recurse -File | ForEach-Object { Convert-ToLf $_.FullName }
  Write-Lock (Core-Version $CORE_DIR)
  $v = Core-Version $CORE_DIR
  if (Verify-Tree $CORE_DIR) { $vs = 'core verified' } else { $vs = 'core FAILED verify -- run: ledger-sync rollback' }
  Say "migration complete -- core $v; all zones/files present; $vs."
  Say ''
  Say 'One step left -- fill the project facts (facts from memory, no secrets):'
  Say '  .context_ledger/kickoff.md          -- Project Facts (remote URL, default branch, name)'
  Say '  AGENTS.md                    -- <PROJECT_NAME>'
  Say '  memory/workflows/active.md   -- protocol by agent type, BOTH edition paths'
  Say "then commit + push: chore(ledger): migrate to core $v"
  if ((Split-Path -Leaf $LEDGER_DIR) -eq '.context') {
    Say ''
    Say 'This project still uses the legacy .context/ directory -- finish the 0.18'
    Say 'rename with: ledger-sync rename'
  }
  exit 0
}

# rename -- one-time 0.18 migration: git mv a legacy .context/ project
# directory to .context_ledger/ and sweep the generated entry points.
function Cmd-Rename {
  Need-Project 'rename'
  if ((Split-Path -Leaf $LEDGER_DIR) -ne '.context') { Die 'this project already uses .context_ledger/ -- nothing to rename' }
  & git -C $PROJECT_DIR rev-parse --is-inside-work-tree *> $null
  if ($LASTEXITCODE -ne 0) { Die 'project is not a git repo -- cannot rename' }
  if (& git -C $PROJECT_DIR status --porcelain) { Die 'working tree not clean -- commit or stash first, then re-run rename' }
  & git -C $PROJECT_DIR mv .context .context_ledger
  if ($LASTEXITCODE -ne 0) { Die 'git mv .context .context_ledger failed -- rename by hand, then re-run this command' }
  # this script itself moved with the tree -- re-point the computed paths
  $script:LEDGER_DIR  = Join-Path $PROJECT_DIR '.context_ledger'
  $script:CORE_DIR    = Join-Path $LEDGER_DIR 'core'
  $script:MEMORY_DIR  = Join-Path $LEDGER_DIR 'memory'
  # the generated entry points hardcode the directory name; sweep them
  foreach ($f in @('.context_ledger/README.md', '.context_ledger/kickoff.md', '.context_ledger/.gitattributes', 'AGENTS.md', 'CLAUDE.md')) {
    $p = Join-Path $PROJECT_DIR $f
    if (Test-Path -LiteralPath $p -PathType Leaf) {
      $t = Get-Content -Encoding UTF8 -LiteralPath $p -Raw
      # WriteAllText UTF-8 without a BOM - Set-Content writes ANSI on
      # Windows PowerShell 5.1 and would mangle every em-dash in these files.
      [IO.File]::WriteAllText($p, ($t -replace '\.context/', '.context_ledger/' -replace '\.context\b', '.context_ledger'), (New-Object System.Text.UTF8Encoding $false))
    }
  }
  Get-ChildItem -LiteralPath $CORE_DIR -Recurse -File | ForEach-Object { Convert-ToLf $_.FullName }
  Write-Lock (Core-Version $CORE_DIR)
  if (Verify-Tree $CORE_DIR) { $vs = 'core verified' } else { $vs = 'core FAILED verify -- run: ledger-sync rollback' }
  Say "renamed .context/ -> .context_ledger/ ($vs)"
  Say 'One step left -- sweep stale ''.context/'' instruction references in your memory/ files'
  Say '(historical log entries stay as written -- append-only), then commit + push:'
  Say '  chore(ledger): rename .context/ to .context_ledger/ (core 0.18)'
  exit 0
}

function Cmd-Rollback {
  param([string]$want)
  Need-Project 'rollback'
  if (-not $want) { $want = Lock-Version }
  if (-not $want) { Die 'no version given and no memory/core.lock -- pass a version: ledger-sync rollback 0.2.0' }
  & git -C $PROJECT_DIR rev-parse --is-inside-work-tree *> $null
  if ($LASTEXITCODE -ne 0) { Die 'project is not a git repo -- cannot roll back' }
  $found = ''
  $shas = & git -C $PROJECT_DIR log --format=%H -- .context_ledger/core/VERSION
  foreach ($sha in $shas) {
    $v = (& git -C $PROJECT_DIR show "${sha}:.context_ledger/core/VERSION" 2>$null | Select-Object -First 1)
    if ($null -ne $v) { $v = ($v -replace '\s', '') }
    if ($v -eq $want) { $found = $sha; break }
  }
  if (-not $found) { Die "no commit in history has core VERSION $want" }
  Remove-Item -LiteralPath (Join-Path $PROJECT_DIR '.context_ledger/core') -Recurse -Force
  & git -C $PROJECT_DIR checkout $found -- .context_ledger/core
  if ($LASTEXITCODE -ne 0) { Die 'git checkout failed -- run: git checkout HEAD -- .context_ledger/core' }
  # a CRLF checkout (core.autocrlf=true) restores hashes that do not match
  # the manifest -- rewrite to LF so the rolled-back core verifies.
  Get-ChildItem -LiteralPath (Join-Path $PROJECT_DIR '.context_ledger/core') -Recurse -File | ForEach-Object { Convert-ToLf $_.FullName }
  Write-Lock $want
  Say "core rolled back to $want (from commit $($found.Substring(0, [Math]::Min(8, $found.Length))))"
  Say 'log the incident in memory/office/flaws/log.md, then commit as:'
  Say "  chore(ledger): roll back core to $want"
  exit 0
}

# --- dispatch ----------------------------------------------------------------
$argsRest = if ($null -eq $Rest) { @() } else { $Rest }

switch ($Command) {
  'status'   { Cmd-Status ($argsRest | Select-Object -First 1); exit 0 }
  'verify'   { Cmd-Verify ($argsRest | Select-Object -First 1) }
  'update'   { Cmd-Update $argsRest }
  'migrate'  { Cmd-Migrate $argsRest }
  'rollback' { Cmd-Rollback ($argsRest | Select-Object -First 1) }
  'rename'   { Cmd-Rename }
  'lock' {
    Need-Project 'lock'
    Write-Lock (Core-Version $CORE_DIR)
    Say "locked $(Core-Version $CORE_DIR)"
    exit 0
  }
  { $_ -in 'manifest', 'bootstrap', 'harvest' } {
    Die "'$Command' is not ported to PowerShell -- run the sh script on macOS/Linux: sh core/bin/ledger-sync $Command"
  }
  { $_ -in '', $null, '-h', '--help', 'help' } {
    # print the command-doc comment (lines 13..31) as help, stripping '# '
    $self = Get-Content -Encoding UTF8 -LiteralPath $PSCommandPath
    $self[12..33] | ForEach-Object { Say ($_ -replace '^# ?', '') }
    exit 2
  }
  default { Die "unknown command: $Command (try: ledger-sync.ps1 help)" }
}
