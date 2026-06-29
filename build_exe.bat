@echo off
cd /d "%~dp0"

echo Installing / updating PyInstaller...
python -m pip install --upgrade pip
python -m pip install pyinstaller

echo Building exe...
pyinstaller --onefile --windowed --name "Khanh_Mail_Checker_V44_SMSDateClickCopy" "Khanh_Mail_Checker_V44_SMSDateClickCopy.pyw"

echo.
echo Done.
echo EXE: dist\Khanh_Mail_Checker_V44_SMSDateClickCopy.exe
pause
