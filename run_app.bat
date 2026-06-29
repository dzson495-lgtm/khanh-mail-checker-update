@echo off
cd /d "%~dp0"

echo Starting Khanh Mail Checker V44...
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0Khanh_Mail_Checker_V44_SMSDateClickCopy.pyw"
) else (
    python "%~dp0Khanh_Mail_Checker_V44_SMSDateClickCopy.pyw"
    pause
)
