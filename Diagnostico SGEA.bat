@echo off
chcp 65001 >nul
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERRO: Python nao encontrado.
    pause
    exit /b 1
)
python "%~dp0diagnostico.py"
