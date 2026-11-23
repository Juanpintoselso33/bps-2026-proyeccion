"""Proyecta todos los cortes guardados en data/raw y arma data.json (último) + history.json."""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from project import proyectar  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
raws = sorted(glob.glob(os.path.join(REPO, "data/raw/*.json")))
hist, vistos, ultimo = [], set(), None
for r in raws:
    raw = json.load(open(r, encoding="utf-8-sig"))
    corte = raw[0]["FechaConsulta"]
    if corte in vistos:
        continue
    vistos.add(corte)
    res = proyectar(raw)
    ultimo = res
    hist.append({
        "corte": corte, "pct": res["pct_circuitos"],
        "ordenes": {o["orden"]: {l["nombre"]: [l["proy_pct"], l["ic_lo"], l["ic_hi"], l["crudo_pct"]]
                                 for l in o["listas"]} for o in res["ordenes"]},
    })
hist.sort(key=lambda h: h["pct"])
json.dump(ultimo, open(os.path.join(REPO, "data/data.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump(hist, open(os.path.join(REPO, "data/history.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(ultimo["fecha_corte"], ultimo["pct_circuitos"], [(o["orden"], o["lider"], o["prob_lider"]) for o in ultimo["ordenes"]])
