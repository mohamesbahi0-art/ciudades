"""El Cartógrafo (canal de mapas): el mapa del mundo de los vídeos de bolas-país.

- Una vez (o cuando falte): convierte el mapa libre de Natural Earth (dominio público; el paquete world-atlas, licencia
  ISC) en mundo.json: la forma de cada país ya proyectada (Natural Earth I), su nombre en español, su centro y su
  encuadre (el de su parte principal: España sin Canarias, Estados Unidos sin Alaska…).
      python bots/estudio/cartografo.py construir countries-110m.json   (necesita pycountry solo para esto)
- En cada vídeo: el encuadre de cada escena (el mundo, la zona o el país) y los vecinos de un país, para colocar las
  bolas donde toca.
"""
import json
import math
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
MUNDO = os.path.join(AQUI, "datos", "mundo.json")
BANDERAS = os.path.join(AQUI, "banderas")
ANCHO = 4000
_MUNDO = {}


# ---------- construir mundo.json (una vez) ----------
def _proyectar(lon, lat):
    """Natural Earth I, en píxeles de un mapa de ANCHO de ancho."""
    l, p = math.radians(lon), math.radians(lat)
    p2 = p * p
    x = l * (0.870700 - p2 * (0.131979 + p2 * (0.013791 + p2 * p2 * p2 * (0.003971 * p2 - 0.001529))))
    y = p * (1.007226 + p2 * (0.015085 + p2 * p2 * (-0.044475 + 0.028874 * p2 - 0.005916 * p2 * p2)))
    escala = ANCHO / (2 * 2.7354)
    return (x + 2.7354) * escala, (1.4224 - y) * escala


def _arcos(topo):
    t = topo.get("transform")
    salida = []
    for arco in topo["arcs"]:
        x = y = 0
        puntos = []
        for dx, dy in arco:
            x, y = x + dx, y + dy
            puntos.append((x * t["scale"][0] + t["translate"][0], y * t["scale"][1] + t["translate"][1]) if t else (x, y))
        salida.append(puntos)
    return salida


def _anillo(indices, arcos):
    puntos = []
    for i in indices:
        a = arcos[i] if i >= 0 else list(reversed(arcos[~i]))
        puntos.extend(a if not puntos else a[1:])
    return puntos


def _area(anillo):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(anillo, anillo[1:] + anillo[:1]))) / 2


def _centroide(anillo):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(anillo, anillo[1:] + anillo[:1]):
        f = x0 * y1 - x1 * y0
        a, cx, cy = a + f, cx + (x0 + x1) * f, cy + (y0 + y1) * f
    if abs(a) < 1e-9:
        return sum(x for x, _ in anillo) / len(anillo), sum(y for _, y in anillo) / len(anillo)
    return cx / (3 * a), cy / (3 * a)


def construir(ruta_topojson, salida=MUNDO):
    import gettext
    import pycountry
    es = gettext.translation("iso3166-1", pycountry.LOCALES_DIR, languages=["es"])
    topo = json.load(open(ruta_topojson, encoding="utf-8"))
    arcos = _arcos(topo)
    paises = {}
    for g in topo["objects"]["countries"]["geometries"]:
        nombre_en = (g.get("properties") or {}).get("name", "")
        c = pycountry.countries.get(numeric=str(g.get("id"))) if g.get("id") else None
        iso2 = c.alpha_2 if c else {"Kosovo": "XK"}.get(nombre_en)
        if not iso2 or g["type"] not in ("Polygon", "MultiPolygon"):
            continue
        poligonos = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
        anillos = []
        for pol in poligonos:
            for k, indices in enumerate(pol):
                geo = _anillo(indices, arcos)
                if sum(lon for lon, _ in geo) / len(geo) > 0:      # lo que cruza el meridiano 180 se queda a un lado
                    geo = [(lon + 360 if lon < -90 else lon, lat) for lon, lat in geo]
                else:
                    geo = [(lon - 360 if lon > 90 else lon, lat) for lon, lat in geo]
                anillos.append((k == 0, [_proyectar(lon, lat) for lon, lat in geo]))
        exteriores = [a for ext, a in anillos if ext]
        if not exteriores:
            continue
        principal = max(exteriores, key=_area)
        grande = _area(principal)
        cuerpo = [a for a in exteriores if _area(a) >= grande * 0.08 and         # sin territorios de ultramar
                  math.dist(_centroide(a), _centroide(principal)) < 300] or [principal]
        xs = [x for a in cuerpo for x, _ in a]
        ys = [y for a in cuerpo for _, y in a]
        d = "".join("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in a) + "Z" for _, a in anillos if len(a) > 2)
        nombre = es.gettext(c.name) if c else "Kosovo"
        nombre = {"BO": "Bolivia", "VE": "Venezuela", "RU": "Rusia", "KR": "Corea del Sur", "KP": "Corea del Norte",
                  "IR": "Irán", "TW": "Taiwán", "VN": "Vietnam", "TZ": "Tanzania", "SY": "Siria", "MD": "Moldavia",
                  "LA": "Laos", "CD": "R. D. del Congo", "PS": "Palestina", "TR": "Turquía", "FK": "Islas Malvinas",
                  "TF": "Tierras Australes Francesas", "GB": "Reino Unido", "US": "Estados Unidos",
                  "CZ": "Chequia"}.get(iso2, nombre)
        paises[iso2] = {"nombre": nombre, "d": d, "caja": [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))],
                        "centro": [round(v) for v in _centroide(principal)], "area": round(grande)}
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    datos = {"ancho": ANCHO, "alto": round(2 * 1.4224 * ANCHO / (2 * 2.7354)), "proyeccion": "Natural Earth I",
             "fuente": "Natural Earth (dominio público), paquete world-atlas 2.0.2 (ISC)", "paises": paises}
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    return len(paises)


