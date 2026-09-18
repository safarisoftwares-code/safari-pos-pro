' ============================================================
'  Safari POS Pro - Launcher for Packaged EXE (v4)
'  Uses WinHttp for reliable health checks (no hang on refused)
' ============================================================

Option Explicit

Dim WshShell, FSO, here, exePath, edgePath, edgeProfile, splashPath
Dim edgeCmd, cmd, exitCode, i, candidates
Dim objWMIService, colProcesses, proc, foundEdge, waited
Dim logFile, logsDir

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

here = FSO.GetParentFolderName(WScript.ScriptFullName)
exePath = here & "\SafariPOSPro.exe"
edgeProfile = here & "\.edge-profile"
splashPath = here & "\launcher\splash.html"
If Not FSO.FileExists(splashPath) Then
    splashPath = here & "\splash.html"
End If

logsDir = here & "\logs"
If Not FSO.FolderExists(logsDir) Then
    On Error Resume Next
    FSO.CreateFolder(logsDir)
    On Error Goto 0
End If
logFile = logsDir & "\vbs_launcher.log"

Sub LogMsg(msg)
    On Error Resume Next
    Dim f
    Set f = FSO.OpenTextFile(logFile, 8, True)
    f.WriteLine "[" & Now & "] " & msg
    f.Close
    On Error Goto 0
End Sub

' ----------------------------------------------------------------
'  Reliable health check via WinHttp
'  Returns True if server responds with HTTP 200, False otherwise.
' ----------------------------------------------------------------
Function IsServerHealthy()
    Dim wh
    IsServerHealthy = False
    On Error Resume Next
    Set wh = CreateObject("WinHttp.WinHttpRequest.5.1")
    wh.SetTimeouts 500, 500, 1000, 1000   ' resolve, connect, send, receive (ms)
    wh.Open "GET", "http://localhost:8001/health", False
    wh.Send
    If Err.Number = 0 Then
        If wh.Status = 200 Then
            IsServerHealthy = True
        End If
    End If
    On Error Goto 0
End Function

LogMsg "=== VBS launcher v4 started ==="
LogMsg "here=" & here

If Not FSO.FileExists(exePath) Then
    LogMsg "ERROR: exePath missing: " & exePath
    MsgBox "SafariPOSPro.exe was not found in:" & vbCrLf & here, _
           vbCritical, "Safari POS Pro"
    WScript.Quit 1
End If

WshShell.CurrentDirectory = here

' Step 1: Is server already running?
If IsServerHealthy() Then
    LogMsg "Server already running - not starting EXE"
Else
    LogMsg "Server not running - launching EXE"
    WshShell.Run """" & exePath & """", 0, False

    Dim tries, ok
    tries = 0
    ok = False
    Do While tries < 30
        WScript.Sleep 1000
        tries = tries + 1
        If IsServerHealthy() Then
            ok = True
            LogMsg "Server responded after " & tries & "s"
            Exit Do
        End If
    Loop

    If Not ok Then
        LogMsg "ERROR: Server did not start in 30s"
        MsgBox "The Safari POS Pro server did not start within 30 seconds.", _
               vbCritical, "Safari POS Pro"
        WshShell.Run "cmd /c taskkill /F /IM SafariPOSPro.exe >nul 2>&1", 0, True
        WScript.Quit 1
    End If
End If

' Step 2: Find Edge
edgePath = ""
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
    LogMsg "ERROR: Edge not found"
    MsgBox "Microsoft Edge was not found.", vbCritical, "Safari POS Pro"
    WshShell.Run "cmd /c taskkill /F /IM SafariPOSPro.exe >nul 2>&1", 0, True
    WScript.Quit 1
End If
LogMsg "Edge: " & edgePath

' Step 3: Launch Edge
Dim startUrl
If FSO.FileExists(splashPath) Then
    startUrl = "file:///" & Replace(splashPath, "\", "/")
Else
    startUrl = "http://localhost:8001/"
End If
LogMsg "URL: " & startUrl

edgeCmd = """" & edgePath & """ --app=""" & startUrl & """ --disable-http-cache " & _
          "--user-data-dir=""" & edgeProfile & """ " & _
          "--start-maximized --no-first-run --no-default-browser-check"

WshShell.Run edgeCmd, 1, False

' Step 4: Wait for Edge process to appear
Set objWMIService = GetObject("winmgmts:\\.\root\cimv2")
foundEdge = False
waited = 0
Do While Not foundEdge And waited < 60
    WScript.Sleep 500
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
    LogMsg "ERROR: Edge process not detected"
    WshShell.Run "cmd /c taskkill /F /IM SafariPOSPro.exe >nul 2>&1", 0, True
    WScript.Quit 1
End If
LogMsg "Edge detected after " & waited & " x 0.5s"

' Step 5: Wait for Edge to close
Do While True
    WScript.Sleep 500
    foundEdge = False
    Set colProcesses = objWMIService.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'msedge.exe'")
    For Each proc In colProcesses
        If InStr(proc.CommandLine, edgeProfile) > 0 Then
            foundEdge = True
            Exit For
        End If
    Next
    If Not foundEdge Then
        LogMsg "Edge closed - proceeding to kill EXE"
        Exit Do
    End If
Loop

' Step 6: Kill EXE
LogMsg "Issuing taskkill /F /IM SafariPOSPro.exe"
WshShell.Run "cmd /c taskkill /F /IM SafariPOSPro.exe >nul 2>&1", 0, True
LogMsg "taskkill complete - exiting"
LogMsg "=== VBS launcher finished ==="

WScript.Quit 0
