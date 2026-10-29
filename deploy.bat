@echo off
setlocal EnableDelayedExpansion

:: Ensure the script runs in its own directory
cd /d "%~dp0"

:: ---------------------------------------------------------------------------
:: 1. Run build script
:: ---------------------------------------------------------------------------
echo [1/4] Running buildBlog.py...
python "%~dp0buildBlog.py"
if errorlevel 1 (
    echo.
    echo [ERROR] buildBlog.py failed. Aborting.
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: Locate Brave browser executable
:: ---------------------------------------------------------------------------
set "BRAVE_BIN="
where brave >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "BRAVE_BIN=brave"
) else if exist "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BRAVE_BIN=C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
) else if exist "%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BRAVE_BIN=%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"
)

:: ---------------------------------------------------------------------------
:: 2. Brave open any newly created .html posts and html index
:: ---------------------------------------------------------------------------
set "POST_TITLE=Blog update"
set "HAS_TITLE="

if exist "%~dp0.last_build.txt" (
    for /f "usebackq delims=" %%L in ("%~dp0.last_build.txt") do (
        if not defined HAS_TITLE (
            set "POST_TITLE=%%L"
            set "HAS_TITLE=1"
        ) else (
            set "TARGET_HTML=%%L"
            set "TARGET_HTML=!TARGET_HTML:/=\!"
            if exist "%~dp0!TARGET_HTML!" (
                echo Opening newly created post in Brave: !TARGET_HTML!
                if defined BRAVE_BIN (
                    start "" "!BRAVE_BIN!" "%~dp0!TARGET_HTML!"
                ) else (
                    start "" "%~dp0!TARGET_HTML!"
                )
            )
        )
    )
)

echo Opening index.html in Brave...
if defined BRAVE_BIN (
    start "" "!BRAVE_BIN!" "%~dp0index.html"
) else (
    start "" "%~dp0index.html"
)

:: ---------------------------------------------------------------------------
:: 3. Ask user to confirm, if any input, abort script here
:: ---------------------------------------------------------------------------
echo.
set "CONFIRM="
set /p CONFIRM="Press [Enter] to confirm and push to git (or enter any text to abort): "
if defined CONFIRM (
    echo.
    echo [ABORTED] Deployment cancelled by user.
    if exist "%~dp0.last_build.txt" del "%~dp0.last_build.txt"
    exit /b 1
)

:: Clean up temporary build metadata before git add
if exist "%~dp0.last_build.txt" del "%~dp0.last_build.txt"

:: ---------------------------------------------------------------------------
:: 4. Git deployment
:: ---------------------------------------------------------------------------
echo.
echo [3/4] Staging and committing changes...
git add .
git commit -m "!POST_TITLE!"

echo.
echo [4/4] Pushing to origin main...
git push -u origin main

echo.
echo ============================================================
echo  Deployment complete!
echo ============================================================

