@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem ============================================================
rem  Instalacion manual del entorno (dependencias de Python).
rem  Uso normal: NO hace falta correr esto - "2 - Iniciar
rem  Facturacion.vbs" se instala solo automaticamente.
rem  Este archivo queda como respaldo para forzar una
rem  reinstalacion manual si algo falla.
rem ============================================================

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY_LAUNCHER=py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY_LAUNCHER=python"
    ) else (
        echo ERROR: No se encontro Python instalado. Instalalo desde python.org
        pause
        exit /b 1
    )
)

rem ------------------------------------------------------------
rem  Cerrar cualquier proceso python/pythonw que haya quedado
rem  corriendo (si no, sus archivos quedan bloqueados y el venv
rem  no se puede borrar ni recrear -> "Acceso denegado").
rem ------------------------------------------------------------
echo Cerrando procesos de Facturacion que puedan estar abiertos...
taskkill /f /im pythonw.exe >nul 2>nul
taskkill /f /im python.exe >nul 2>nul
timeout /t 2 /nobreak >nul

echo Creando entorno virtual...
if exist venv (
    rmdir /s /q venv >nul 2>nul
    if exist venv (
        echo.
        echo ============================================================
        echo  ERROR: no se pudo borrar la carpeta "venv" (acceso denegado).
        echo  Cerra cualquier ventana de Facturacion / Python que tengas
        echo  abierta y volve a ejecutar este archivo.
        echo ============================================================
        pause
        exit /b 1
    )
)
%PY_LAUNCHER% -m venv venv

if not exist "venv\Scripts\python.exe" (
    echo.
    echo ERROR: no se pudo crear el entorno virtual.
    pause
    exit /b 1
)

echo Instalando dependencias...
venv\Scripts\python.exe -m pip install --upgrade pip -q
venv\Scripts\python.exe -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo ERROR: fallo la instalacion de dependencias. Revisa tu conexion a internet.
    pause
    exit /b 1
)
copy /y requirements.txt venv\.deps_ok >nul

rem ------------------------------------------------------------
rem  Chequeo final: confirmar que Django quedo realmente instalado
rem  antes de decir "Listo" (evita falsos positivos).
rem ------------------------------------------------------------
venv\Scripts\python.exe -c "import django" >nul 2>nul
if not !errorlevel!==0 (
    echo.
    echo ============================================================
    echo  ERROR: la instalacion no quedo completa ^(Django no se pudo
    echo  importar^). Volve a ejecutar este archivo.
    echo  Si se repite, puede ser el antivirus bloqueando archivos:
    echo  agrega esta carpeta como excepcion en tu antivirus.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo Listo. Ahora hace doble clic en "2 - Iniciar Facturacion.vbs"
pause
