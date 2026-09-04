@echo off
cd /d "%~dp0.."
echo Reseteando password del usuario admin...
echo.
"venv\Scripts\python.exe" manage.py changepassword admin
echo.
pause
