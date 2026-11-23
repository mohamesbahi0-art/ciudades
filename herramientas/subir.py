"""Sube un vídeo a YouTube en privado y programado a su hora (publishAt), gratis con la API oficial.
Es el Subidor de la Ciudad Central. No necesita ordenador: corre en GitHub Actions con los secretos del repositorio.

Uso:
  python subir.py --canal gta --id-canal UCxxxxxxxxxxxxxxxxxxxxxx --video v.mp4 --titulo "..." \
                  --descripcion "..." --etiquetas "gta 6,shorts" --hora "2026-11-25T13:00:00+01:00" \
                  --registro registro_subidas.json [--portada p.jpg] [--ia] [--prueba]

Secretos (variables de entorno, nunca en el código): YT_CLIENT_ID, YT_CLIENT_SECRET y
YT_REFRESH_<CANAL> (por ejemplo YT_REFRESH_GTA), el permiso de ese canal.

Sale con: 0 subido (o ya estaba en el registro) · 2 tope de subidas del canal (esperar 1 hora) ·
3 sin cuota de la API hoy · 4 el permiso es de otro canal (no sube nada) · 5 permiso caducado o revocado · 1 otro error.
"""
import argparse, datetime as dt, json, os, random, sys, time

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
REINTENTABLES = {500, 502, 503, 504}


def leer_registro(ruta):
    try:
        return json.load(open(ruta, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def motivo(err):
    try:
        return json.loads(err.content.decode())["error"]["errors"][0]["reason"]
    except Exception:
        return ""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--canal", required=True, help="clave del canal (gta, clips, curios…)")
    p.add_argument("--id-canal", dest="id_canal", required=True, help="id de YouTube esperado (UC…)")
    p.add_argument("--video", required=True)
    p.add_argument("--titulo", required=True)
    p.add_argument("--descripcion", default="")
    p.add_argument("--etiquetas", default="")
    p.add_argument("--hora", required=True, help="hora de publicación con zona, ISO 8601")
    p.add_argument("--categoria", default="24", help="24 entretenimiento, 20 videojuegos")
    p.add_argument("--registro", required=True)
    p.add_argument("--portada")
    p.add_argument("--ia", action="store_true", help="marca contenido sintético realista (aviso de IA de YouTube)")
    p.add_argument("--prueba", action="store_true", help="comprueba todo sin conectarse ni subir")
    a = p.parse_args()

    if not os.path.isfile(a.video):
        sys.exit(f"No existe el vídeo {a.video}")
    if len(a.titulo) > 100:
        sys.exit("El título pasa de 100 caracteres: YouTube lo rechaza.")
    hora = dt.datetime.fromisoformat(a.hora)
    if hora.tzinfo is None:
        sys.exit("La hora tiene que llevar zona, por ejemplo 2026-11-25T13:00:00+01:00")
    if hora <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15):
        sys.exit("La hora de publicación tiene que ser al menos 15 minutos en el futuro.")
    registro = leer_registro(a.registro)
    if any(r.get("archivo") == os.path.basename(a.video) and r.get("canal") == a.canal for r in registro):
        print("Ya estaba subido según el registro: no lo subo otra vez.")
        return 0
    cuerpo = {
        "snippet": {"title": a.titulo, "description": a.descripcion, "categoryId": a.categoria,
                    "tags": [t.strip() for t in a.etiquetas.split(",") if t.strip()],
                    "defaultLanguage": "es", "defaultAudioLanguage": "es"},
        "status": {"privacyStatus": "private", "publishAt": hora.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "selfDeclaredMadeForKids": False, "containsSyntheticMedia": bool(a.ia)},
    }
    if a.prueba:
        print("PRUEBA, no se sube nada. Esto es lo que se mandaría:")
        print(json.dumps(cuerpo, ensure_ascii=False, indent=1))
        return 0

    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    clave_secreto = "YT_REFRESH_" + a.canal.upper()
    falta = [v for v in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", clave_secreto) if not os.environ.get(v)]
    if falta:
        sys.exit("Faltan secretos: " + ", ".join(falta))
    cred = Credentials(None, refresh_token=os.environ[clave_secreto], client_id=os.environ["YT_CLIENT_ID"],
                       client_secret=os.environ["YT_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token",
                       scopes=SCOPES)
    yt = build("youtube", "v3", credentials=cred, cache_discovery=False)
    try:
        mios = yt.channels().list(part="id", mine=True).execute().get("items", [])
    except RefreshError:
        print("El permiso de este canal ha caducado o se ha quitado: el dueño tiene que pulsar «Permitir» otra vez.")
        return 5
    if not mios or mios[0]["id"] != a.id_canal:
        print(f"El permiso es de otro canal ({mios[0]['id'] if mios else 'ninguno'}), no de {a.id_canal}. No subo nada.")
        return 4

    media = MediaFileUpload(a.video, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    peticion = yt.videos().insert(part="snippet,status", body=cuerpo, media_body=media)
    respuesta, intento = None, 0
    while respuesta is None:
        try:
            _, respuesta = peticion.next_chunk()
        except HttpError as e:
            r = motivo(e)
            if r == "uploadLimitExceeded":
                print("YouTube no deja subir más vídeos hoy a este canal. Esperar 1 hora antes de reintentar.")
                return 2
            if r in ("quotaExceeded", "dailyLimitExceeded"):
                print("Se ha acabado la cuota de la API por hoy (se renueva hacia las 09:00 de España).")
                return 3
            if e.resp.status in REINTENTABLES and intento < 6:
                intento += 1
                time.sleep(min(60, 2 ** intento) + random.random())
                continue
            raise
    vid = respuesta["id"]
    if a.portada and os.path.isfile(a.portada):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(a.portada)).execute()
        except HttpError as e:
            print("La portada no se pudo poner (el canal tiene que estar verificado):", motivo(e) or e.resp.status)
    registro.append({"canal": a.canal, "archivo": os.path.basename(a.video), "id": vid, "titulo": a.titulo,
                     "publica": cuerpo["status"]["publishAt"],
                     "subido": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    tmp = a.registro + ".tmp"
    json.dump(registro, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, a.registro)
    print(f"OK subido https://youtu.be/{vid} · sale el {hora.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
