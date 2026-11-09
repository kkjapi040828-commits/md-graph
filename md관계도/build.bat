@echo off
setlocal EnableExtensions
title md graph builder

rem ==================================================================
rem  md graph builder  --  double-click this file
rem
rem  What it does:
rem    1. looks at the folder that CONTAINS this package folder
rem    2. runs graph_explorer.py with Python 3.10 or newer
rem    3. opens the result in the default web browser
rem
rem  This file is ASCII only and has no BOM ON PURPOSE.
rem  Non-English letters inside a .bat file break on Windows, so every
rem  message here is plain English. README.md explains each message
rem  in Korean, one line per message.
rem ==================================================================

rem --- 1. the folder to map = parent of this package folder --------
pushd "%~dp0.." 2>nul
if errorlevel 1 goto :err_parent
set "ROOT=%CD%"
popd
set "PKGDIR=%~dp0"
echo Map folder: %ROOT%

rem --- 1b. did the user flatten the package into their md folder? ---
rem     WHY (measured 2026-11-09): if someone extracts the three files
rem     directly into their md folder instead of keeping the package
rem     folder, then ROOT becomes the folder ABOVE their md folder.
rem     The build still succeeded (exit 0) and quietly mapped the wrong
rem     folder. That was the only failure mode without an error message.
rem
rem     HOW WE DETECT IT: the package folder normally holds only its own
rem     README.md. If it also holds OTHER .md files, the user's documents
rem     were mixed into it, so the package was flattened.
rem     This check is ASCII only (matches the file-name README.md), so it
rem     works on any Windows code page.
set "OWNMD=0"
for /f "delims=" %%F in ('dir /b /a-d "%PKGDIR%*.md" 2^>nul') do (
    if /i not "%%F"=="README.md" set /a OWNMD+=1
)
if not "%OWNMD%"=="0" goto :err_flat

rem --- 2. is there at least one .md file worth mapping? ------------
rem     README.md inside this package folder does not count.
rem     NOTE: do NOT use findstr with a path here. A path ends with a
rem     backslash and findstr reads  \"  as an escaped quote, so the
rem     filter silently matches nothing (measured 2026-11-09).
set "MDCOUNT=0"
for /f "delims=" %%F in ('dir /b /s /a-d "%ROOT%\*.md" 2^>nul') do (
    if /i not "%%~dpF"=="%PKGDIR%" set /a MDCOUNT+=1
)
if "%MDCOUNT%"=="0" goto :err_nomd
echo Found %MDCOUNT% .md file(s).

rem --- 3. find Python 3 (py launcher first: it never opens the Store) ----
set "PY="
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto :check_version
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY goto :err_nopy

:check_version
rem --- 4. is it 3.10 or newer? ------------------------------------
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 goto :err_oldpy

rem --- 5. build the graph (UTF-8 console so Korean text shows) -----
rem     PYTHONWARNINGS only silences the harmless SyntaxWarning from a
rem     backslash inside graph_explorer.py's docstring. We must not edit
rem     that file, so we turn that one warning class off here instead.
set "PYTHONIOENCODING=utf-8"
set "PYTHONWARNINGS=ignore::SyntaxWarning"
chcp 65001 >nul 2>nul
echo Building the graph. Please wait ...
set "LOG=%TEMP%\mdgraph_log_%RANDOM%.txt"
%PY% "%~dp0graph_explorer.py" --root "%ROOT%" > "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
set "PYTHONWARNINGS="
type "%LOG%"
if not "%RC%"=="0" goto :err_run

rem --- 6. the program prints "OK  <full path>" on its first line ----
rem     take that path, so we open exactly what it made.
set "OUTHTML="
for /f "usebackq tokens=1,* delims= " %%A in ("%LOG%") do (
    if /i "%%A"=="OK" if not defined OUTHTML set "OUTHTML=%%B"
)
del "%LOG%" >nul 2>nul

set "FOUND="
if defined OUTHTML if exist "%OUTHTML%" set "FOUND=%OUTHTML%"
if not defined FOUND for /f "delims=" %%H in ('dir /b /a-d /o-d "%ROOT%\_docs\*.html" 2^>nul') do if not defined FOUND set "FOUND=%ROOT%\_docs\%%H"
if not defined FOUND for /f "delims=" %%H in ('dir /b /a-d /o-d "%ROOT%\*.html" 2^>nul') do if not defined FOUND set "FOUND=%ROOT%\%%H"
if not defined FOUND goto :err_nohtml

start "" "%FOUND%"

echo.
echo Done. The graph is open in your browser.
echo File: %FOUND%
echo You can close this window.
echo Press any key to close ...
pause >nul
exit /b 0


rem ==================================================================
rem  messages -- plain English on purpose, see README.md for Korean
rem ==================================================================
:err_parent
echo.
echo [ERROR] Cannot open the folder above this package folder.
echo         Unzip this package INSIDE the folder you want to map,
echo         then double-click build.bat again.
echo.
pause
exit /b 1

:err_flat
echo.
echo [ERROR] This package folder also contains YOUR .md files.
echo         That means the three files were taken out of the package
echo         folder and dropped directly into your documents folder.
echo.
echo         If you continue, the tool would map the folder ABOVE your
echo         documents -- the wrong place -- and say "Done" anyway.
echo         So it stopped here instead.
echo.
echo FIX: delete the three files (build.bat, graph_explorer.py,
echo      README.md) from this folder, then unzip the package again
echo      and KEEP the folder that the unzip creates whole.
echo.
echo      Result you want:  your-docs-folder\THE-UNZIPPED-FOLDER\build.bat
echo.
pause
exit /b 1

:err_nomd
echo.
echo [ERROR] No .md files found in: %ROOT%
echo         Put this package folder inside a folder that has .md files.
echo         (This package's own README.md is not counted.)
echo.
pause
exit /b 1

:err_nopy
echo.
echo [ERROR] Python 3.10 or newer is not installed on this computer.
echo       1. Open  https://www.python.org/downloads/
echo       2. Install Python and TICK the box "Add python.exe to PATH".
echo       3. Double-click build.bat again.
echo.
pause
exit /b 1

:err_oldpy
echo.
echo [ERROR] Your Python is too old. Please install Python 3.10 or newer.
echo         https://www.python.org/downloads/
echo.
pause
exit /b 1

:err_run
echo.
echo [ERROR] The graph program stopped with an error.
echo         The lines above say why. Show this window to the sender.
echo         Log kept at: %LOG%
echo.
pause
exit /b 1

:err_nohtml
echo.
echo [ERROR] The program ran but no .html file was found in:
echo         %ROOT%
echo.
pause
exit /b 1
