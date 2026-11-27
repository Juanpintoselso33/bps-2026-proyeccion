"""Proyección del escrutinio departamental BPS 2026.

Compara el feed departamental (D) con el primario final (P) y proyecta lo que falta:
- Departamentos con observados ya incorporados (CircuitosFlgConObservados): de ahí se mide
  cuántos votos a listas deja cada sobre observado (rendimiento) y hacia qué listas se
  inclinan respecto de cómo votó ese departamento en el primario (factor por lista).
- Departamentos pendientes: se reponen los circuitos que faltan con su dato primario y se
  suman sus observados con ese rendimiento y esa inclinación aplicada a su reparto primario.
- Intervalo 95%: bootstrap sobre los departamentos ya cerrados; cada departamento pendiente
  toma el rendimiento de un departamento cerrado al azar.

Uso: python3 model/dep.py  (lee data/dep/D-*.json más nuevo y data/dep/P-*.json)
"""
import glob
import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from project import NOMBRES, CANDIDATOS, HOC  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = 4000


def load(p):
    return json.load(open(p, encoding="utf-8-sig"))


def votos(o):
    return {x["Id"]: x["Total"] for x in o["Opciones"]}


def proyectar_orden(D, P, oi, rng):
    ids = [x["Id"] for x in D[0]["Ordenes"][oi]["Opciones"]]
    done, pend, actual, filas = [], [], {i: 0 for i in ids}, []
    for d, p in zip(D[1:], P[1:]):
        od, op = d["Ordenes"][oi], p["Ordenes"][oi]
        vd, vp = votos(od), votos(op)
        for i in ids:
            actual[i] += vd[i]
        dl = {i: vd[i] - vp[i] for i in ids}
        faltan = d["CircuitosTotal"] - d["CircuitosEscrutados"]
        r = dict(n=d["DepNombre"], obs=op["TotalObservados"], vp=vp, dl=dl, faltan=faltan)
        listo = bool(d["CircuitosFlgConObservados"])
        (done if listo else pend).append(r)
        filas.append({"depto": d["DepNombre"], "obs_incorporados": listo, "observados": op["TotalObservados"],
                      "rechazados": od.get("TotalObservadosRechazados", 0),
                      "circ": f'{d["CircuitosEscrutados"]}/{d["CircuitosTotal"]}',
                      "delta": {str(i): dl[i] for i in ids} if listo else None})

    base = dict(actual)
    for r in pend:  # reponer circuitos faltantes con el dato primario
        if r["faltan"] > 0:
            for i in ids:
                base[i] -= min(0, r["dl"][i])

    def medir(sample):
        obs = sum(r["obs"] for r in sample)
        add = {i: sum(r["dl"][i] for r in sample) for i in ids}
        tot = sum(add.values())
        if obs <= 0 or tot <= 0:
            return None
        esp = {i: sum(r["vp"][i] / max(1, sum(r["vp"].values())) * sum(r["dl"].values()) for r in sample) for i in ids}
        fac = {i: max(add[i], 0.5) / max(esp[i], 0.5) for i in ids}
        rend = [sum(r["dl"].values()) / r["obs"] for r in sample if r["obs"] > 0]
        return tot / obs, fac, rend

    def completar(m, por_depto):
        y, fac, rend = m
        t = dict(base)
        for r in pend:
            yy = rng.choice(rend) if por_depto else y
            v = max(0.0, yy) * r["obs"]
            w = {i: r["vp"][i] * fac[i] for i in ids}
            sw = sum(w.values()) or 1
            for i in ids:
                t[i] += v * w[i] / sw
        return t

    m = medir(done) if done else None
    if m is None or not pend:
        proy, sims, rend_med, fac = dict(base), [dict(base)], None, None
    else:
        proy = completar(m, False)
        rend_med, fac = m[0], m[1]
        sims = []
        for _ in range(B):
            s = [rng.choice(done) for _ in done]
            ms = medir(s)
            if ms:
                sims.append(completar(ms, True))
    total = sum(proy.values())
    orden_ids = sorted(ids, key=lambda i: -proy[i])
    a, b = orden_ids[0], orden_ids[1]
    difs = sorted(s[a] - s[b] for s in sims)
    n = len(difs)
    listas = []
    for i in orden_ids:
        ps = sorted(100 * s[i] / sum(s.values()) for s in sims)
        listas.append({"id": i, "nombre": f"Lista {i}", "agrupacion": NOMBRES.get(i, ""),
                       "candidato": CANDIDATOS.get(i, ""), "hoc": i in HOC,
                       "actual": actual[i], "proy": round(proy[i]),
                       "proy_pct": round(100 * proy[i] / total, 2),
                       "ic_lo": round(ps[int(.025 * n)], 2), "ic_hi": round(ps[int(.975 * n) - 1 if n > 1 else 0], 2),
                       "factor_obs": round(fac[i], 2) if fac else None})
    return {
        "orden": D[0]["Ordenes"][oi]["OrdenDsc"],
        "lider": f"Lista {a}", "segundo": f"Lista {b}",
        "dif_actual": actual[a] - actual[b], "dif_proy": round(proy[a] - proy[b]),
        "dif_lo": round(difs[int(.025 * n)]), "dif_hi": round(difs[int(.975 * n) - 1 if n > 1 else 0]),
        "dif_pp": round(100 * (proy[a] - proy[b]) / total, 2),
        "prob_lider": round(100 * sum(x > 0 for x in difs) / n, 1),
        "obs_pendientes": sum(r["obs"] for r in pend),
        "deptos_pendientes": [r["n"] for r in pend],
        "rendimiento": round(rend_med, 3) if rend_med is not None else None,
        "listas": listas, "deptos": filas,
    }


def main():
    ds = sorted(glob.glob(os.path.join(REPO, "data/dep/D-*.json")))
    ps = sorted(glob.glob(os.path.join(REPO, "data/dep/P-*.json")))
    D, P = load(ds[-1]), load(ps[-1])
    rng = random.Random(1)
    out = {"fecha_corte": D[0]["FechaConsulta"], "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
           "circuitos_escrutados": D[0]["CircuitosEscrutados"], "circuitos_total": D[0]["CircuitosTotal"],
           "primario_corte": P[0]["FechaConsulta"],
           "ordenes": [proyectar_orden(D, P, oi, rng) for oi in range(len(D[0]["Ordenes"]))]}
    json.dump(out, open(os.path.join(REPO, "data/dep.json"), "w", encoding="utf-8"), ensure_ascii=False)
    hp = os.path.join(REPO, "data/dep_history.json")
    hist = json.load(open(hp)) if os.path.exists(hp) else []
    if not hist or hist[-1]["corte"] != out["fecha_corte"]:
        hist.append({"corte": out["fecha_corte"], "ordenes": {o["orden"]: [o["dif_actual"], o["dif_proy"], o["dif_lo"], o["dif_hi"]] for o in out["ordenes"]}})
    json.dump(hist, open(hp, "w", encoding="utf-8"), ensure_ascii=False)
    for o in out["ordenes"]:
        print(o["orden"], o["lider"], "dif actual", o["dif_actual"], "proy", o["dif_proy"], f'[{o["dif_lo"]},{o["dif_hi"]}]',
              "prob", o["prob_lider"], "pend", o["deptos_pendientes"], o["obs_pendientes"])


if __name__ == "__main__":
    main()
