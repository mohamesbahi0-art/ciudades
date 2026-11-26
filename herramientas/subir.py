"""Sube un vídeo a YouTube en privado y programado a su hora (publishAt), gratis con la API oficial.
Es el Subidor de la Ciudad Central. No necesita ordenador: corre en GitHub Actions con los secretos del repositorio.

Uso:
  python subir.py --canal gta --id-canal UCxxxxxxxxxxxxxxxxxxxxxx --video v.mp4 --titulo "..." \
                  --descripcion "..." --etiquetas "gta 6,shorts" --hora "2026-11-25T13:00:00+01:00" \
                  --registro registro_subidas.json [--portada p.jpg] [--ia] [--prueba]

Secretos (variables de entorno, nunca en el código): YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_<CANAL> (el permiso
del canal, por ejemplo YT_REFRESH_GTA) y YT_ID_<CANAL> (su id). Los dos últimos los guarda conectar_canal.py.
Si no se da --id-canal, se usa YT_ID_<CANAL>.

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


def subir(canal, video, titulo, hora, registro, descripcion="", etiquetas="", categoria="24", portada=None, ia=False,
          id_canal=None, prueba=False, idioma="es"):
    """Sube y programa un vídeo. Devuelve (código, mensaje, id del vídeo o None) con los mismos códigos de salida."""
    if not os.path.isfile(video):
        return 1, f"No existe el vídeo {video}", None
    if len(titulo) > 100:
        return 1, "El título pasa de 100 caracteres: YouTube lo rechaza.", None
    hora = dt.datetime.fromisoformat(hora.replace("Z", "+00:00")) if isinstance(hora, str) else hora
    if hora.tzinfo is None:
        return 1, "La hora tiene que llevar zona, por ejemplo 2026-11-25T13:00:00+01:00", None
    if hora <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15):
        return 1, "La hora de publicación tiene que ser al menos 15 minutos en el futuro.", None
    lista = leer_registro(registro)
    # Mismo canal, mismo archivo Y mismo título: los vídeos del estudio se llaman todos «video.mp4», así que el nombre
    # solo no basta (se perdieron dos vídeos aprobados el 26 nov por creerlos ya subidos).
    if any(r.get("archivo") == os.path.basename(video) and r.get("canal") == canal and r.get("titulo") == titulo
           for r in lista):
        return 0, "Ya estaba subido según el registro: no lo subo otra vez.", None
    if isinstance(etiquetas, str):
        etiquetas = [t.strip() for t in etiquetas.split(",") if t.strip()]
    cuerpo = {
        "snippet": {"title": titulo, "description": descripcion, "categoryId": str(categoria), "tags": etiquetas,
                    "defaultLanguage": idioma, "defaultAudioLanguage": idioma},
        "status": {"privacyStatus": "private", "publishAt": hora.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "selfDeclaredMadeForKids": False, "containsSyntheticMedia": bool(ia)},
    }
    if prueba:
        return 0, "PRUEBA, no se sube nada. Esto es lo que se mandaría:\n" + json.dumps(cuerpo, ensure_ascii=False, indent=1), None

    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    falta = [v for v in ("YT_CLIENT_ID", "YT_CLIENT_SECRET") if not os.environ.get(v)]
    if falta:
        return 1, "Faltan secretos: " + ", ".join(falta), None
    refresh = os.environ.get("YT_REFRESH_" + canal.upper())
    if not refresh:
        return 5, f"El canal {canal} todavía no está conectado (falta el secreto YT_REFRESH_{canal.upper()}).", None
    id_canal = id_canal or os.environ.get("YT_ID_" + canal.upper())
    if not id_canal:
        return 1, "No sé qué id de canal esperar: pásalo con --id-canal.", None
    cred = Credentials(None, refresh_token=refresh, client_id=os.environ["YT_CLIENT_ID"],
                       client_secret=os.environ["YT_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=cred, cache_discovery=False)
    try:
        mios = yt.channels().list(part="id", mine=True).execute().get("items", [])
    except RefreshError:
        return 5, "El permiso de este canal ha caducado o se ha quitado: el dueño tiene que pulsar «Permitir» otra vez.", None
    except HttpError as e:
        if motivo(e) in ("quotaExceeded", "dailyLimitExceeded"):
            return 3, "Se ha acabado la cuota de la API por hoy (se renueva hacia las 09:00 de España).", None
        raise
    if not mios or mios[0]["id"] != id_canal:
        return 4, "El permiso es de otro canal, no del que toca. No subo nada.", None

    media = MediaFileUpload(video, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    peticion = yt.videos().insert(part="snippet,status", body=cuerpo, media_body=media)
    respuesta, intento = None, 0
    while respuesta is None:
        try:
            _, respuesta = peticion.next_chunk()
        except HttpError as e:
            r = motivo(e)
            if r == "uploadLimitExceeded":
                return 2, "YouTube no deja subir más vídeos hoy a este canal. Esperar 1 hora antes de reintentar.", None
            if r in ("quotaExceeded", "dailyLimitExceeded"):
                return 3, "Se ha acabado la cuota de la API por hoy (se renueva hacia las 09:00 de España).", None
            if e.resp.status in REINTENTABLES and intento < 6:
                intento += 1
                time.sleep(min(60, 2 ** intento) + random.random())
                continue
            raise
    vid = respuesta["id"]
    aviso = ""
    if portada and os.path.isfile(portada):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(portada)).execute()
        except HttpError as e:
            aviso = f" (la portada no se pudo poner: {motivo(e) or e.resp.status})"
    lista = leer_registro(registro)
    lista.append({"canal": canal, "archivo": os.path.basename(video), "id": vid, "titulo": titulo, "ia": bool(ia),
                  "publica": cuerpo["status"]["publishAt"],
                  "subido": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    os.makedirs(os.path.dirname(os.path.abspath(registro)), exist_ok=True)
    tmp = registro + ".tmp"
    json.dump(lista, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, registro)
    return 0, f"OK subido https://youtu.be/{vid} · sale el {hora.isoformat()}{aviso}", vid


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--canal", required=True, help="clave del canal (gta, clips, curios…)")
    p.add_argument("--id-canal", dest="id_canal", help="id de YouTube esperado (UC…); por defecto, el del permiso")
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
    codigo, mensaje, _ = subir(a.canal, a.video, a.titulo, a.hora, a.registro, a.descripcion, a.etiquetas, a.categoria,
                               a.portada, a.ia, a.id_canal, a.prueba)
    print(mensaje)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
