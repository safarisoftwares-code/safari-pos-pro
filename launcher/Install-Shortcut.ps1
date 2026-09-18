# ============================================================
#  Safari POS Pro - Shortcut Installer
#
#  Creates a desktop shortcut that launches the app with NO
#  black console flash. Runs PowerShell directly (hidden) on
#  the launcher script.
#
#  Usage: Right-click this file -> Run with PowerShell
#         OR:  powershell -ExecutionPolicy Bypass -File "Install-Shortcut.ps1"
# ============================================================

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $here "Safari-POS-Pro-Launcher.ps1"
$icon = Join-Path $here "Safari-POS-Pro.ico"

if (-not (Test-Path $launcher)) {
    Write-Host "ERROR: Launcher not found at $launcher" -ForegroundColor Red
    Write-Host "Place this installer in the same folder as Safari-POS-Pro-Launcher.ps1"
    Read-Host "Press Enter to exit"
    exit 1
}

# Target command: powershell.exe with full args
$powershellPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$args = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""

# Shortcut path
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Safari POS Pro.lnk"

# Create shortcut via WScript.Shell COM
$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershellPath
$shortcut.Arguments = $args
$shortcut.WorkingDirectory = $here
$shortcut.WindowStyle = 7   # 7 = Minimized
$shortcut.Description = "Safari POS Pro - Point of Sale System"

if (Test-Path $icon) {
    $shortcut.IconLocation = "$icon,0"
} else {
    Write-Host "Note: Icon not found at $icon, using default PowerShell icon" -ForegroundColor Yellow
}

$shortcut.Save()

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Shortcut created successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Location: $shortcutPath"
Write-Host ""
Write-Host "You can now double-click the shortcut to launch the app."
Write-Host "No console window will appear."
Write-Host ""

Read-Host "Press Enter to close"