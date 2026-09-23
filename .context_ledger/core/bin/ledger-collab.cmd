@echo off
rem ledger-collab.cmd -- policy-free launcher for ledger-collab.ps1 (Windows).
rem A .cmd file is executed by cmd.exe, which ignores the PowerShell
rem execution policy; this shim starts the matching .ps1 with
rem -ExecutionPolicy Bypass so the documented Windows invocations work on
rem a stock machine without any Set-ExecutionPolicy step. It targets
rem Windows PowerShell 5.1 on purpose: it ships with every Windows 10+
rem install, while pwsh 7 is an optional add-on.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ledger-collab.ps1" %*
exit /b %ERRORLEVEL%
