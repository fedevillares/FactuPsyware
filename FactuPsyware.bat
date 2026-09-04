@echo off
cd /d "%~dp0"

rem ============================================================
rem  FactuPsyware.bat
rem  Uso diario: entorno de homologacion (pruebas, no fiscal).
rem  Si se llama con el argumento PRODUCCION, arranca contra
rem  AFIP real en su lugar.
rem ============================================================
if /i "%~1"=="PRODUCCION" (
    call "%~dp0iniciar_facturacion_produccion.bat"
) else (
    call "%~dp0iniciar_facturacion.bat"
)
