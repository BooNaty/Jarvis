Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
jarvisDir = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
pythonw = jarvisDir & "\venv\Scripts\pythonw.exe"
mainPy = jarvisDir & "\main.py"
cmd = """" & pythonw & """ """ & mainPy & """ --minimized"
sh.Run cmd, 0, False
