"""Proyección de las elecciones BPS 2026 (Uruguay) a partir del feed de la Corte Electoral.

Método: estimador de razón estratificado por departamento (conteo rápido clásico).
- Cada departamento es un estrato. Los circuitos ya escrutados son una muestra de
  conglomerados (circuitos) de ese estrato.
- Votos finales esperados del estrato: votos contados x (circuitos totales / circuitos
  escrutados). Así cada departamento pesa por su tamaño real y no por lo que llegó primero
  (el interior cuenta antes que Montevideo).
- Proporción de cada lista en el estrato: la observada en sus circuitos escrutados.
- Proyección nacional: suma de los estratos (contado + pendiente estimado).
- Varianza: binomial sobre votos válidos, inflada por efecto de diseño de conglomerados
  Varianza de muestreo de conglomerados: S^2 / n por estrato (S = desvío de la proporción
  entre circuitos), con corrección por población finita (1 - n/N).
  Solo aporta varianza la parte NO contada.
"""
import json
import math
import sys
from datetime import datetime

S_CIRC = 0.10  # desvío de la proporción de una lista entre circuitos de un mismo depto (10 pts, conservador)
Z = 1.96
# Sesgo por orden de llegada: los circuitos pendientes de un depto pueden votar distinto
# de los ya contados (urbanos/grandes entran al final). Se modela como un corrimiento
# sistemático, correlacionado entre departamentos, de B puntos sobre los votos pendientes.
B_LISTA = 0.03   # 3 pts sobre la proporción de una lista
B_DIF = 0.05     # 5 pts sobre la diferencia entre las dos primeras

