#!/bin/bash
# Baja el feed de la Corte por el Chrome de Juan (Hola VPN en Uruguay), proyecta y sube los datos.
# La página en Vercel lee data/ desde GitHub, así que no hace falta redeployar.
set -u
REPO=/Users/juan/dev/bps-2026-proyeccion
URL="https://eleccionesbps2026.corteelectoral.gub.uy/JSON/ResumenGeneralBPS_P.json"
DL="$HOME/Downloads/ResumenGeneralBPS_P.json"
LOG="$REPO/logs/update.log"
mkdir -p "$REPO/logs" "$REPO/data/raw"
ts=$(date +%Y%m%d-%H%M%S)

rm -f "$HOME/Downloads"/ResumenGeneralBPS_P*.json
osascript -e 'tell application "Google Chrome"' \
  -e "make new tab at end of tabs of front window with properties {URL:\"$URL?$(date +%s)\"}" \
  -e 'end tell' >/dev/null 2>&1
for i in $(seq 1 30); do [ -s "$DL" ] && break; sleep 1; done
if [ ! -s "$DL" ]; then echo "$ts sin descarga (¿Chrome cerrado o Hola apagado?)" >> "$LOG"; exit 1; fi
if ! python3 -c "import json,sys;json.load(open(sys.argv[1],encoding='utf-8-sig'))" "$DL" 2>>"$LOG"; then
  echo "$ts descarga inválida" >> "$LOG"; rm -f "$DL"; exit 1
fi
mv "$DL" "$REPO/data/raw/$ts.json"
rm -f "$HOME/Downloads"/ResumenGeneralBPS_P*.json

cd "$REPO" || exit 1
python3 model/build.py >> "$LOG" 2>&1 || { echo "$ts falló build" >> "$LOG"; exit 1; }
git add data/data.json data/history.json data/raw/"$ts".json
git commit -q -m "Datos $(date +%H:%M)" && git push -q origin main >> "$LOG" 2>&1
echo "$ts ok" >> "$LOG"
