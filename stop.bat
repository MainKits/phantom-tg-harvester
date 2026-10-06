@echo off
title Phantom TG Harvester - Stop
echo Stopping all Phantom processes...
taskkill /f /fi "WINDOWTITLE eq Phantom Backend*" 2>nul
taskkill /f /fi "WINDOWTITLE eq Phantom Frontend*" 2>nul
echo Done.
timeout /t 2
