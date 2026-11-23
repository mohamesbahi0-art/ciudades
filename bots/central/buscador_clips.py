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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dias", type=int, default=30)
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
    privado.guardar_estado("clips/candidatos.json", {"busquedas": BUSQUEDAS, "desde": desde, "licencia": "CC BY",
                                                     "candidatos": candidatos})
    cuaderno = privado.cuaderno("buscador_clips")
    cuaderno.apuntar("busqueda", {"encontrados": len(candidatos), "dias": a.dias})
    cuaderno.guardar()
    largos = sum(1 for c in candidatos if c["segundos"] >= 120)
    print(f"buscador de clips: {len(candidatos)} vídeos con licencia Creative Commons ({largos} de más de 2 minutos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
