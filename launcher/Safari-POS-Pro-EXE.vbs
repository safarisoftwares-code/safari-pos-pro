' ============================================================
'  Safari POS Pro - Launcher for Packaged EXE
'  - Starts SafariPOSPro.exe (from this same folder)
'  - Waits for server health
'  - Launches Edge in app-mode pointing at localhost:8001
'  - Monitors Edge; when it closes, kills the EXE and frees the port
' ============================================================

Option Explicit

Dim WshShell, FSO, here, exePath, edgePath, edgeProfile, splashPath
Dim edgeCmd, cmd, exitCode, i, candidates
Dim objWMIService, colProcesses, proc, foundEdge, waited

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' --- Where am I? (this VBS file's own folder) ---
here = FSO.GetParentFolderName(WScript.ScriptFullName)
exePath = here & "\SafariPOSPro.exe"
edgeProfile = here & "\.edge-profile"
splashPath = here & "\launcher\splash.html"

' If splash is not inside a subfolder, look next to the EXE
If Not FSO.FileExists(splashPath) Then
    splashPath = here & "\splash.html"
End If

If Not FSO.FileExists(exePath) Then
    MsgBox "SafariPOSPro.exe was not found in:" & vbCrLf & here & vbCrLf & vbCrLf & _
           "Please make sure this launcher is in the same folder as SafariPOSPro.exe.", _
           vbCritical, "Safari POS Pro"
    WScript.Quit 1
End If

WshShell.CurrentDirectory = here

' ---------- Step 1: Is server already running? ----------
Dim isRunning
isRunning = False
On Error Resume Next
Dim http
Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
http.setTimeouts 1000, 1000, 2000, 2000
http.open "GET", "http://localhost:8001/health", False
http.send
If http.Status = 200 Then
    isRunning = True
End If
On Error Goto 0

If Not isRunning Then
    ' Launch the EXE hidden
    WshShell.Run """" & exePath & """", 0, False

    ' Wait up to 30s for /health to respond
    Dim tries
    tries = 0
    Do While tries < 30
        WScript.Sleep 1000
        tries = tries + 1
        On Error Resume Next
        Dim http2
        Set http2 = CreateObject("MSXML2.ServerXMLHTTP.6.0")
        http2.setTimeouts 1000, 1000, 2000, 2000
        http2.open "GET", "http://localhost:8001/health", False
        http2.send
        If http2.Status = 200 Then
            On Error Goto 0
            Exit Do
        End If
        On Error Goto 0
    Loop

    If tries >= 30 Then
        MsgBox "The Safari POS Pro server did not start within 30 seconds." & vbCrLf & _
               "Check antivirus settings or port 8001 availability.", _
               vbCritical, "Safari POS Pro"
        ' Try to kill it anyway
        WshShell.Run "cmd /c taskkill /F /IM SafariPOSPro.exe >nul 2>&1", 0, True
        WScript.Quit 1
    End If
End If

' ---------- Step 2: Find Edge ----------
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
    MsgBox "Microsoft Edge was not found." & vbCrLf & _
           "Safari POS Pro requires Microsoft Edge (included with Windows 10/11).", _
           vbCritical, "Safari POS Pro"
    WshShell.Run "cmd /c taskkill /F /IM SafariPOSPro.exe >nul 2>&1", 0, True
    WScript.Quit 1
End If

' ---------- Step 3: Launch Edge in app mode ----------
Dim startUrl
If FSO.FileExists(splashPath) Then
    startUrl = "file:///" & Replace(splashPath, "\", "/")
Else
    startUrl = "http://localhost:8001/"
End If

edgeCmd = """" & edgePath & """ --app=""" & startUrl & """ --disable-http-cache " & _
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
    ' Edge didn't start - kill the EXE and exit
    WshShell.Run "cmd /c taskkill /F /IM SafariPOSPro.exe >nul 2>&1", 0, True
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

' ---------- Step 6: Kill the EXE and free the port ----------
WshShell.Run "cmd /c taskkill /F /IM SafariPOSPro.exe >nul 2>&1", 0, True

WScript.Quit 0
