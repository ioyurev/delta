@echo off
setlocal

set APP_NAME=Delta
set SPEC_FILE=delta.spec
set BUILD_DIR=build
set DIST_DIR=dist

title Building %APP_NAME%...
echo.
echo  ========================================================
echo    STARTING BUILD PROCESS: %APP_NAME%
echo  ========================================================

uv --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo  [ERROR] 'uv' not found!
    pause
    exit /b 1
)

echo.
echo  [1/6] Preparing directories...
if exist %BUILD_DIR% (
    rmdir /s /q %BUILD_DIR%
)
mkdir %BUILD_DIR%

if exist %DIST_DIR% (
    rmdir /s /q %DIST_DIR%
)

echo.
echo  [2/6] Installing project (for metadata)...
uv pip install .
if %errorlevel% neq 0 (
    echo  [WARNING] Failed to install package. Metadata might be missing.
)

echo.
echo  [3/6] Generating assets in '%BUILD_DIR%'...

:: [FIX #3] Передаем путь для сохранения аргументом
uv run tools/make_icon.py %BUILD_DIR%\icon.ico
if %errorlevel% neq 0 exit /b 1

uv run tools/make_splash.py %BUILD_DIR%\splash.png
if %errorlevel% neq 0 exit /b 1

echo.
echo  [4/6] Running PyInstaller via uv...
:: workpath перенаправляет временные файлы PyInstaller внутрь build/temp
uv run pyinstaller %SPEC_FILE% --clean --noconfirm --workpath %BUILD_DIR%\temp --distpath %DIST_DIR%

if %errorlevel% neq 0 (
    color 0C
    echo.
    echo  ========================================================
    echo    [ERROR] BUILD FAILED!
    echo  ========================================================
    pause
    exit /b 1
)

echo.
echo  [5/6] Finalizing...
:: Папку build не удаляем, чтобы можно было проверить артефакты, если нужно.
:: Но она содержит temp файлы PyInstaller, которые можно почистить.
rmdir /s /q %BUILD_DIR%\temp

color 0A
echo.
echo  ========================================================
echo    [SUCCESS] BUILD COMPLETE!
echo  ========================================================
echo.
echo  Executable: %~dp0%DIST_DIR%\%APP_NAME%\%APP_NAME%.exe
echo.

pause
endlocal
