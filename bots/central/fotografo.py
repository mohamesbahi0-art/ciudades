"""El Fotógrafo: busca en Wikimedia Commons una foto LIBRE para cada escena (biografías de gente real) y la deja lista
en vertical. Solo fotos que se pueden usar sin nombrar a nadie (dominio público y CC0), porque el dueño no quiere
créditos en sus vídeos. Fuera todas las demás (CC BY, SA, NC, ND). De dónde sale cada una queda apuntado en privado.
No copia fotos de vídeos de otros creadores. Si una escena no tiene foto, usa la de la escena de al lado."""
import html
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
AGENTE = "ciudades-bot/1.0 (fotos libres con su credito para videos cortos)"
# El dueño no quiere créditos en sus vídeos: por eso solo valen las fotos que NO piden nombrar a nadie (dominio público
# y CC0). Las CC BY obligan a nombrar al autor, así que quedan fuera.
LIBRES = ("public domain", "pd", "cc0", "no restrictions")


def _libre(licencia):
    l = re.sub(r"[-_]", " ", str(licencia or "").lower()).strip()
    return bool(l) and "sa" not in l.split() and "nc" not in l.split() and "nd" not in l.split() and \
        any(l == x or l.startswith(x + " ") for x in LIBRES)


def _texto(valor):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", str(valor or "")))).strip()


NO_SON_FOTOS = ("logo", "map", "kaart", "karte", "coat of arms", "wapen", "signature", "handtekening", "flag", "vlag",
                "icon", "diagram", "chart", "stamp", "postzegel", "locator", "blason", "escudo")
USOS_POR_FOTO = 3              # una misma foto, como mucho en 3 escenas (con encuadres distintos)
MIN_DISTINTAS = 5              # con menos fotos distintas no hay vídeo: se cambia de persona


def buscar(consulta, cuantas=40):
    """Fotos libres de Commons para una búsqueda: [{titulo, url, ancho, alto, autor, licencia, pagina}]."""
    q = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrsearch": f"{consulta} filetype:bitmap",
                                "gsrnamespace": 6, "gsrlimit": cuantas, "prop": "imageinfo",
                                "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1280, "format": "json"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            paginas = (json.load(r).get("query") or {}).get("pages") or {}
    except (urllib.error.URLError, ValueError, OSError):
        return []
    fotos = []
    for p in sorted(paginas.values(), key=lambda x: x.get("index", 99)):
        i = (p.get("imageinfo") or [{}])[0]
        m = i.get("extmetadata") or {}
        licencia = _texto((m.get("LicenseShortName") or {}).get("value"))
        if i.get("mime") not in ("image/jpeg", "image/png") or not _libre(licencia) or min(i.get("width") or 0, i.get("height") or 0) < 500:
            continue
        titulo = str(p.get("title") or "").lower()
        if any(x in titulo for x in NO_SON_FOTOS):           # logos, mapas, escudos, firmas: no son fotos de la persona
            continue
        fotos.append({"titulo": p.get("title", ""), "url": i.get("thumburl") or i.get("url"), "ancho": i.get("width"),
                      "alto": i.get("height"), "autor": _texto((m.get("Artist") or {}).get("value"))[:80] or "Wikimedia Commons",
                      "licencia": licencia, "pagina": i.get("descriptionurl")})
    return fotos


def _vertical(origen, destino):
    """La foto entera sobre su propio fondo desenfocado, en 1080×1920 (así no se corta ninguna cara)."""
    filtro = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:4,eq=brightness=-0.18[f];"
              "[0:v]scale=1080:1500:force_original_aspect_ratio=decrease[p];[f][p]overlay=(W-w)/2:(H-h)/2-90")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", origen, "-filter_complex", filtro, "-frames:v", "1",
                    "-q:v", "3", destino], check=True)


def hay_fotos(persona):
    """Cuántas fotos libres distintas hay de esa persona (para elegir de quién se puede hacer el vídeo)."""
    return len({f["url"] for f in buscar(str(persona or "").strip()[:80])}) if str(persona or "").strip() else 0


def fotografiar(escenas, carpeta, persona=""):
    """Una foto por escena (None si no hay ninguna que valga) y de dónde sale cada una. Primero la foto que pide la
    escena; si no hay, una de la persona. Las fotos se reparten: la menos usada primero y ninguna más de 3 veces; una
    escena que solo podría repetir una foto ya gastada se queda sin foto (y cuenta como que falta)."""
    os.makedirs(carpeta, exist_ok=True)
    usos, hechas, origen, rutas, cache = {}, {}, [], [], {}
    for n, e in enumerate(escenas, 1):
        ruta = None
        for consulta in dict.fromkeys(x for x in (str(e.get("dibujo") or "").strip()[:80], persona) if x):
            if consulta not in cache:
                cache[consulta] = buscar(consulta)
            for f in sorted(cache[consulta], key=lambda x: usos.get(x["url"], 0)):   # la menos usada primero
                if usos.get(f["url"], 0) >= USOS_POR_FOTO:
                    continue
                if f["url"] not in hechas:                     # cada foto se baja y se prepara una sola vez
                    cruda = os.path.join(carpeta, f"cruda{n:02d}")
                    lista = os.path.join(carpeta, f"foto{len(hechas) + 1:02d}.jpg")
                    try:
                        req = urllib.request.Request(f["url"], headers={"User-Agent": AGENTE})
                        with urllib.request.urlopen(req, timeout=60) as r, open(cruda, "wb") as out:
                            out.write(r.read(25_000_000))
                        _vertical(cruda, lista)
                    except (urllib.error.URLError, OSError, ValueError, subprocess.CalledProcessError):
                        usos[f["url"]] = USOS_POR_FOTO          # esa foto no se puede usar: no se vuelve a probar
                        continue
                    finally:
                        if os.path.exists(cruda):
                            os.remove(cruda)
                    hechas[f["url"]] = lista
                    origen.append({"pagina": f.get("pagina"), "autor": f.get("autor"), "licencia": f.get("licencia")})
                usos[f["url"]] = usos.get(f["url"], 0) + 1
                ruta = hechas[f["url"]]
                break
            if ruta:
                break
        rutas.append(ruta)
    if len(hechas) < MIN_DISTINTAS:                 # con tan pocas fotos el vídeo sería una sola imagen: no vale
        return [None] * len(escenas), origen
    return rutas, origen
