"""El Reportero: trae las fuentes que necesitan los canales de noticias, datos y comparaciones, gratis y sin cuota de
YouTube: titulares recientes de Google Noticias (RSS) y los artículos de Wikipedia del tema. El Escritor solo puede
contar lo que digan estas fuentes. Apunta qué titulares ya se usaron para no repetir noticia.

Cada canal dice en config/canales.json qué buscar: "fuentes": {"noticias": ["GTA 6", ...], "wikipedia": ["Grand Theft
Auto VI", ...]}."""
import datetime as dt
import email.utils
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from bots.comun import privado

AGENTE = {"User-Agent": "Mozilla/5.0 (compatible; ciudades-reportero/1.0)"}


def _bajar(url, tiempo=30):
    req = urllib.request.Request(url, headers=AGENTE)
    with urllib.request.urlopen(req, timeout=tiempo) as r:
        return r.read()


def noticias(busqueda, idioma="es", pais="ES", dias=4):
    """Titulares de Google Noticias de los últimos días: [{titulo, fuente, fecha, enlace}]."""
    q = urllib.parse.quote(f"{busqueda} when:{dias}d")
    url = f"https://news.google.com/rss/search?q={q}&hl={idioma}&gl={pais}&ceid={pais}:{idioma}"
    raiz = ET.fromstring(_bajar(url))
    salida = []
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        fuente = (item.findtext("source") or "").strip()
        if fuente and titulo.endswith(f" - {fuente}"):
            titulo = titulo[: -len(fuente) - 3].strip()
        try:
            fecha = email.utils.parsedate_to_datetime(item.findtext("pubDate")).astimezone(dt.timezone.utc)
        except (TypeError, ValueError):
            fecha = None
        salida.append({"titulo": titulo, "fuente": fuente, "fecha": fecha.strftime("%Y-%m-%d %H:%M") if fecha else "",
                       "enlace": item.findtext("link") or ""})
    return salida


def wikipedia(articulo, idioma="en", maximo=6000):
    """Texto llano del artículo (sin tablas), recortado."""
    url = (f"https://{idioma}.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&redirects=1&format=json"
           f"&titles={urllib.parse.quote(articulo)}")
    paginas = json.loads(_bajar(url))["query"]["pages"]
    texto = next(iter(paginas.values())).get("extract", "")
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto[:maximo]


def wist_je_dat(idioma="nl"):
    """Los datos curiosos de la portada de la Wikipedia (sección «Wist je dat…?» en neerlandés, «Did you know…?» en
    inglés): frases cortas, comprobadas y que cambian cada pocos días."""
    import html as html_mod
    pagina = {"nl": "Hoofdpagina", "en": "Main_Page"}.get(idioma, "Hoofdpagina")
    url = (f"https://{idioma}.wikipedia.org/w/api.php?action=parse&page={pagina}&prop=text&format=json"
           "&formatversion=2&disablelimitreport=1")
    texto = json.loads(_bajar(url))["parse"]["text"]
    marca = {"nl": "wist je dat", "en": "did you know"}.get(idioma, "wist je dat")
    i = texto.lower().find(marca)
    if i < 0:
        return []
    trozo = texto[i:i + 8000]
    datos = []
    for item in re.findall(r"<li[^>]*>(.*?)</li>", trozo, flags=re.S):
        limpio = html_mod.unescape(re.sub(r"<[^>]+>", "", item)).strip()
        if 25 < len(limpio) < 400:
            datos.append(limpio)
    return datos[:12]


def _clave(titulo):
    return re.sub(r"\W+", " ", titulo.lower()).strip()[:90]


def fuentes(clave, canal, registro=print):
    """Devuelve (texto numerado para el Escritor, lista de fuentes) o (None, []) si no encuentra nada."""
    cfg = canal.get("fuentes") or {}
    usados = set(privado.leer(os.path.join("estado", "reportero", f"{clave}.json"), []) or [])
    lista = []
    for busqueda in cfg.get("noticias", []):
        try:
            for n in noticias(busqueda, idioma=canal.get("idioma", "es")[:2], pais=canal.get("pais", "ES")):
                if _clave(n["titulo"]) not in usados and all(_clave(n["titulo"]) != _clave(x["titulo"]) for x in lista):
                    lista.append(dict(n, tipo="noticia"))
        except Exception as e:  # una fuente caída no para el turno
            registro(f"reportero: Google Noticias no contesta ({type(e).__name__})")
    lista.sort(key=lambda n: n["fecha"], reverse=True)
    lista = lista[:25]
    if cfg.get("wist_je_dat"):
        try:
            for dato in wist_je_dat(cfg.get("wist_je_dat_idioma", "nl")):
                if _clave(dato) not in usados:
                    lista.append({"tipo": "noticia", "titulo": dato, "fuente": "Wikipedia (Wist je dat)", "fecha": "",
                                  "enlace": ""})
        except Exception as e:
            registro(f"reportero: la portada de Wikipedia no contesta ({type(e).__name__})")
    for articulo in cfg.get("wikipedia", []):
        try:
            texto = wikipedia(articulo, idioma=cfg.get("wikipedia_idioma", "en"))
            if texto:
                lista.append({"tipo": "enciclopedia", "titulo": f"Wikipedia: {articulo}", "texto": texto})
        except Exception as e:
            registro(f"reportero: Wikipedia no contesta ({type(e).__name__})")
    if not lista:
        return None, []
    partes = []
    for i, f in enumerate(lista, 1):
        if f["tipo"] == "noticia":
            partes.append(f"[{i}] {f['fecha']} · {f['fuente']}: {f['titulo']}")
        else:
            partes.append(f"[{i}] {f['titulo']}\n{f['texto']}")
    return "\n".join(partes), lista


def apuntar_usadas(clave, lista, numeros):
    """Guarda los titulares que ha usado el Escritor para no repetir la misma noticia."""
    ruta = os.path.join("estado", "reportero", f"{clave}.json")
    usados = privado.leer(ruta, []) or []
    for n in numeros or []:
        try:
            f = lista[int(str(n).strip("[] ")) - 1]
        except (ValueError, IndexError):
            continue
        if f.get("tipo") == "noticia":
            usados.append(_clave(f["titulo"]))
    privado.escribir(ruta, usados[-400:])
