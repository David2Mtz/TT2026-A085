@echo off
title Puente LSL - Debug
echo ===================================================
echo Iniciando Puente TCP a LSL (Modo Debug)...
echo ===================================================
echo.

:: Hemos quitado --invisible temporalmente y agregado pause al final
"C:\Program Files\openvibe-3.7.0-64bit\bin\openvibe-designer.exe" --play "C:\Users\Laptop\Documents\Trabajo Terminal\TT2\TT_Interfaz\Puente.xml"

echo.
echo ===================================================
echo El puente se ha detenido. Lee el error de arriba.
echo ===================================================
pause