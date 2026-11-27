#!/bin/bash
# Escrutinio departamental: baja el feed D por el Chrome de Juan (Hola en Uruguay), proyecta y sube data/dep.json.
set -u
REPO=/Users/juan/dev/bps-2026-proyeccion
URL="https://eleccionesbps2026.corteelectoral.gub.uy/JSON/ResumenGeneralBPS_D.json"
DL="$HOME/Downloads/ResumenGeneralBPS_D.json"
LOG="$REPO/logs/update_dep.log"
mkdir -p "$REPO/logs" "$REPO/data/dep"
ts=$(date +%Y%m%d-%H%M)
rm -f "$HOME/Downloads"/ResumenGeneralBPS_D*.json
osascript -e 'tell application "Google Chrome"' \
  -e "make new tab at end of tabs of front window with properties {URL:\"$URL?$(date +%s)\"}" \
  -e 'end tell' >/dev/null 2>&1
for i in $(seq 1 30); do [ -s "$DL" ] && break; sleep 1; done
if [ ! -s "$DL" ]; then echo "$ts sin descarga" >> "$LOG"; exit 1; fi
corte=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8-sig'))[0]['FechaConsulta'])" "$DL" 2>>"$LOG") || { echo "$ts descarga inválida" >> "$LOG"; exit 1; }
prev=$(python3 -c "import json;print(json.load(open('$REPO/data/dep.json'))['fecha_corte'])" 2>/dev/null)
mv "$DL" "$REPO/data/dep/D-$ts.json"
if [ "$corte" = "$prev" ] && [ "${FORCE:-0}" != 1 ]; then rm -f "$REPO/data/dep/D-$ts.json"; echo "$ts sin corte nuevo ($corte)" >> "$LOG"; exit 0; fi
python3 "$REPO/model/dep.py" >> "$LOG" 2>&1 || { echo "$ts falló dep.py" >> "$LOG"; exit 1; }
git -C "$REPO" add data/dep.json data/dep_history.json "data/dep/D-$ts.json" data/dep/P-*.json
git -C "$REPO" commit -q -m "Departamental $corte" && git -C "$REPO" push -q origin main >> "$LOG" 2>&1
echo "$ts ok $corte" >> "$LOG"