# ---------- en cada vídeo ----------
def mundo():
    if not _MUNDO:
        _MUNDO.update(json.load(open(MUNDO, encoding="utf-8")))
    return _MUNDO


def existe(iso2):
    return str(iso2 or "").upper() in mundo()["paises"]


def tiene_bandera(iso2):
    return os.path.exists(os.path.join(BANDERAS, f"{str(iso2).lower()}.svg"))


def nombre(iso2):
    return mundo()["paises"].get(str(iso2).upper(), {}).get("nombre", str(iso2))


def por_nombre(texto):
    """De un nombre en español («Reino Unido», «méxico») a su código; None si no lo conoce."""
    import unicodedata
    plano = lambda s: "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")  # noqa: E731
    t = plano(texto.strip())
    for iso, p in mundo()["paises"].items():
        if plano(p["nombre"]) == t:
            return iso
    return {"eeuu": "US", "ee. uu.": "US", "usa": "US", "inglaterra": "GB", "holanda": "NL", "paises bajos": "NL",
            "corea": "KR", "rusia": "RU", "chequia": "CZ", "republica checa": "CZ"}.get(t)


def vecinos(iso2, cuantos=6, margen=0.35):
    """Los países que tocan (o casi) al de iso2, de más grande a más pequeño."""
    p = mundo()["paises"].get(str(iso2).upper())
    if not p:
        return []
    x0, y0, x1, y1 = p["caja"]
    mx, my = min((x1 - x0) * margen, 140) + 20, min((y1 - y0) * margen, 140) + 20     # un país grande no llega a otro continente
    cerca = []
    for iso, q in mundo()["paises"].items():
        if iso in (iso2.upper(), "AQ"):        # la Antártida no es vecina de nadie
            continue
        a0, b0, a1, b1 = q["caja"]
        if a1 >= x0 - mx and a0 <= x1 + mx and b1 >= y0 - my and b0 <= y1 + my:
            cx, cy = q["centro"]
            dentro = x0 - mx <= cx <= x1 + mx and y0 - my <= cy <= y1 + my
            cerca.append((not dentro, -q["area"], iso))
    return [iso for _, _, iso in sorted(cerca)[:cuantos]]


def encuadre(plano, iso2=None, otros=()):
    """La caja del mapa que se ve en una escena (vertical 9:16, el mapa ocupa la parte de arriba)."""
    m = mundo()
    if not iso2 or not existe(iso2):
        return [0, 0, m["ancho"], m["alto"]]
    if plano == "mundo":                     # medio mundo alrededor del país: en vertical, el mundo entero se ve diminuto
        cx, cy = m["paises"][iso2.upper()]["centro"]
        cy = min(max(cy, 760), m["alto"] - 760)
        return [round(cx - 1000), round(cy - 760), round(cx + 1000), round(cy + 760)]
    cajas = [m["paises"][iso2.upper()]["caja"]] + [m["paises"][o]["caja"] for o in otros if o in m["paises"]]
    x0, y0 = min(c[0] for c in cajas), min(c[1] for c in cajas)
    x1, y1 = max(c[2] for c in cajas), max(c[3] for c in cajas)
    holgura = 0.35 if plano == "zona" else 0.18
    w, h = (x1 - x0) * (1 + 2 * holgura) + 60, (y1 - y0) * (1 + 2 * holgura) + 60
    w, h = max(w, h * 0.9, 260), max(h, 240)                       # casi cuadrado: así cabe en el móvil
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [round(cx - w / 2), round(cy - h / 2), round(cx + w / 2), round(cy + h / 2)]


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "construir":
        print(f"cartógrafo: {construir(sys.argv[2])} países en {MUNDO}")
    else:
        print(__doc__)
