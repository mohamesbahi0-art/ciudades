"""El Recolector de clips: trae solo, sin que el dueño grabe ni suba nada, clips de GTA 5 y GTA 6 con licencia libre de
Internet Archive (archive.org). Es la biblioteca de internet y deja bajar sus vídeos a cualquiera, también a los robots:
no se salta nada.

Solo licencias que valen para un Short de YouTube: CC BY (nombrando al autor) y CC0 (dominio público). No valen las que
prohíben usos comerciales (NC) o cambios (ND), ni las que obligan a publicar con la misma licencia (SA). Tampoco la
«marca de dominio público», que a veces se pone a vídeos de otros. Fuera también los vídeos filtrados, los tráileres y
las charlas.

Cada día:
1. Busca vídeos nuevos de GTA 5 y GTA 6 con esas licencias.
2. Mira unas muestras de cada vídeo con la IA, sin bajarlo entero: el trozo justo se pide al servidor. Encuentra tomas
   de juego limpio (6 a 25 s, con su juego y sus etiquetas) y momentos virales (90 o más).
3. Corta cada una y la limpia como el Portero de clips: sin bandas, sin lo que no sea juego y sin la voz del creador.
   Después la guarda en la Videoteca con su crédito (autor, enlace y licencia). Los momentos virales quedan listos para
   su propio Short.

Uso:  python bots/central/recolector.py [--maximo 3]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from bots.central import clips, videoteca  # noqa: E402
from bots.comun import almacen, gemini, privado  # noqa: E402

ESTADO = os.path.join("estado", "clips", "recolector.json")
AGENTE = {"User-Agent": "ciudades-recolector/1.0 (clips con licencia libre)"}
BUSQUEDA = ('(title:(GTA) OR title:("grand theft auto")) AND mediatype:movies AND '
            '(licenseurl:*creativecommons.org/licenses/by/* OR licenseurl:*publicdomain/zero*)')
FUERA = re.compile(r"leak|filtra|s[ıi]zd[ıi]r|trailer|tr[áa]iler|podcast|fridman|reacci|reaction|minecraft|roblox|"
                   r"san andreas|stories|gta\s*(2|3|iv|4)\b|london 1969|advert|anuncio", re.I)
MUESTRA, MUESTRAS = 60, 4          # cuánto mira la IA de cada vídeo largo (en trozos)
TOMAS_POR_VIDEO = 5
NOTA_MOMENTO, CALIDAD_TOMA = 90, 80
TOPE_VIDEOTECA = 600               # con tantas tomas ya hay para muchos vídeos: deja de recoger (la estantería no crece sin fin)

VER = """Eres el Recolector de clips de una fábrica de Shorts de GTA. Este es un trozo de {segundos} segundos de un vídeo
con licencia libre ({licencia}) titulado «{titulo}». Busca dentro:
1. «tomas»: trozos de 6 a 25 segundos de juego limpio de GTA 5 o GTA 6 que enseñen claramente UNA cosa, para ilustrar
   otros vídeos. De 1 a 3 etiquetas de esta lista: {etiquetas}.
2. «momentos»: solo si hay algo que de verdad se haría viral solo (gracioso, épico, increíble o un secreto que casi
   nadie sabe), de 90 o más, con su canal: "clips", "curios" o "versus".
