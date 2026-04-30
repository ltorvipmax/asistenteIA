@echo off
setlocal

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "PYTHON_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"
set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\frontend"
set "BACKEND_PORT=8000"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] No se encontro el entorno Python en "%PYTHON_EXE%".
    echo Crea o corrige el entorno virtual antes de iniciar el backend.
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm no esta disponible en PATH.
    echo Instala Node.js o abre una terminal con npm configurado.
    exit /b 1
)

if /i "%~1"=="backend" goto start_backend_only
if /i "%~1"=="frontend" goto start_frontend_only

call :resolve_backend_port

echo Iniciando backend y frontend...
start "Backend - mi-asistente" cmd /k "cd /d "%BACKEND_DIR%" && "%PYTHON_EXE%" -m uvicorn main:app --reload --port %BACKEND_PORT%"
call :wait_for_url "http://127.0.0.1:%BACKEND_PORT%/health" "backend"
start "Frontend - mi-asistente" cmd /k "cd /d "%FRONTEND_DIR%" && set "VITE_API_TARGET=http://127.0.0.1:%BACKEND_PORT%" && npm run dev"
call :wait_for_url "http://localhost:5173" "frontend"
start "" "http://localhost:5173"
goto end

:start_backend_only
call :resolve_backend_port
echo Iniciando solo el backend...
start "Backend - mi-asistente" cmd /k "cd /d "%BACKEND_DIR%" && "%PYTHON_EXE%" -m uvicorn main:app --reload --port %BACKEND_PORT%"
call :wait_for_url "http://127.0.0.1:%BACKEND_PORT%/health" "backend"
goto end

:start_frontend_only
call :resolve_backend_port
echo Iniciando solo el frontend...
start "Frontend - mi-asistente" cmd /k "cd /d "%FRONTEND_DIR%" && set "VITE_API_TARGET=http://127.0.0.1:%BACKEND_PORT%" && npm run dev"
call :wait_for_url "http://localhost:5173" "frontend"
start "" "http://localhost:5173"
goto end

:resolve_backend_port
for /f %%P in ('powershell -NoProfile -Command "$ports = 8000..8010; foreach ($port in $ports) { if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { $port; break } }"') do set "BACKEND_PORT=%%P"

if not defined BACKEND_PORT set "BACKEND_PORT=8000"

if not "%BACKEND_PORT%"=="8000" (
    echo [INFO] El puerto 8000 esta en uso. Se usara el puerto %BACKEND_PORT% para el backend.
)
exit /b 0

:wait_for_url
set "WAIT_URL=%~1"
set "WAIT_NAME=%~2"
echo [INFO] Esperando a que %WAIT_NAME% este disponible en %WAIT_URL%...
powershell -NoProfile -Command "$url = '%WAIT_URL%'; $deadline = (Get-Date).AddSeconds(30); do { try { Invoke-WebRequest -UseBasicParsing $url | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo [WARN] No se pudo confirmar %WAIT_NAME% en 30 segundos. Continuando de todos modos.
) else (
    echo [INFO] %WAIT_NAME% listo.
)
exit /b 0

:end
echo Listo.
echo Backend: http://127.0.0.1:%BACKEND_PORT%
echo Frontend: http://localhost:5173
echo Uso opcional: levantar_servidores.bat backend ^| frontend
exit /b 0