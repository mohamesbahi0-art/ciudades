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
from bots.central.videoteca import ETIQUETAS, juego_de  # noqa: E402

# (búsqueda, días hacia atrás): de GTA 6, lo último; de GTA 5 vale todo el año (para las tomas de GTA 5 contra GTA 6)
BUSQUEDAS = [("GTA 6", 30), ("GTA VI gameplay", 30), ("GTA 6 momentos", 30), ("GTA 5 gameplay", 365),
             ("GTA V gameplay 4K", 365)]


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
REGLA DE ORO: del creador solo se pone su nombre en la descripción. En los trozos que elijas NO puede verse ni oírse NADA
suyo: ni su cara, ni su webcam, ni su nombre, logo o marca de agua, ni sus textos, flechas o animaciones (suscríbete,
redes), ni intros, anuncios o pantallas de espera. Solo el juego. Si en un trozo sale algo suyo, NO lo elijas.
Busca dos cosas:
1. «momentos»: como mucho {n} trozos de 8 a 35 segundos que de verdad se harían virales solos (si no hay ninguno así, no
   devuelvas ninguno). Para cada uno, el canal: "clips" (algo gracioso, épico o increíble), "curios" (un detalle o
   secreto que casi nadie sabe) o "versus" (algo que se puede comparar entre GTA 5 y GTA 6).
2. «tomas»: como mucho 4 trozos de 6 a 25 segundos de juego limpio que enseñen claramente UNA cosa, para ilustrar otros
   vídeos (lo que se ve tiene que ser lo que dice la voz). Di de qué juego es ("gta5" o "gta6"; de GTA 5, solo el juego
   original, sin mods que cambien los gráficos) y de 1 a 3 etiquetas de esta lista: {etiquetas}.
   Prefiere cosas que se puedan comparar entre GTA 5 y GTA 6 (agua, coches, policía, explosiones, físicas, gráficos...).
Devuelve SOLO un JSON: {{"momentos": [{{"desde": 0, "hasta": 0, "para": "clips|curios|versus", "que_pasa": "una frase",
"por_que_engancha": "una frase", "sale_creador": "no | sí (qué y dónde)", "habla_creador": "no | sí",
"gancho": "texto de 2 a 5 palabras para el principio", "nota": 0}}],
"tomas": [{{"desde": 0, "hasta": 0, "juego": "gta5|gta6", "etiquetas": ["..."], "que_se_ve": "una frase",
"sale_creador": "no | sí (qué y dónde)", "habla_creador": "no | sí", "calidad": 0}}]}}
(nota de 0 a 100: cuánto se haría viral, solo valen los de {minima} o más; calidad de 0 a 100: lo bien que se ve y lo
claro que enseña su etiqueta, solo valen las de {toma_minima} o más)"""

TOMA_MINIMA = 80     # las tomas son ingredientes: tienen que verse bien y enseñar claro su etiqueta


def _numero(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def limpio(m, toma=False):
    """Un momento (o una toma) vale si no sale nada del creador y llega a su nota mínima."""
    sale = str(m.get("sale_creador", m.get("sale_youtuber", ""))).strip().lower()
    if toma:
        return sale.startswith("no") and _numero(m.get("calidad", m.get("nota"))) >= TOMA_MINIMA
    return sale.startswith("no") and _numero(m.get("nota")) >= MINIMA


def prioridades(lista):
    """Qué grabar primero: los momentos de 90 o más; luego las tomas que completan una pareja GTA 5 / GTA 6 o traen
    algo que la videoteca no tiene; luego lo demás."""
    from bots.central import videoteca
    hay = {(t.get("juego"), e) for t in videoteca.tomas() for e in t.get("etiquetas") or []}
    for m in lista:
        if m.get("estado") != "por_grabar":
            continue
        if m.get("tipo") != "toma":
            m["prioridad"] = 1
            continue
        otro = "gta5" if m.get("juego") == "gta6" else "gta6"
        etiquetas = m.get("etiquetas") or []
        if any((m.get("juego"), e) not in hay and (otro, e) in hay for e in etiquetas):
            m["prioridad"] = 2                  # completa una pareja para el versus
        elif any((m.get("juego"), e) not in hay for e in etiquetas):
            m["prioridad"] = 3                  # algo que la videoteca todavía no tiene
        else:
            m["prioridad"] = 4
    return lista


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
    # mitad GTA 6 y mitad GTA 5 (para las parejas del versus), y dentro de cada uno los más famosos primero
    orden = sorted(candidatos, key=lambda c: (c["suscriptores_creador"], c["visitas"]), reverse=True)
    seis = [c for c in orden if juego_de({"titulo_original": c["titulo"]}) == "gta6"]
    cinco = [c for c in orden if juego_de({"titulo_original": c["titulo"]}) == "gta5"]
    mezcla = [c for par in zip(seis, cinco) for c in par] + seis[len(cinco):] + cinco[len(seis):]
    for c in mezcla:
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
                                   VER.format(n=2 if c["segundos"] < 90 else 3, minima=MINIMA, toma_minima=TOMA_MINIMA,
                                              etiquetas=", ".join(ETIQUETAS)))
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
                          "juego": juego_de({"titulo_original": c["titulo"], "que_pasa": m.get("que_pasa", "")}),
                          "tipo": "momento", "estado": "por_grabar", "elegido": privado.ahora()})
        for t in (r or {}).get("tomas", []) if isinstance(r, dict) else []:
            try:
                desde, hasta = float(t["desde"]), float(t["hasta"])
            except (KeyError, TypeError, ValueError):
                continue
            if not 4 <= hasta - desde <= 30 or hasta > c["segundos"] + 1 or not limpio(t, toma=True):
                continue
            juego = str(t.get("juego") or "").lower().replace(" ", "")
            numero += 1
            lista.append({"codigo": f"C-{numero:03d}", "video": c["id"], "creador": c["canal"],
                          "suscriptores_creador": c["suscriptores_creador"], "titulo_original": c["titulo"],
                          "enlace": f"https://youtu.be/{c['id']}?t={int(desde)}", "desde": desde, "hasta": hasta,
                          "para": "videoteca", "tipo": "toma",
                          "juego": juego if juego in ("gta5", "gta6") else juego_de({"titulo_original": c["titulo"]}),
                          "etiquetas": [e for e in t.get("etiquetas") or [] if e in ETIQUETAS][:3] or ["ciudad"],
                          "que_pasa": t.get("que_se_ve", ""), "sale_creador": "no",
                          "habla_creador": str(t.get("habla_creador", "")).lower().startswith("s"),
                          "nota": t.get("calidad"), "licencia": "CC BY", "estado": "por_grabar",
                          "elegido": privado.ahora()})
    prioridades(lista)
    lista.sort(key=lambda m: (m["estado"] != "por_grabar", m.get("prioridad") or 9, -_numero(m.get("nota"))))
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
    ahora = dt.datetime.now(dt.timezone.utc)
    desde = (ahora - dt.timedelta(days=a.dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = []
    for q, dias in BUSQUEDAS:
        hace = (ahora - dt.timedelta(days=max(dias, a.dias))).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = yt.search().list(part="id", q=q, type="video", videoLicense="creativeCommon", order="viewCount",
                             publishedAfter=hace, maxResults=50).execute()
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
    privado.guardar_estado("clips/candidatos.json", {"busquedas": [q for q, _ in BUSQUEDAS], "desde": desde, "licencia": "CC BY",
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
