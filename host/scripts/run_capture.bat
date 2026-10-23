@echo off
REM VW MEB CAN FD Bus Monitor - Capture Wrapper for Windows
REM Usage: run_capture.bat COM14 300 [output_dir]

set PORT=%1
set DURATION=%2
set OUTDIR=%3

if "%PORT%"=="" (
    echo Usage: run_capture.bat PORT DURATION [OUTDIR]
    echo Example: run_capture.bat COM14 300 logs
    exit /b 1
)

if "%DURATION%"=="" set DURATION=60
if "%OUTDIR%"=="" set OUTDIR=logs

mkdir %OUTDIR% 2>nul

set TIMESTAMP=%DATE:~6,4%%DATE:~3,2%%DATE:~0,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set OUTFILE=%OUTDIR%\capture_%TIMESTAMP%.csv

echo Starting capture on %PORT% for %DURATION% seconds...
echo Output: %OUTFILE%

cd /d "%~dp0.."
python -m cli capture --port %PORT% --baud 115200 --tty-baudrate 500000 --duration %DURATION% --output %OUTFILE% --filter "0x5A2,0x5AC,0xF7,0x503,0x3B5,0x668,0x5E1,0x5E9,0x5CD,0x3C0,0x58C,0x17FC007B,0x17FC00B9,0x746" --format csv

echo Capture complete. See %OUTFILE%