#!/bin/bash
# GGrain v1.0 Launcher for R36S (KNULLI / EmulationStation)
cd /userdata/roms/ports/GGrain || exit 1
export SDL_GAMECONTROLLERCONFIG_FILE="/userdata/system/configs/emulationstation/es_input.cfg"
python3 main.py