@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem ============================================================
rem  ATENCION: este entorno factura contra AFIP REAL.
rem  Los comprobantes emitidos aqui son fiscales.
rem ============================================================
set ARCA_ENTORNO=produccion

rem ============================================================
rem  0) Matar procesos colgados de una corrida anterior.
rem     SIEMPRE primero, antes de tocar nada del venv.
rem ============================================================
taskkill /f /im pythonw.exe >nul 2>nul
taskkill /f /im python.exe >nul 2>nul

rem ============================================================
rem  1) Verificar que Python este disponible en esta PC
rem ============================================================
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY_LAUNCHER=py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY_LAUNCHER=python"
    ) else (
        echo.
        echo ============================================================
        echo  ERROR: No se encontro Python instalado en esta computadora.
        echo  Instalalo desde https://www.python.org/downloads/
        echo  (marcar la casilla "Add Python to PATH" durante la instalacion)
        echo  y volve a ejecutar este archivo.
        echo ============================================================
        echo.
        pause
        exit /b 1
    )
)

rem ============================================================
rem  2) Verificar si el venv existe y funciona en ESTA pc
rem ============================================================
set "VENV_OK=0"
if exist "%~dp0venv\Scripts\python.exe" (
    if exist "%~dp0venv\Scripts\pip.exe" (
        "%~dp0venv\Scripts\python.exe" -c "import django" >nul 2>nul
        if !errorlevel!==0 (
            set "VENV_OK=1"
        )
    )
)

if "!VENV_OK!"=="0" (
    echo.
    echo Preparando el entorno por primera vez en esta computadora...
    echo (esto puede tardar uno o dos minutos, solo ocurre una vez)
    echo.

    timeout /t 1 /nobreak >nul

    if exist "%~dp0venv" (
        rmdir /s /q "%~dp0venv" >nul 2>nul
    )
    if exist "%~dp0venv" (
        echo.
        echo ============================================================
        echo  ERROR: no se pudo borrar la carpeta "venv" ^(acceso denegado^).
        echo  Cerra cualquier ventana de Facturacion o Python abierta
        echo  y volve a intentar.
        echo ============================================================
        pause
        exit /b 1
    )

    %PY_LAUNCHER% -m venv "%~dp0venv"
    if not exist "%~dp0venv\Scripts\python.exe" (
        echo ERROR: no se pudo crear el entorno virtual. Revisa que Python este bien instalado.
        pause
        exit /b 1
    )
    if exist "%~dp0venv\.deps_ok" del "%~dp0venv\.deps_ok"
)

rem ============================================================
rem  3) Instalar/actualizar dependencias solo si hace falta
rem ============================================================
set "NEED_INSTALL=0"
if not exist "%~dp0venv\.deps_ok" set "NEED_INSTALL=1"
if exist "%~dp0venv\.deps_ok" (
    fc /b "%~dp0requirements.txt" "%~dp0venv\.deps_ok" >nul 2>nul
    if not !errorlevel!==0 set "NEED_INSTALL=1"
)

if "!NEED_INSTALL!"=="1" (
    echo.
    echo Instalando dependencias necesarias...
    "%~dp0venv\Scripts\python.exe" -m pip install --upgrade pip -q
    "%~dp0venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" -q
    if !errorlevel! neq 0 (
        echo.
        echo ERROR: fallo la instalacion de dependencias. Revisa tu conexion a internet.
        pause
        exit /b 1
    )
    copy /y "%~dp0requirements.txt" "%~dp0venv\.deps_ok" >nul
    echo Dependencias instaladas correctamente.
)

rem ============================================================
rem  4) Aplicar migraciones de base de datos si hacen falta
rem ============================================================
"%~dp0venv\Scripts\python.exe" manage.py migrate --check >nul 2>nul
if not !errorlevel!==0 (
    echo Actualizando la base de datos...
    "%~dp0venv\Scripts\python.exe" manage.py migrate
)

rem ============================================================
rem  5) Levantar el servidor y abrir el navegador
rem ============================================================
echo.
echo Iniciando Facturacion (ENTORNO REAL)...
start "" /b "%~dp0venv\Scripts\pythonw.exe" manage.py runserver 0.0.0.0:8000 > "%~dp0server_produccion.log" 2>&1
timeout /t 3 /nobreak >nul
start http://127.0.0.1:8000/facturas/
echo Listo. Esta ventana se puede cerrar.
timeout /t 3 /nobreak >nul