REGLA DE ORO: del creador solo se pone su nombre en la descripción. En lo que elijas NO puede verse ni oírse NADA suyo:
ni su cara, ni su webcam, ni su nombre, logo o marca de agua, ni sus textos o animaciones, ni su voz comentando. Tampoco
anuncios, intros o pantallas de espera. Solo el juego. Si algo de eso está pegado a un borde, da un «recorte» que lo
quite (x, y, ancho y alto, de 0 a 1). Si no se puede quitar, no lo elijas. Nada que parezca un tráiler oficial o
material filtrado.
Los tiempos van en segundos desde el principio de ESTE trozo. Si el trozo no es de GTA 5 ni de GTA 6, pon
"juego_principal": "otro" y deja las listas vacías.
Devuelve SOLO un JSON: {{"juego_principal": "gta5|gta6|otro",
"tomas": [{{"desde": 0, "hasta": 0, "juego": "gta5|gta6", "etiquetas": ["..."], "que_se_ve": "una frase",
"habla_creador": false, "recorte": null, "calidad": 0}}],
"momentos": [{{"desde": 0, "hasta": 0, "para": "clips|curios|versus", "juego": "gta5|gta6", "que_pasa": "una frase",
"por_que": "una frase", "gancho": "de 2 a 5 palabras", "habla_creador": false, "recorte": null, "nota": 0}}]}}
(calidad de 0 a 100: lo bien que se ve y lo claro que enseña su etiqueta; nota de 0 a 100: cuánto se haría viral)"""


def _pedir(url, espera=60):
    req = urllib.request.Request(url, headers=AGENTE)
    with urllib.request.urlopen(req, timeout=espera) as r:
        return json.loads(r.read())


def url_de(identificador, nombre):
    return f"https://archive.org/download/{identificador}/" + urllib.parse.quote(nombre)


def licencia(url):
    u = str(url or "").lower()
    if re.search(r"/licenses/by/\d", u):
        return "CC BY"
    if "publicdomain/zero" in u:
        return "CC0"
    return None


def _num(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _segundos_de(valor):
    try:
        if isinstance(valor, str) and ":" in valor:
            total = 0.0
            for parte in valor.split(":"):
                total = total * 60 + float(parte)
            return total
        return float(valor or 0)
    except ValueError:
        return 0.0


def _estado():
    return privado.leer(ESTADO, {}) or {}


def buscar(paginas=2):
    """Los vídeos de GTA con licencia que vale, sin los que no convienen (filtraciones, tráileres, charlas...)."""
    docs = []
    for pagina in range(1, paginas + 1):
        url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(
            {"q": BUSQUEDA, "fl[]": ["identifier", "title", "licenseurl", "creator", "downloads"], "rows": 100,
             "page": pagina, "sort[]": "downloads desc", "output": "json"}, doseq=True)
        lote = _pedir(url).get("response", {}).get("docs", [])
        docs += lote
        if len(lote) < 100:
            break
    return [d for d in docs if licencia(d.get("licenseurl")) and not FUERA.search(str(d.get("title") or ""))]


def elegir_archivo(meta):
    archivos = [f for f in meta.get("files", []) if re.search(r"\.(mp4|webm|mkv|mov)$", str(f.get("name", "")), re.I)]
    if not archivos:
        return None

    def puntos(f):
        alto = int(_num(f.get("height")))
        return (str(f.get("name", "")).lower().endswith(".mp4"), 0 < alto <= 1080, alto, -int(_num(f.get("size"))))
    return max(archivos, key=puntos)


def _siguiente_id(estado):
    estado["contador"] = int(estado.get("contador") or 0) + 1
    return f"A-{estado['contador']:03d}"


def _cortar(url, desde, segundos, salida):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{desde:.2f}", "-i", url, "-t", f"{segundos:.2f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-b:a", "128k", salida], check=True, capture_output=True, timeout=900)
    return salida


def _guardar(estado, url, inicio, x, origen, tmp, momento=False):
    """Corta el trozo, lo limpia como el Portero y lo deja en la Videoteca (y, si es un momento, listo para su Short)."""
    desde, hasta = _num(x.get("desde")), _num(x.get("hasta"))
    if not 4 <= hasta - desde <= 35:
        return None
    nuevo = _siguiente_id(estado)
    crudo = _cortar(url, inicio + desde, hasta - desde, os.path.join(tmp, f"{nuevo}-crudo.mp4"))
    rev = {"bandas": clips.bandas(crudo), "recorte": clips._recorte_valido(x.get("recorte")),
           "sonido": x.get("habla_creador") is False and clips._tiene_audio(crudo)}
    limpio = videoteca.limpiar(crudo, rev, os.path.join(tmp, f"{nuevo}.mp4"))
    almacen.guardar(videoteca.ESTANTERIA, limpio, f"{nuevo}.mp4")
    juego = x.get("juego") if x.get("juego") in videoteca.JUEGOS else origen["juego"]
    que = str(x.get("que_se_ve") or x.get("que_pasa") or "")[:300]
    toma = {"id": nuevo, "archivo": f"{nuevo}.mp4", "juego": juego,
            "etiquetas": videoteca.etiquetas_de({"etiquetas": x.get("etiquetas") or [], "que_se_ve": que}),
            "que_se_ve": que, "segundos": round(clips._segundos(limpio), 1), "sonido": bool(rev["sonido"]),
            "creador": origen["creador"], "enlace": origen["enlace"], "licencia": origen["licencia"],
            "calidad": _num(x.get("nota") if momento else x.get("calidad")), "origen": "archive.org",
            "fuente": origen["fuente"], "entrada": privado.ahora(), "usos": 0}
    lista = videoteca.tomas() + [toma]
    videoteca._guardar(lista)
    if momento:
        clips.añadir({"codigo": nuevo, "tipo": "momento", "para": x.get("para") if x.get("para") in ("clips", "curios",
                      "versus") else "clips", "estado": "grabado", "en_videoteca": True, "archivo": f"{nuevo}.mp4",
                      "creador": origen["creador"], "enlace": origen["enlace"], "licencia": origen["licencia"],
                      "titulo_original": origen["titulo"], "que_pasa": x.get("que_pasa", ""), "por_que": x.get("por_que", ""),
                      "gancho": x.get("gancho", ""), "nota": _num(x.get("nota")), "juego": juego, "sale_creador": "no",
                      "origen": "archive.org", "elegido": privado.ahora(), "grabadoEl": privado.ahora()})
    return nuevo


def recoger_video(doc, estado, tmp, paso=print):
    ident = doc["identifier"]
    meta = _pedir(f"https://archive.org/metadata/{ident}")
    archivo = elegir_archivo(meta)
    if not archivo:
        return {"resultado": "sin vídeo"}
    url = url_de(ident, archivo["name"])
    total = _segundos_de(archivo.get("length")) or clips._segundos(url)
    if total < 6:
        return {"resultado": "demasiado corto"}
    info = meta.get("metadata") or {}
    creador = info.get("creator") or doc.get("creator") or info.get("uploader") or "?"
    creador = creador[0] if isinstance(creador, list) else creador
    lic = licencia(info.get("licenseurl") or doc.get("licenseurl"))
    if not lic:
        return {"resultado": "licencia que no vale"}
    titulo = str(info.get("title") or doc.get("title") or "")[:150]
    origen = {"creador": str(creador)[:80], "licencia": lic, "titulo": titulo,
              "enlace": info.get("originalurl") or f"https://archive.org/details/{ident}",
              "fuente": f"https://archive.org/details/{ident}",
              "juego": videoteca.juego_de({"titulo_original": titulo})}
    if total <= MUESTRA * 1.5:
        trozos = [(0.0, total)]
    else:
        trozos = [(min(total * f, total - MUESTRA), MUESTRA) for f in (0.15, 0.4, 0.65, 0.88)][:MUESTRAS]
    hecho = {"tomas": [], "momentos": []}
    for k, (inicio, dur) in enumerate(trozos):
        muestra = os.path.join(tmp, f"muestra{k}.mp4")
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{inicio:.1f}", "-i", url, "-t", f"{dur:.1f}",
                            "-vf", "scale=-2:480", "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-c:a", "aac",
                            "-b:a", "48k", "-ac", "1", muestra], capture_output=True, timeout=900)
        if r.returncode != 0 or not os.path.exists(muestra) or os.path.getsize(muestra) > gemini.VIDEO_MAXIMO:
            continue
        v = gemini.preguntar(VER.format(segundos=round(dur), licencia=lic, titulo=titulo,
                                        etiquetas=", ".join(videoteca.ETIQUETAS)), video=muestra, temperatura=0.3)
        if not isinstance(v, dict):
            continue
        if v.get("juego_principal") == "otro":
            break                                        # no es de GTA 5 ni de GTA 6
        for t in sorted(v.get("tomas") or [], key=lambda t: -_num(t.get("calidad"))):
            if len(hecho["tomas"]) >= TOMAS_POR_VIDEO:
                break
            if _num(t.get("calidad")) >= CALIDAD_TOMA:
                nuevo = _guardar(estado, url, inicio, t, origen, tmp)
                if nuevo:
                    hecho["tomas"].append(nuevo)
        for m in v.get("momentos") or []:
            if _num(m.get("nota")) >= NOTA_MOMENTO:
                es_momento = m.get("para") in ("clips", "curios")      # lo de versus va a la videoteca (por parejas)
                nuevo = _guardar(estado, url, inicio, m, origen, tmp, momento=es_momento)
                if nuevo:
                    hecho["momentos" if es_momento else "tomas"].append(nuevo)
    return {"resultado": "hecho", **hecho}


def recoger(maximo=3, paso=print):
    """Mira hasta `maximo` vídeos nuevos. Devuelve cuántas tomas y momentos ha traído."""
    if len(videoteca.tomas()) >= TOPE_VIDEOTECA:
        paso(f"recolector: la videoteca ya tiene {TOPE_VIDEOTECA} tomas o más; hoy no recoge")
        return {"tomas": 0, "momentos": 0, "vistos": 0}
    estado = _estado()
    vistos = estado.setdefault("vistos", {})
    nuevos = [d for d in buscar() if d["identifier"] not in vistos or
              (vistos[d["identifier"]].get("resultado") == "error" and int(vistos[d["identifier"]].get("fallos") or 0) < 3)]
    traidas = {"tomas": 0, "momentos": 0, "vistos": 0}
    cuaderno = privado.cuaderno("recolector_clips")
    for doc in nuevos[:maximo]:
        tmp = tempfile.mkdtemp(prefix="recolector-")
        ident = doc["identifier"]
        try:
            r = recoger_video(doc, estado, tmp, paso)
        except gemini.SinIA:
            paso("recolector: la IA no contesta; lo demás, mañana")
            break
        except Exception as e:
            antes = vistos.get(ident) or {}
            r = {"resultado": "error", "fallos": int(antes.get("fallos") or 0) + 1, "error": f"{type(e).__name__}"}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        vistos[ident] = dict(r, fecha=privado.ahora())
        traidas["vistos"] += 1
        traidas["tomas"] += len(r.get("tomas") or [])
        traidas["momentos"] += len(r.get("momentos") or [])
        privado.guardar_estado("clips/recolector.json", estado)
        paso(f"recolector: un vídeo mirado ({r['resultado']}): {len(r.get('tomas') or [])} tomas y "
             f"{len(r.get('momentos') or [])} momentos")
    estado["ultimo"] = privado.ahora()
    estado["pendientes"] = max(0, len(nuevos) - traidas["vistos"])
    privado.guardar_estado("clips/recolector.json", estado)
    cuaderno.apuntar("ronda", traidas)
    cuaderno.guardar()
    gemini.apuntar_portero()
    return traidas


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--maximo", type=int, default=3, help="vídeos nuevos que mira en esta pasada")
    a = p.parse_args()
    t = recoger(a.maximo)
    print(f"recolector: {t['vistos']} vídeos mirados, {t['tomas']} tomas y {t['momentos']} momentos nuevos en la videoteca")
    return 0


if __name__ == "__main__":
    sys.exit(main())
