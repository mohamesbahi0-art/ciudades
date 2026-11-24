"""La bandeja «Para subir»: los vídeos de TikTok e Instagram que sube el dueño a mano (skill `para-subir`).

Cada vídeo terminado se guarda en la estantería «para-subir» del Almacén y deja un documento por red en parasubir/ del
repositorio privado, con el texto listo para copiar, las etiquetas y la hora recomendada. Una ronda de Claude lo copia a
la app (colección `parasubir`) y trae de vuelta lo que el dueño marca como subido o descartado."""
import datetime as dt
import os
import re
import unicodedata

from bots.central import huecos
from bots.comun import almacen, privado

CARPETA = "parasubir"


def slug(texto, largo=40):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:largo].strip("-") or "video"


def documentos():
    carpeta = os.path.join(privado.carpeta(), CARPETA)
    if not os.path.isdir(carpeta):
        return []
    salida = []
    for n in sorted(os.listdir(carpeta)):
        if n.endswith(".json"):
            d = privado.leer(os.path.join(CARPETA, n), None)
            if d:
                salida.append(dict(d, _id=n[:-5]))
    return salida


def pendientes(barrio):
    return sum(1 for d in documentos() if d.get("barrio") == barrio and d.get("estado") == "pendiente")


def cuando(barrio, canal, ahora=None):
    """La siguiente hora recomendada que no tenga ya otro vídeo pendiente del mismo barrio y red."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    ocupadas = [huecos.fecha(d["cuando"]) for d in documentos()
                if d.get("barrio") == barrio and d.get("estado") == "pendiente" and d.get("cuando")]
    return huecos.siguiente([canal.get("hora", "19:00")], ocupadas, ahora=ahora, dias_maximos=60)


def dejar(clave, canal, video, guion, duracion, juicio=None):
    """Guarda el vídeo y crea sus documentos. Devuelve los ids creados."""
    hoy = dt.datetime.now(dt.timezone.utc)
    base = f"{hoy.strftime('%Y-%m-%d')}-{slug(clave, 20)}-{slug(guion.get('titulo', 'video'), 30)}"
    enlace = almacen.guardar("para-subir", video, f"{base}.mp4")
    hora = cuando(clave, canal) or hoy + dt.timedelta(hours=2)
    ids = []
    guion_id = None
    try:        # el guion se guarda con el vídeo: así se le puede cambiar la voz o rehacerlo sin escribirlo otra vez
        from bots.estudio import estudio
        privado.escribir(os.path.join("estado", "guiones", f"{base}.json"),
                         {"barrio": clave, "creado": privado.ahora(), "guion": estudio.guion_escrito(guion)})
        guion_id = base
    except Exception as e:
        print(f"para subir: no he podido guardar el guion ({type(e).__name__})", flush=True)
    for red in canal.get("redes", ["instagram"]):
        texto = guion.get(f"texto_{red}") or guion.get("texto_instagram") or guion.get("descripcion", "")
        doc = {"barrio": clave, "red": red, "titulo": guion.get("titulo", ""), "texto": texto.strip(),
               "etiquetas": guion.get("hashtags", [])[:5], "video": enlace, "duracion": round(duracion, 1),
               "cuando": huecos.iso(hora), "creado": privado.ahora(), "estado": "pendiente"}
        if juicio:
            doc["nota"] = juicio.get("total")
            if juicio.get("cerebro"):
                doc["juzgo"] = juicio["cerebro"]             # quién juzgó: «claude» o «gemini» (lo enseña la app)
        if guion.get("cerebro"):
            doc["cerebro"] = guion["cerebro"]                # quién escribió el guion: «claude», «gemini» o «a mano»
        if guion_id:
            doc["guion_id"] = guion_id                       # estado/guiones/<guion_id>.json
        if guion.get("voz_motor"):
            doc["voz"] = guion["voz_motor"]                  # con qué voz salió: «edge» (gratis) o «elevenlabs»
        if guion.get("version", 1) > 1:
            doc["version"] = guion["version"]                # versión corregida tras un suspenso
        id_doc = f"{base}-{'ig' if red == 'instagram' else 'tt' if red == 'tiktok' else slug(red, 8)}"
        privado.escribir(os.path.join(CARPETA, f"{id_doc}.json"), doc)
        ids.append(id_doc)
    try:                                   # el Cartero avisa al móvil (sin nombres de cuentas)
        from bots.central import cartero
        esperan = len({(d.get("barrio"), d.get("titulo")) for d in documentos() if d.get("estado") == "pendiente"})
        textos = {red: guion.get(f"texto_{red}") or guion.get("texto_instagram") or guion.get("descripcion", "")
                  for red in canal.get("redes", ["instagram"])}
        cartero.entregar_video(video, guion.get("titulo", ""), textos, canal.get("apodo") or "una de tus cuentas", esperan)
    except Exception as e:
        print(f"cartero: no ha podido avisar ({type(e).__name__})", flush=True)
    return ids


def limpiar(dias=14):
    """Borra de la estantería los vídeos que el dueño ya subió o descartó hace más de `dias` días (el texto se queda)."""
    import collections
    por_video = collections.defaultdict(list)
    for d in documentos():
        if d.get("video") and not d.get("videoBorrado"):
            por_video[d["video"].rsplit("/", 1)[-1]].append(d)
    limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dias)
    borrados = 0
    for nombre, docs in por_video.items():
        fechas = [huecos.fecha(d.get("subidoEl") or d.get("descartadoEl")) for d in docs]
        if all(d.get("estado") in ("subido", "descartado") for d in docs) and all(f and f < limite for f in fechas):
            almacen.borrar("para-subir", nombre)
            for d in docs:
                d2 = {k: v for k, v in d.items() if k != "_id"}
                d2["videoBorrado"] = privado.ahora()
                privado.escribir(os.path.join(CARPETA, f"{d['_id']}.json"), d2)
            borrados += 1
    return borrados
