@echo off
chcp 65001 >nul
title Cerrar Facturacion

echo ============================================================
echo  Cerrando todos los procesos de Facturacion...
echo ============================================================
echo.

taskkill /f /im pythonw.exe >nul 2>nul
if %errorlevel%==0 (echo - Proceso pythonw.exe cerrado.) else (echo - No habia pythonw.exe corriendo.)

taskkill /f /im python.exe >nul 2>nul
if %errorlevel%==0 (echo - Proceso python.exe cerrado.) else (echo - No habia python.exe corriendo.)

echo.
echo Listo. Ahora podes volver a abrir "FactuPsyware.bat" sin problemas.
echo.
pause
