@echo off
chcp 65001 >nul
REM ==========================================================================
REM  Build HollowKnightSaveManager.exe (Windows)
REM  Freeze save_manager_win.py into a self-contained .exe with PyInstaller.
REM  Requires a real Python install that ships Tcl/Tk (tkinter).
REM  NOTE: the Microsoft Store "python" alias is NOT a real interpreter and
REM        will be rejected by the checks below.
REM ==========================================================================
setlocal
cd /d "%~dp0"

REM ---------- 1) locate a working Python interpreter ----------
set "PYEXE="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYEXE=py -3"
)
if not defined PYEXE (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PYEXE=python"
    )
)
if not defined PYEXE goto NOPYTHON
echo [0/3] Using Python: %PYEXE%
%PYEXE% -c "import sys;print('      version:',sys.version.split()[0])"

REM ---------- 2) require tkinter (Tcl/Tk) ----------
%PYEXE% -c "import tkinter" >nul 2>&1
if errorlevel 1 goto NOTK

REM ---------- 3) ensure PyInstaller ----------
echo [1/3] Ensuring PyInstaller is available...
%PYEXE% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo       PyInstaller not found, installing via pip...
    %PYEXE% -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] pip install pyinstaller failed. Check your network / Python.
        pause
        exit /b 1
    )
)

REM ---------- 4) build ----------
echo [2/3] Building one-file windowed executable...
%PYEXE% -m PyInstaller --noconfirm --onefile --windowed ^
    --name "HollowKnightSaveManager" ^
    --icon "icon.ico" ^
    --clean ^
    save_manager_win.py
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo [3/3] Done.
echo.
echo Build succeeded: dist\HollowKnightSaveManager.exe
echo Double-click it to run; no Python required on the target machine.
pause
exit /b 0

:NOPYTHON
echo [ERROR] No working Python interpreter found.
echo         ("python" may be the Microsoft Store alias, which is not usable here.)
echo.
echo         Install Python 3.11+ from https://www.python.org/downloads/windows/
echo         and tick "Add python.exe to PATH" during setup, then run this again.
echo         The official installer includes tkinter (Tcl/Tk) by default.
pause
exit /b 1

:NOTK
echo [ERROR] Your Python is missing tkinter (Tcl/Tk), which this GUI app needs.
echo         Reinstall Python from https://www.python.org/downloads/windows/
echo         (the official installer includes Tcl/Tk), then run this again.
pause
exit /b 1
