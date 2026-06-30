@echo off
cd /d "%~dp0.."
"%~dp0..\venv\Scripts\pythonw.exe" "%~dp0..\main.py" --minimized
