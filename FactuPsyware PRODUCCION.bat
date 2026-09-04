@echo off
rem ============================================================
rem  FactuPsyware PRODUCCION.bat
rem  Lanza el sistema contra AFIP REAL (entorno de producción).
rem  Los comprobantes emitidos desde aquí son fiscalmente válidos.
rem ============================================================
cd /d "%~dp0"
call "%~dp0FactuPsyware.bat" PRODUCCION
