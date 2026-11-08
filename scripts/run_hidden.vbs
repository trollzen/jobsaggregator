' Starts run_scheduled.ps1 with no console window (used by the Task Scheduler task).
' A visible PowerShell window could be closed by accident, which killed the run (0xC000013A).
Set sh = CreateObject("WScript.Shell")
dir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
code = sh.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & dir & "\run_scheduled.ps1""", 0, True)
WScript.Quit code
