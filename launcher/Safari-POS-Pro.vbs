' ============================================================
'  Safari POS Pro - Main Launcher v4
'  Uses dedicated Edge --user-data-dir so we can track the
'  app process and kill the server when the user closes it.
' ============================================================

Option Explicit

Dim WshShell, FSO, rootDir, launcherDir, splashPath, startBat, killBat, edgePath
Dim edgeProfile, edgeCmd, cmd, exitCode, i
Dim objWMIService, colProcesses, proc, foundEdge, waited

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

launcherDir = FSO.GetParentFolderName(WScript.ScriptFullName)
rootDir = FSO.GetParentFolderName(launcherDir)
splashPath = launcherDir & "\splash.html"
startBat = launcherDir & "\start_server.bat"
killBat = launcherDir & "\launcher_helpers.bat"
edgeProfile = rootDir & "\.edge-profile"

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

' ---------- Step 3: Launch Edge with dedicated profile ----------
edgeCmd = """" & edgePath & """ --app=""file:///" & Replace(splashPath, "\", "/") & """ " & _
          "--user-data-dir=""" & edgeProfile & """ " & _
          "--start-maximized " & _
          "--no-first-run --no-default-browser-check"

WshShell.Run edgeCmd, 1, False

' ---------- Step 4: Wait for Edge process to appear ----------
Set objWMIService = GetObject("winmgmts:\\.\root\cimv2")

foundEdge = False
waited = 0
Do While Not foundEdge And waited < 30
    WScript.Sleep 1000
    waited = waited + 1
    Set colProcesses = objWMIService.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'msedge.exe'")
    For Each proc In colProcesses
        If InStr(proc.CommandLine, edgeProfile) > 0 Then
            foundEdge = True
            Exit For
        End If
    Next
Loop

If Not foundEdge Then
    WshShell.Run "cmd /c """ & killBat & """ kill", 0, True
    WScript.Quit 1
End If

' ---------- Step 5: Wait for Edge process to exit ----------
Do While True
    WScript.Sleep 2000
    foundEdge = False
    Set colProcesses = objWMIService.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'msedge.exe'")
    For Each proc In colProcesses
        If InStr(proc.CommandLine, edgeProfile) > 0 Then
            foundEdge = True
            Exit For
        End If
    Next
    If Not foundEdge Then Exit Do
Loop

' ---------- Step 6: Kill server ----------
WshShell.Run "cmd /c """ & killBat & """ kill", 0, True

WScript.Quit 0
