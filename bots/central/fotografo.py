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


def buscar(consulta, cuantas=8):
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


def fotografiar(escenas, carpeta, persona=""):
    """Una foto por escena (None si no hay ninguna que valga) y los créditos de las usadas."""
    os.makedirs(carpeta, exist_ok=True)
    usadas, creditos, rutas, cache = set(), [], [], {}
    for n, e in enumerate(escenas, 1):
        ruta = None
        for consulta in dict.fromkeys(x for x in (str(e.get("dibujo") or "").strip()[:80], persona) if x):
            if consulta not in cache:
                cache[consulta] = buscar(consulta)
            for f in sorted(cache[consulta], key=lambda x: x["url"] in usadas):   # primero las que no han salido
                cruda = os.path.join(carpeta, f"cruda{n:02d}")
                try:
                    req = urllib.request.Request(f["url"], headers={"User-Agent": AGENTE})
                    with urllib.request.urlopen(req, timeout=60) as r, open(cruda, "wb") as out:
                        out.write(r.read())
                    ruta = os.path.join(carpeta, f"escena{n:02d}.jpg")
                    _vertical(cruda, ruta)
                except (urllib.error.URLError, OSError, subprocess.CalledProcessError):
                    ruta = None
                    continue
                finally:
                    if os.path.exists(cruda):
                        os.remove(cruda)
                if f["url"] not in usadas:
                    creditos.append(f"{f['autor']} ({f['licencia']})")
                usadas.add(f["url"])
                break
            if ruta:
                break
        rutas.append(ruta)
    return rutas, list(dict.fromkeys(creditos))
