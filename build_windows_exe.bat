@echo off
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopy

echo Creating virtual environment...
%PY% -m venv .venv || goto fail
call .venv\Scripts\activate.bat

echo Installing pygame and PyInstaller...
python -m pip install --upgrade pip || goto fail
python -m pip install -r requirements.txt || goto fail

echo Building CQB_Trainer.exe ...
pyinstaller --noconfirm --clean --onefile --windowed --name CQB_Trainer cqb_game.py || goto fail

echo.
echo ================================================
echo  DONE.  Your game is:  dist\CQB_Trainer.exe
echo ================================================
pause
exit /b 0

:nopy
echo Python 3 was not found. Install Python 3.11 or 3.12 from python.org
echo and tick "Add python.exe to PATH", then run this file again.
pause
exit /b 1

:fail
echo.
echo Build failed - see the messages above.
pause
exit /b 1
