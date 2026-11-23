"""El Archivero de mapas (canal de mapas): ordena las series «¿Y si X desapareciera?» para que salgan en orden.

Cada país es una serie de 3 partes que salen seguidas (la Parte 2 después de la 1, la 3 después de la 2). El Archivero
lee todos los títulos del canal (los programados que dejó la fábrica antigua, los ya publicados y los nuestros) y decide
qué toca ahora:
1. Si una serie se quedó a medias (por ejemplo, solo la Parte 1), la termina primero, con lo que pasó en las partes
   anteriores para que la historia siga. Las series viejas de una sola parte acaban en la Parte 2.
2. Si no, empieza un país nuevo de la lista, sin repetir ninguno.
Se fía solo de los títulos («… (Parte N)»), así que nunca se desordena aunque un vídeo falle y se repita.
"""
import os
import re

from bots.comun import privado
from bots.estudio import cartografo

PARTES = 3
# Países que no se tocan: guerras o conflictos abiertos (el humor de bolas-país ahí puede hacer daño de verdad)
FUERA = {"UA", "RU", "IL", "PS", "SY", "YE", "SD", "SS", "AF", "MM", "KP", "AQ", "TF", "FK", "EH", "XK", "CY"}
# Orden para el público hispano: primero lo cercano y conocido
ORDEN = ["DE", "JP", "PT", "CN", "CA", "AU", "EC", "BO", "PY", "GT", "CR", "PA", "HN", "SV", "NI", "DO", "PR", "IN",
         "EG", "MA", "KR", "TR", "GR", "NL", "CH", "SE", "NO", "IS", "GL", "NZ", "ZA", "NG", "SA", "TH", "PH", "ID",
         "IE", "BE", "AT", "PL", "DK", "FI", "VN", "MY", "KE", "ET", "PE", "JM", "CU", "VE", "UY", "CO", "CL", "AR",
         "MX", "ES", "US", "BR", "IT", "FR", "GB"]
OTROS_NOMBRES = {"US": ["Estados Unidos", "EEUU", "EE. UU.", "USA"], "GB": ["Reino Unido", "Inglaterra"],
                 "NL": ["Países Bajos", "Holanda"], "KR": ["Corea del Sur", "Corea"], "DO": ["República Dominicana"],
                 "CZ": ["Chequia", "República Checa"], "CD": ["Congo"]}
PARTE = re.compile(r"\(\s*parte\s*(\d+)\s*\)", re.I)


def titulos(clave):
    """Todos los títulos del canal, en orden: programados viejos, publicados y los nuestros."""
    revision = privado.leer(os.path.join("estado", "canales", f"{clave}.json"), {}) or {}
    publicados = [v.get("titulo", "") for v in reversed(revision.get("recientes") or []) if isinstance(v, dict)]
    lista, vistos = [], set()
    for t in publicados + privado.titulos_recientes(clave, 500):
        if t and t not in vistos:
            vistos.add(t)
            lista.append(t)
    return lista


def _nombres():
    nombres = {}
    for iso, p in cartografo.mundo()["paises"].items():
        for n in [p["nombre"]] + OTROS_NOMBRES.get(iso, []):
            nombres[n.lower()] = iso
    return sorted(nombres.items(), key=lambda x: -len(x[0]))      # los nombres largos primero («Corea del Sur»)


def pais_del_titulo(titulo, nombres=None):
    """El país protagonista: el que sale antes en el título («México desaparece y Estados Unidos…» → México)."""
    t = titulo.lower()
    mejor = None
    for nombre, iso in nombres or _nombres():
        m = re.search(rf"(?<![\w]){re.escape(nombre)}(?![\w])", t)
        if m and (mejor is None or m.start() < mejor[0]):
            mejor = (m.start(), iso)
    return mejor[1] if mejor else None


def series(clave):
    """{iso: {"partes": [1, 2], "titulos": [...]}} en el orden en que empezaron."""
    nombres = _nombres()
    salida = {}
    for t in titulos(clave):
        iso = pais_del_titulo(t, nombres)
        if not iso:
            continue
        m = PARTE.search(t)
        s = salida.setdefault(iso, {"partes": [], "titulos": []})
        s["partes"].append(int(m.group(1)) if m else 1)
        s["titulos"].append(t)
    return salida


SERIES = os.path.join("estado", "mapas", "series.json")      # las series que empezamos nosotros y cuántas partes tienen


def siguiente(clave):
    """Lo que toca: {"pais", "nombre", "parte", "partes", "anteriores"}."""
    hechas = series(clave)
    nuestras = privado.leer(SERIES, {}) or {}
    for iso, s in nuestras.items():                     # 1. terminar nuestras series (la parte que falte, en orden)
        hecho = max(hechas.get(iso, {}).get("partes") or [0])
        if hecho < int(s.get("partes", PARTES)) and iso not in FUERA:
            return {"pais": iso, "nombre": cartografo.nombre(iso), "parte": hecho + 1, "partes": int(s.get("partes", PARTES)),
                    "anteriores": hechas.get(iso, {}).get("titulos", [])}
    for iso, s in hechas.items():                       # 2. las viejas que se quedaron en la Parte 1 acaban en la 2
        if iso not in nuestras and s["partes"] == [1] and iso not in FUERA:
            return {"pais": iso, "nombre": cartografo.nombre(iso), "parte": 2, "partes": 2, "anteriores": s["titulos"]}
    for iso in ORDEN + sorted(cartografo.mundo()["paises"], key=lambda k: -cartografo.mundo()["paises"][k]["area"]):
        if iso not in hechas and iso not in nuestras and iso not in FUERA and cartografo.existe(iso) \
                and cartografo.tiene_bandera(iso):
            return {"pais": iso, "nombre": cartografo.nombre(iso), "parte": 1, "partes": PARTES, "anteriores": []}
    return {"pais": "ES", "nombre": "España", "parte": 1, "partes": PARTES, "anteriores": []}


def apuntar(clave, eleccion, titulo):
    """Apunta la serie (si empieza una nuestra) y lo que se ha escrito, en el cuaderno del Archivero."""
    if eleccion["parte"] == 1:
        nuestras = privado.leer(SERIES, {}) or {}
        nuestras.setdefault(eleccion["pais"], {"partes": eleccion["partes"], "empezada": privado.ahora()})
        privado.escribir(SERIES, nuestras)
    c = privado.cuaderno("archivero_mapas")
    c.apuntar("serie", {"pais": eleccion["pais"], "parte": eleccion["parte"], "partes": eleccion["partes"],
                        "titulo": titulo, "canal": privado.alias(clave)})
    c.guardar()
