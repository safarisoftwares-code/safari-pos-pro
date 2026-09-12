' ============================================================
'  Safari POS Pro - Main Launcher v2
'  Starts server silently, opens splash in Edge app-mode,
'  waits for the Edge window to close, then kills server.
' ============================================================

Option Explicit

Dim WshShell, FSO, rootDir, launcherDir, splashPath, startBat, killBat, edgePath, cmd
Dim edgeCmd, exitCode, i, found
Dim WINDOW_TITLE

WINDOW_TITLE = "Safari POS Pro - Loading..."

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

launcherDir = FSO.GetParentFolderName(WScript.ScriptFullName)
rootDir = FSO.GetParentFolderName(launcherDir)
splashPath = launcherDir & "\splash.html"
startBat = launcherDir & "\start_server.bat"
killBat = launcherDir & "\launcher_helpers.bat"

WshShell.CurrentDirectory = rootDir

' ---------- Step 1: Is server already running? ----------
cmd = "cmd /c """ & killBat & """ is_running"
exitCode = WshShell.Run(cmd, 0, True)

If exitCode <> 0 Then
    WshShell.Run "cmd /c """ & startBat & """", 0, True
    WScript.Sleep 1500
End If

' ---------- Step 2: Find Edge ----------
edgePath = ""
Dim candidates
candidates = Array( _
    WshShell.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Microsoft\Edge\Application\msedge.exe", _
    WshShell.ExpandEnvironmentStrings("%ProgramFiles%") & "\Microsoft\Edge\Application\msedge.exe", _
    WshShell.ExpandEnvironmentStrings("%LocalAppData%") & "\Microsoft\Edge\Application\msedge.exe" _
)
For i = 0 To UBound(candidates)
    If FSO.FileExists(candidates(i)) Then
        edgePath = candidates(i)
        Exit For
    End If
Next

If edgePath = "" Then
    MsgBox "Microsoft Edge was not found." & vbCrLf & _
           "Safari POS Pro requires Microsoft Edge (included with Windows 10/11).", _
           vbCritical, "Safari POS Pro"
    WScript.Quit 1
End If

' ---------- Step 3: Open splash in Edge app-mode ----------
' Use --start-maximized so it takes the screen
edgeCmd = """" & edgePath & """ --app=""file:///" & Replace(splashPath, "\", "/") & """ " & _
          "--start-maximized " & _
          "--disable-features=msEdgeWelcomePage,msEdgeSidebar,msEdgeShoppingAssistant " & _
          "--no-first-run --no-default-browser-check"

' Launch Edge (do NOT wait ? Edge detaches)
WshShell.Run edgeCmd, 1, False

' Give Edge a moment to create its window
WScript.Sleep 2500

' Force Edge window to foreground
On Error Resume Next
found = False
For i = 1 To 10
    If WshShell.AppActivate(WINDOW_TITLE) Then
        found = True
        Exit For
    End If
    WScript.Sleep 500
Next
On Error GoTo 0

' ---------- Step 4: Wait for Edge window to close ----------
' Poll every 2 seconds. AppActivate returns True if window exists.
Dim stillOpen, waited
stillOpen = True
waited = 0
Do While stillOpen
    WScript.Sleep 2000
    waited = waited + 2
    On Error Resume Next
    stillOpen = WshShell.AppActivate(WINDOW_TITLE)
    On Error GoTo 0
    ' Safety: if we somehow lose the window reference but Edge is running,
    ' keep checking up to 8 hours (28800s), then kill anyway
    If waited > 28800 Then
        stillOpen = False
    End If
Loop

' ---------- Step 5: Cleanup ----------
cmd = "cmd /c """ & killBat & """ kill"
WshShell.Run cmd, 0, True

WScript.Quit 0
