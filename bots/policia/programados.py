"""Los Jefes de canal: miran en YouTube qué tiene cada canal, sin tocar nada.
Para cada canal conectado: suscriptores, último vídeo publicado (con sus visitas), vídeos ya programados (los que salen
solos a su hora, por ejemplo los que dejó la fábrica antigua), cuántos salen en las próximas 24 horas y hasta qué día
hay vídeos. Lo deja en estado/canales/<clave>.json del repositorio privado y lo apunta en el cuaderno de jefes_canal.
Gasta muy poca cuota (unas 3-5 unidades por canal).

Uso:  python bots/policia/programados.py [--canal gta]
Secretos: YT_CLIENT_ID, YT_CLIENT_SECRET y, por canal, YT_REFRESH_<CANAL> y YT_ID_<CANAL>.
"""
import argparse
import datetime as dt
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import privado  # noqa: E402


def servicio(clave):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    cred = Credentials(None, refresh_token=os.environ[f"YT_REFRESH_{clave.upper()}"], client_id=os.environ["YT_CLIENT_ID"],
                       client_secret=os.environ["YT_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
    return build("youtube", "v3", credentials=cred, cache_discovery=False)


def fecha(texto):
    return dt.datetime.fromisoformat(texto.replace("Z", "+00:00")) if texto else None


def revisar(clave, cfg):
    yt = servicio(clave)
    canal = yt.channels().list(part="snippet,contentDetails,statistics", mine=True).execute()["items"][0]
    esperado = os.environ.get(f"YT_ID_{clave.upper()}")
    if esperado and canal["id"] != esperado:
        return {"canal": clave, "error": "el permiso es de otro canal"}
    subidas = canal["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, pagina = [], None
    for _ in range(4):                                   # los 200 vídeos más recientes como mucho
        r = yt.playlistItems().list(playlistId=subidas, part="contentDetails", maxResults=50, pageToken=pagina).execute()
        ids += [x["contentDetails"]["videoId"] for x in r.get("items", [])]
        pagina = r.get("nextPageToken")
        if not pagina:
            break
    videos = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(id=",".join(ids[i:i + 50]), part="snippet,status,statistics").execute()
        videos += r.get("items", [])
    ahora = dt.datetime.now(dt.timezone.utc)
    programados, publicados = [], []
    for v in videos:
        st, sn = v["status"], v["snippet"]
        sale = fecha(st.get("publishAt"))
        if st.get("privacyStatus") == "private" and sale and sale > ahora:
            programados.append({"titulo": sn["title"], "sale": sale.strftime("%Y-%m-%dT%H:%M:%SZ"), "id": v["id"]})
        elif st.get("privacyStatus") == "public":
            est = v.get("statistics", {})
            publicados.append({"titulo": sn["title"], "publicado": sn["publishedAt"], "id": v["id"],
                               "url": f"https://youtu.be/{v['id']}", "visitas": int(est.get("viewCount", 0)),
                               "megusta": int(est.get("likeCount", 0)), "comentarios": int(est.get("commentCount", 0))})
    programados.sort(key=lambda x: x["sale"])
    publicados.sort(key=lambda x: x["publicado"], reverse=True)
    en_24h = [p for p in programados if fecha(p["sale"]) <= ahora + dt.timedelta(hours=24)]
    stats = canal.get("statistics", {})
    return {"canal": clave, "nombre": cfg["nombre"], "suscriptores": int(stats.get("subscriberCount", 0)),
            "visitas_totales": int(stats.get("viewCount", 0)), "videos_totales": int(stats.get("videoCount", 0)),
            "programados": programados, "programados24h": len(en_24h),
            "hasta": programados[-1]["sale"] if programados else None,
            "ultimo_publicado": publicados[0] if publicados else None,
            "publicados_7_dias": sum(1 for p in publicados if fecha(p["publicado"]) > ahora - dt.timedelta(days=7)),
            "recientes": publicados[:40]}


def apuntar_historial(clave, r):
    """Una foto de las cifras del canal cada vez que se revisa: con ellas la Analista ve cómo crece."""
    ruta = os.path.join("estado", "historial", f"{clave}.json")
    fotos = privado.leer(ruta, []) or []
    fotos.append({"fecha": privado.ahora(), "suscriptores": r.get("suscriptores"), "visitas": r.get("visitas_totales"),
                  "videos": r.get("videos_totales")})
    privado.escribir(ruta, fotos[-400:])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--canal")
    a = p.parse_args()
    with open(os.path.join(privado.carpeta(), "config", "canales.json"), encoding="utf-8") as f:
        canales = json.load(f)["canales"]
    jefes = privado.cuaderno("jefes_canal")
    resumen, fallos = {}, 0
    for clave, cfg in canales.items():
        if a.canal and clave != a.canal:
            continue
        if not os.environ.get(f"YT_REFRESH_{clave.upper()}"):
            resumen[clave] = {"canal": clave, "conectado": False}
            continue
        try:
            r = revisar(clave, cfg)
        except Exception as e:  # un canal que falla no para a los demás
            r = {"canal": clave, "error": f"{type(e).__name__}: {str(e)[:200]}"}
            fallos += 1
        resumen[clave] = r
        privado.guardar_estado(f"canales/{clave}.json", r)
        if not r.get("error"):
            apuntar_historial(clave, r)
        jefes.apuntar("revision", {"canal": clave, "programados": len(r.get("programados", [])), "hasta": r.get("hasta"),
                                   "error": r.get("error")})
        if r.get("error"):
            print(f"{clave}: ERROR {r['error']}")
        else:
            print(f"{clave}: {r['suscriptores']} suscriptores · {len(r['programados'])} programados "
                  f"(hasta {r['hasta'] or '—'}) · {r['programados24h']} en 24 h")
    jefes.guardar()
    privado.guardar_estado("canales/_resumen.json", {"canales": {k: {x: v.get(x) for x in
                           ("suscriptores", "programados24h", "hasta", "error", "conectado")} for k, v in resumen.items()}})
    return 1 if fallos == len(resumen) and resumen else 0


if __name__ == "__main__":
    sys.exit(main())
