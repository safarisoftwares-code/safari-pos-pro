# ============================================================
#  Safari POS Pro - Launcher (v6)
#  - Socket-based port check (no HTTP hang)
#  - WaitForExit() for Edge monitoring (no WMI, no polling)
#  - Kills EXE when Edge closes
# ============================================================

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$exePath = Join-Path $here "SafariPOSPro.exe"
$edgeProfile = Join-Path $here ".edge-profile"
$logsDir = Join-Path $here "logs"
if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir -Force | Out-Null }
$logFile = Join-Path $logsDir "launcher.log"

function L($m) {
    try {
        $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m
        Add-Content -Path $logFile -Value $line -ErrorAction SilentlyContinue
    } catch {}
}

function Test-PortOpen($port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $result = $client.BeginConnect("127.0.0.1", $port, $null, $null)
        $success = $result.AsyncWaitHandle.WaitOne(500)
        $connected = ($success -and $client.Connected)
        $client.Close()
        return $connected
    } catch {
        return $false
    }
}

L "=== Launcher v6 started ==="
L "here=$here"

if (-not (Test-Path $exePath)) {
    L "ERROR: EXE not found"
    exit 1
}

Set-Location $here

# --- Step 1: Start EXE if port free ---
if (Test-PortOpen 8001) {
    L "Port 8001 already open - server running, skipping EXE start"
} else {
    L "Port 8001 free - launching EXE"
    try {
        $proc = Start-Process -FilePath $exePath -WindowStyle Hidden -PassThru -ErrorAction Stop
        L "EXE started, PID=$($proc.Id)"
    } catch {
        L "ERROR starting EXE: $($_.Exception.Message)"
        exit 1
    }

    $ok = $false
    for ($i = 1; $i -le 60; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-PortOpen 8001) {
            L "Port 8001 opened after $($i * 0.5)s"
            $ok = $true
            break
        }
    }
    if (-not $ok) {
        L "ERROR: port never opened - killing EXE"
        Stop-Process -Name SafariPOSPro -Force -ErrorAction SilentlyContinue
        exit 1
    }
}

# --- Step 2: Find Edge ---
$candidates = @()
if ($env:ProgramFiles) { $candidates += (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe") }
if (${env:ProgramFiles(x86)}) { $candidates += (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe") }
if ($env:LocalAppData) { $candidates += (Join-Path $env:LocalAppData "Microsoft\Edge\Application\msedge.exe") }

$edge = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) {
    L "ERROR: Edge not found"
    Stop-Process -Name SafariPOSPro -Force -ErrorAction SilentlyContinue
    exit 1
}
L "Edge: $edge"

# --- Step 3: Launch Edge ---
$url = "http://localhost:8001/"
L "URL=$url"

$edgeArgs = @(
    "--app=$url",
    "--disable-http-cache",
    "--user-data-dir=$edgeProfile",
    "--start-maximized",
    "--no-first-run",
    "--no-default-browser-check"
)

try {
    $ep = Start-Process -FilePath $edge -ArgumentList $edgeArgs -PassThru -ErrorAction Stop
    L "Edge launched, PID=$($ep.Id)"
} catch {
    L "ERROR starting Edge: $($_.Exception.Message)"
    Stop-Process -Name SafariPOSPro -Force -ErrorAction SilentlyContinue
    exit 1
}

# --- Step 4: Wait for Edge to exit using WaitForExit ---
# This is a BLOCKING call. When the user closes the Edge window,
# the parent msedge.exe process exits, and WaitForExit returns.
L "Waiting for Edge to close (WaitForExit)..."

try {
    $ep.WaitForExit()
    L "Edge closed (WaitForExit returned)"
} catch {
    L "WaitForExit error: $($_.Exception.Message)"
}

# Brief grace period for Edge to fully clean up child processes
Start-Sleep -Milliseconds 800

# --- Step 5: Graceful shutdown, then fallback force-kill ---
L "Requesting graceful shutdown via /__shutdown__"
try {
    Invoke-WebRequest -Uri "http://localhost:8001/__shutdown__" -Method POST -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop | Out-Null
    L "Shutdown request accepted"
} catch {
    L "Shutdown request failed: $($_.Exception.Message) - will force-kill"
}

# Wait up to 5 seconds for the EXE to exit gracefully
$exited = $false
for ($i = 1; $i -le 10; $i++) {
    Start-Sleep -Milliseconds 500
    if (-not (Get-Process -Name SafariPOSPro -ErrorAction SilentlyContinue)) {
        L "EXE exited gracefully after $($i * 0.5)s"
        $exited = $true
        break
    }
}

if (-not $exited) {
    L "EXE did not exit within 5s - force-killing"
    Stop-Process -Name SafariPOSPro -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    L "Force-kill issued"
}

L "EXE stopped - exiting"
L "=== Launcher finished ==="