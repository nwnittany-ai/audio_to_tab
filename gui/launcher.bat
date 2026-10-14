@echo off
rem Starts the audio2tab window with no console window (pythonw), like the stem maker's launch.bat.
cd /d "%~dp0.."
start "" ".venv\Scripts\pythonw.exe" gui\app.py
