"""El Buscador de clips: busca con la API oficial de YouTube vídeos de GTA con licencia Creative Commons (CC BY), los
únicos de otros creadores que se pueden reutilizar sin pedir permiso, siempre que se diga de quién son. Solo busca y
apunta: no descarga nada (YouTube no deja descargar desde los servidores de GitHub, y eso no se salta).

Gasta 100 unidades de cuota por búsqueda, así que no corre en bucle. Deja la lista en estado/clips/candidatos.json del
repositorio privado.

Uso:  python bots/central/buscador_clips.py [--dias 30]
"""
import argparse
import datetime as dt
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import privado  # noqa: E402

BUSQUEDAS = ["GTA 6", "GTA VI gameplay", "GTA 6 momentos"]


def servicio():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    for clave in ("CLIPS", "GTA", "CURIOS", "VERSUS", "TERROR"):
        refresh = os.environ.get(f"YT_REFRESH_{clave}")
        if refresh:
            cred = Credentials(None, refresh_token=refresh, client_id=os.environ["YT_CLIENT_ID"],
                               client_secret=os.environ["YT_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
            return build("youtube", "v3", credentials=cred, cache_discovery=False)
    raise SystemExit("No hay ningún canal conectado para buscar.")


def segundos(iso):
    m = re.fullmatch(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 0


MINIMA = 90          # solo los momentos que de verdad merecen la pena (la misma nota que pide el dueño para publicar)

VER = """Mira este vídeo de GTA (tiene licencia Creative Commons: se puede reutilizar diciendo de quién es).
Busca como mucho {n} momentos para Shorts de 8 a 35 segundos, pero SOLO los que de verdad se harían virales: si el vídeo
no tiene ninguno así, no devuelvas ninguno. Para cada uno, piensa en qué canal encaja:
- "clips": un momento gracioso, épico o increíble del juego;
- "curios": un detalle o secreto de GTA 6 que casi nadie sabe;
- "versus": una comparación entre GTA 5 y GTA 6.
REGLA DE ORO: del creador solo se pone su nombre en la descripción. En el trozo elegido NO puede verse ni oírse NADA suyo:
ni su cara, ni su webcam, ni su nombre, logo o marca de agua, ni sus textos, flechas o animaciones (suscríbete, redes),
ni intros, anuncios o pantallas de espera. Solo el juego. Si en ese trozo sale algo suyo, NO lo elijas.
Devuelve SOLO un JSON: {{"momentos": [{{"desde": 0, "hasta": 0, "para": "clips|curios|versus", "que_pasa": "una frase",
"por_que_engancha": "una frase", "sale_creador": "no | sí (qué y dónde)", "habla_creador": "no | sí",
"gancho": "texto de 2 a 5 palabras para el principio", "nota": 0}}]}}  (nota de 0 a 100: cuánto se haría viral; solo
valen los de {minima} o más)"""


def limpio(m):
    """Un momento vale si no sale nada del creador y llega a la nota mínima."""
    sale = str(m.get("sale_creador", m.get("sale_youtuber", ""))).strip().lower()
    try:
        nota = float(m.get("nota") or 0)
    except (TypeError, ValueError):
        nota = 0
    return sale.startswith("no") and nota >= MINIMA


def ver_y_elegir(candidatos, cuantos=6):
    """Gemini «ve» por su enlace los vídeos de los creadores más famosos y elige los mejores momentos (no se descarga
    nada): solo los de 90 o más y donde no sale nada del creador (ni cara, ni webcam, ni nombre, ni logo). Deja la lista
    en estado/clips/para_grabar.json; el dueño los graba con el móvil y los sube en la app."""
    from bots.comun import gemini
    anterior = privado.leer(os.path.join("estado", "clips", "para_grabar.json"), {}) or {}
    lista = anterior.get("momentos", [])
    vistos = {m["video"] for m in lista}
    # 2 vídeos como mucho por creador, los creadores con más suscriptores primero, vídeos de 20 s a 20 min
    por_creador, elegidos = {}, []
    for c in sorted(candidatos, key=lambda c: (c["suscriptores_creador"], c["visitas"]), reverse=True):
        if c["id"] in vistos or not 20 <= c["segundos"] <= 1200 or por_creador.get(c["canal_id"], 0) >= 2:
            continue
        por_creador[c["canal_id"]] = por_creador.get(c["canal_id"], 0) + 1
        elegidos.append(c)
        if len(elegidos) >= cuantos:
            break
    numero = max([int(m["codigo"][2:]) for m in lista] + [0])
    for c in elegidos:
        try:
            r = gemini.ver_youtube(f"https://www.youtube.com/watch?v={c['id']}",
                                   VER.format(n=2 if c["segundos"] < 90 else 3, minima=MINIMA))
        except gemini.SinIA:            # ningún modelo ha podido verlo hoy: el siguiente vídeo
            r = None
        for m in (r or {}).get("momentos", []) if isinstance(r, dict) else []:
            try:
                desde, hasta = float(m["desde"]), float(m["hasta"])
            except (KeyError, TypeError, ValueError):
                continue
            if not 5 <= hasta - desde <= 45 or hasta > c["segundos"] + 1 or not limpio(m):
                continue        # sale algo del creador o no llega a la nota: no se graba
            numero += 1
            lista.append({"codigo": f"C-{numero:03d}", "video": c["id"], "creador": c["canal"],
                          "suscriptores_creador": c["suscriptores_creador"], "titulo_original": c["titulo"],
                          "enlace": f"https://youtu.be/{c['id']}?t={int(desde)}", "desde": desde, "hasta": hasta,
                          "para": m.get("para", "clips"), "que_pasa": m.get("que_pasa", ""),
                          "por_que": m.get("por_que_engancha", ""), "sale_creador": "no",
                          "habla_creador": str(m.get("habla_creador", "")).lower().startswith("s"),
                          "gancho": m.get("gancho", ""), "nota": m.get("nota"), "licencia": "CC BY",
                          "estado": "por_grabar", "elegido": privado.ahora()})
    lista.sort(key=lambda m: (m["estado"] != "por_grabar", -(m.get("nota") or 0)))
    privado.guardar_estado("clips/para_grabar.json", {"momentos": lista})
    c = privado.cuaderno("buscador_clips")
    c.apuntar("momentos", {"vistos": len(elegidos), "momentos": len(lista) - len(anterior.get("momentos", []))})
    c.guardar()
    gemini.apuntar_portero()
    return lista


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dias", type=int, default=30)
    p.add_argument("--videos", type=int, default=6, help="cuántos vídeos ve Gemini en esta pasada")
    p.add_argument("--sin-ver", action="store_true", help="solo busca, sin que Gemini vea los vídeos")
    a = p.parse_args()
    yt = servicio()
    desde = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = []
    for q in BUSQUEDAS:
        r = yt.search().list(part="id", q=q, type="video", videoLicense="creativeCommon", order="viewCount",
                             publishedAfter=desde, maxResults=50).execute()
        ids += [x["id"]["videoId"] for x in r.get("items", []) if x["id"]["videoId"] not in ids]
    candidatos = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(id=",".join(ids[i:i + 50]), part="snippet,contentDetails,status,statistics").execute()
        for v in r.get("items", []):
            if v["status"].get("license") != "creativeCommon":
                continue
            candidatos.append({"id": v["id"], "url": f"https://youtu.be/{v['id']}", "titulo": v["snippet"]["title"],
                               "canal": v["snippet"]["channelTitle"], "canal_id": v["snippet"]["channelId"],
                               "publicado": v["snippet"]["publishedAt"], "segundos": segundos(v["contentDetails"]["duration"]),
                               "visitas": int(v.get("statistics", {}).get("viewCount", 0)),
                               "idioma": v["snippet"].get("defaultAudioLanguage") or v["snippet"].get("defaultLanguage")})
    candidatos.sort(key=lambda c: c["visitas"], reverse=True)
    # Los creadores más famosos primero (por suscriptores)
    canales = sorted({c["canal_id"] for c in candidatos})
    subs = {}
    for i in range(0, len(canales), 50):
        r = yt.channels().list(id=",".join(canales[i:i + 50]), part="statistics").execute()
        subs.update({x["id"]: int(x["statistics"].get("subscriberCount", 0)) for x in r.get("items", [])})
    for c in candidatos:
        c["suscriptores_creador"] = subs.get(c["canal_id"], 0)
    privado.guardar_estado("clips/candidatos.json", {"busquedas": BUSQUEDAS, "desde": desde, "licencia": "CC BY",
                                                     "candidatos": candidatos})
    if not a.sin_ver:
        momentos = ver_y_elegir(candidatos, a.videos)
        print(f"buscador de clips: {len(momentos)} momentos elegidos para grabar")
    cuaderno = privado.cuaderno("buscador_clips")
    cuaderno.apuntar("busqueda", {"encontrados": len(candidatos), "dias": a.dias})
    cuaderno.guardar()
    largos = sum(1 for c in candidatos if c["segundos"] >= 120)
    print(f"buscador de clips: {len(candidatos)} vídeos con licencia Creative Commons ({largos} de más de 2 minutos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
