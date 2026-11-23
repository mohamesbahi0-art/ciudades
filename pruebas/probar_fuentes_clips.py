"""Prueba: ¿hay vídeos de GTA con licencia libre que un robot pueda bajar solo, sin saltarse nada?

YouTube no deja bajar vídeos a los robots (y eso no se salta). Esta prueba mira tres sitios que sí lo permiten porque es
su forma normal de funcionar: Internet Archive (archive.org), PeerTube (buscador común Sepia Search) y Wikimedia Commons.
Cuenta los vídeos de GTA 5 y GTA 6 con licencia Creative Commons que dejan bajar el archivo, y prueba a bajar el principio
de alguno. En el registro público solo salen cifras; el detalle va al repositorio privado (estado/clips/fuentes_libres.json).

    python pruebas/probar_fuentes_clips.py
"""
import json
import os
import sys
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from bots.comun import privado  # noqa: E402

AGENTE = {"User-Agent": "ciudades-buscador/1.0 (prueba de fuentes con licencia libre)"}
BUSQUEDAS = ["GTA 6", "GTA VI", "GTA 5", "GTA V", "Grand Theft Auto"]


def pedir(url, cabeceras=None, limite=None, espera=40):
    req = urllib.request.Request(url, headers=dict(AGENTE, **(cabeceras or {})))
    with urllib.request.urlopen(req, timeout=espera) as r:
        return r.status, (r.read(limite) if limite else r.read())


def probar_descarga(url):
    """Baja solo el primer MB, para ver que el archivo se puede bajar de verdad."""
    try:
        estado, datos = pedir(url, {"Range": "bytes=0-1048575"}, limite=1048576)
        return {"ok": estado in (200, 206) and len(datos) > 10000, "bytes": len(datos)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:80]}"}


def archivo_org():
    vistos, salida = set(), []
    for q in BUSQUEDAS:
        consulta = f'("{q}") AND mediatype:movies AND licenseurl:*creativecommons*'
        url = ("https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(
            {"q": consulta, "fl[]": ["identifier", "title", "licenseurl", "downloads"], "rows": 50, "output": "json"},
            doseq=True))
        try:
            docs = json.loads(pedir(url)[1]).get("response", {}).get("docs", [])
        except Exception as e:
            salida.append({"busqueda": q, "error": f"{type(e).__name__}: {str(e)[:80]}"})
            continue
        for d in docs:
            if d["identifier"] in vistos:
                continue
            vistos.add(d["identifier"])
            salida.append({"id": d["identifier"], "titulo": str(d.get("title"))[:120], "licencia": d.get("licenseurl"),
                           "busqueda": q})
    # mira los archivos de los 5 primeros: ¿hay un mp4 que se pueda bajar?
    for item in [x for x in salida if x.get("id")][:5]:
        try:
            meta = json.loads(pedir(f"https://archive.org/metadata/{item['id']}")[1])
            mp4 = [f for f in meta.get("files", []) if str(f.get("name", "")).lower().endswith(".mp4")]
            item["mp4"] = len(mp4)
            if mp4:
                item["segundos"] = mp4[0].get("length")
                item["descarga"] = probar_descarga(f"https://archive.org/download/{item['id']}/"
                                                   + urllib.parse.quote(mp4[0]["name"]))
        except Exception as e:
            item["error"] = f"{type(e).__name__}: {str(e)[:80]}"
    return salida


def peertube():
    vistos, salida = set(), []
    for q in BUSQUEDAS:
        url = ("https://sepiasearch.org/api/v1/search/videos?" + urllib.parse.urlencode(
            {"search": q, "count": 50, "licenceOneOf": [1, 2, 7]}, doseq=True))
        try:
            datos = json.loads(pedir(url)[1]).get("data", [])
        except Exception as e:
            salida.append({"busqueda": q, "error": f"{type(e).__name__}: {str(e)[:80]}"})
            continue
        for v in datos:
            clave = v.get("uuid")
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append({"uuid": clave, "titulo": str(v.get("name"))[:120], "licencia": (v.get("licence") or {}).get("label"),
                           "segundos": v.get("duration"), "instancia": (v.get("account") or {}).get("host"),
                           "url": v.get("url"), "busqueda": q})
    for item in [x for x in salida if x.get("uuid")][:5]:      # ¿deja bajar el archivo?
        try:
            datos = json.loads(pedir(f"https://{item['instancia']}/api/v1/videos/{item['uuid']}")[1])
            item["descarga_permitida"] = datos.get("downloadEnabled")
            archivos = datos.get("files") or [f for p in datos.get("streamingPlaylists") or [] for f in p.get("files") or []]
            enlaces = [f.get("fileDownloadUrl") or f.get("fileUrl") for f in archivos if f.get("fileDownloadUrl") or f.get("fileUrl")]
            if enlaces and datos.get("downloadEnabled", True):
                item["descarga"] = probar_descarga(enlaces[-1])
        except Exception as e:
            item["error"] = f"{type(e).__name__}: {str(e)[:80]}"
    return salida


def commons():
    salida = []
    for q in ["GTA", "Grand Theft Auto"]:
        url = ("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "list": "search", "srsearch": f"{q} filetype:video", "srnamespace": 6, "srlimit": 50,
             "format": "json"}))
        try:
            for r in json.loads(pedir(url)[1]).get("query", {}).get("search", []):
                salida.append({"titulo": r.get("title"), "busqueda": q})
        except Exception as e:
            salida.append({"busqueda": q, "error": f"{type(e).__name__}: {str(e)[:80]}"})
    return salida


def main():
    resultado = {"fecha": privado.ahora(), "archive_org": archivo_org(), "peertube": peertube(), "commons": commons()}
    privado.guardar_estado("clips/fuentes_libres.json", resultado)
    for sitio in ("archive_org", "peertube", "commons"):
        items = [x for x in resultado[sitio] if not x.get("error")]
        errores = [x for x in resultado[sitio] if x.get("error")]
        bajan = [x for x in items if (x.get("descarga") or {}).get("ok")]
        seis = [x for x in items if any(k in str(x.get("titulo", "")).upper() for k in ("GTA 6", "GTA VI", "GTA6"))]
        print(f"{sitio}: {len(items)} vídeos con licencia libre ({len(seis)} de GTA 6); "
              f"{len(bajan)} de 5 probados se bajan; {len(errores)} errores", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