# Hay Otro Camino presenta lista en los tres órdenes
HOC = {15, 5, 25}
NOMBRES = {
    11: "Tu equipo en BPS (PIT-CNT)", 15: "Hay Otro Camino",
    1: "ONAJPU", 2: "COJUPE", 5: "Hay Otro Camino",
    21: "Diálogo, experiencia y compromiso", 25: "Hay Otro Camino",
    27: "Con voz propia", 30: "Defendiendo los intereses del país",
}
CANDIDATOS = {
    11: "Carlos Clavijo", 15: "Lorena Paola Roqueta", 1: "Estela Ovelar",
    2: "María Ángela Pereira", 5: "Renaldo Borriero", 21: "Graciela Álvarez",
    25: "Jorge Fernández", 27: "Bernardo Aldabalde", 30: "Daniel Añón",
}


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def proyectar(raw):
    pais = raw[0]
    deptos = raw[1:]
    out = {
        "fecha_corte": pais["FechaConsulta"],
        "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "circuitos_escrutados": pais["CircuitosEscrutados"],
        "circuitos_total": pais["CircuitosTotal"],
        "pct_circuitos": float(pais["CircuitosPorcentaje"]),
        "ordenes": [],
    }
    for oi, orden_pais in enumerate(pais["Ordenes"]):
        ids = [o["Id"] for o in orden_pais["Opciones"]]
        proj = {i: 0.0 for i in ids}
        var = {i: 0.0 for i in ids}
        cov_terms = []  # por estrato, para la varianza de la diferencia
        n_of = {}
        crudo = {o["Id"]: o["Total"] for o in orden_pais["Opciones"]}
        filas = []
        for d in deptos:
            o = d["Ordenes"][oi]
            assert o["OrdenId"] == orden_pais["OrdenId"]
            n, N = d["CircuitosEscrutados"], d["CircuitosTotal"]
            votos = {x["Id"]: x["Total"] for x in o["Opciones"]}
            validos = sum(votos.values())
            emit = o["Total"]
            if n == 0 or validos == 0:
                # estrato sin datos: se imputa con la proporción nacional cruda
                # y votos esperados = habilitados x participación nacional observada
                filas.append({"depto": d["DepNombre"], "pct": 0.0, "validos": 0,
                              "proy_validos": None, "shares": None})
                cov_terms.append(None)
                continue
            f = n / N
            validos_fin = validos / f
            pend = validos_fin - validos
            shares = {i: votos[i] / validos for i in ids}
            deff = None
            fila = {"depto": d["DepNombre"], "pct": round(100 * f, 1), "validos": validos,
                    "proy_validos": round(validos_fin), "habilitados": o["TotalHabilitados"],
                    "shares": {str(i): round(100 * shares[i], 2) for i in ids}}
            filas.append(fila)
            for i in ids:
                proj[i] += votos[i] + pend * shares[i]
                # varianza de los votos pendientes de la lista i en el estrato
                v_share = S_CIRC ** 2 / n * (1 - f)
                var[i] += (pend ** 2) * v_share
            t = (pend, shares, validos, deff, f)
            n_of[id(t)] = n
            cov_terms.append(t)

        # estratos sin datos: proporción nacional de lo proyectado hasta ahora
        tot_proj = sum(proj.values())
        for d, fila in zip(deptos, filas):
            if fila["shares"] is None:
                o = d["Ordenes"][oi]
                part = orden_pais["Total"] / max(1, sum(x["Ordenes"][oi]["TotalHabilitados"] for x in deptos if x["CircuitosEscrutados"] > 0))
                esperado = o["TotalHabilitados"] * part * (sum(crudo.values()) / orden_pais["Total"])
                for i in ids:
                    s = proj[i] / tot_proj
                    proj[i] += esperado * s
                    var[i] += esperado ** 2 * 0.0025  # +-5 pts de incertidumbre

        total = sum(proj.values())
        pend_tot = total - sum(crudo.values())
        for i in ids:
            var[i] += (pend_tot * B_LISTA) ** 2
        listas = []
        for i in ids:
            p = proj[i] / total
            se = math.sqrt(var[i]) / total
            listas.append({
                "id": i, "nombre": f"Lista {i}", "agrupacion": NOMBRES.get(i, ""),
                "candidato": CANDIDATOS.get(i, ""), "hoc": i in HOC,
                "crudo_votos": crudo[i],
                "crudo_pct": round(100 * crudo[i] / sum(crudo.values()), 2),
                "proy_pct": round(100 * p, 2),
                "ic_lo": round(100 * max(0, p - Z * se), 2),
                "ic_hi": round(100 * min(1, p + Z * se), 2),
                "proy_votos": round(proj[i]),
            })
        listas.sort(key=lambda x: -x["proy_pct"])
        a, b = listas[0], listas[1]
        # varianza de la diferencia a-b: en cada estrato var(sa - sb) multinomial
        vd = 0.0
        for t in cov_terms:
            if t is None:
                continue
            pend, sh, val, deff, f = t
            pa, pb = sh[a["id"]], sh[b["id"]]
            vdiff = 2 * S_CIRC ** 2 / n_of[id(t)] * (1 - f)
            vd += pend ** 2 * vdiff
        vd += (pend_tot * B_DIF) ** 2
        diff = (a["proy_votos"] - b["proy_votos"]) / total
        se_diff = math.sqrt(vd) / total if vd > 0 else 1e-9
        prob = norm_cdf(diff / se_diff)
        if prob >= 0.995:
            veredicto = f"Tendencia estadísticamente irreversible para {a['nombre']}"
        elif prob >= 0.95:
            veredicto = f"{a['nombre']} con ventaja clara"
        elif prob >= 0.75:
            veredicto = f"{a['nombre']} favorita, todavía reversible"
        else:
            veredicto = f"Empate técnico entre {a['nombre']} y {b['nombre']}"
        out["ordenes"].append({
            "orden": orden_pais["OrdenDsc"],
            "veredicto": veredicto,
            "ventaja_pts": round(100 * diff, 2),
            "ventaja_ic": round(100 * Z * se_diff, 2),
            "prob_lider": round(100 * prob, 1),
            "lider": a["nombre"],
            "emitidos": orden_pais["Total"],
            "habilitados": orden_pais["TotalHabilitados"],
            "blanco": orden_pais["TotalBlanco"], "anulados": orden_pais["TotalAnulados"],
            "observados": orden_pais["TotalObservados"],
            "listas": listas,
            "deptos": sorted(filas, key=lambda r: -(r.get("habilitados") or 0)),
        })
    return out


if __name__ == "__main__":
    raw = json.load(open(sys.argv[1], encoding="utf-8-sig"))
    res = proyectar(raw)
    json.dump(res, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for o in res["ordenes"]:
        print(o["orden"], o["veredicto"], f"prob {o['prob_lider']}%",
              [(l["nombre"], l["crudo_pct"], l["proy_pct"], l["ic_lo"], l["ic_hi"]) for l in o["listas"]])
