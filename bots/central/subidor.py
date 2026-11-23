"""El Subidor: programa cada vídeo aprobado en YouTube, en el hueco que le toca, comprobando antes que el permiso es del
canal correcto. Si hoy no se puede (se acabó la cuota común o el tope del canal), el vídeo no se pierde: espera en la
cola del Almacén y se sube en la siguiente ronda con cupo.

Lleva la cuenta de las subidas del día (la cuota de YouTube se renueva a medianoche de California, las 09:00 de España)
en estado/cuota.json del repositorio privado."""
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import subir as herramienta  # noqa: E402  (herramientas/subir.py)
from bots.central import huecos  # noqa: E402
from bots.comun import almacen, privado  # noqa: E402

CALIFORNIA = ZoneInfo("America/Los_Angeles")
REGISTRO = os.path.join("registro", "subidas.json")


def _dia():
    return dt.datetime.now(CALIFORNIA).date().isoformat()


def cuota():
    c = privado.leer(os.path.join("estado", "cuota.json"), {}) or {}
    if c.get("dia") != _dia():
        c = {"dia": _dia(), "subidas": 0, "intentos": 0, "agotada_hasta": c.get("agotada_hasta")}
    if c.get("agotada_hasta") and huecos.fecha(c["agotada_hasta"]) <= dt.datetime.now(dt.timezone.utc):
        c["agotada_hasta"] = None
    return c


def _guardar_cuota(c):
    privado.escribir(os.path.join("estado", "cuota.json"), dict(c, actualizado=privado.ahora()))


def hay_cupo(ajustes):
    c = cuota()
    return not c.get("agotada_hasta") and c["subidas"] < ajustes["subidas_por_dia"]


def _manana_california():
    manana = dt.datetime.now(CALIFORNIA).date() + dt.timedelta(days=1)
    return dt.datetime(manana.year, manana.month, manana.day, 0, 10, tzinfo=CALIFORNIA).astimezone(dt.timezone.utc)


def descripcion(guion):
    etiquetas = " ".join(guion.get("hashtags", []))
    return f"{guion.get('descripcion', '').strip()}\n\n{etiquetas}".strip()


def subir(clave, canal, video, guion, hora, prueba=False):
    """Intenta subir. Devuelve {"resultado": "subido" | "prueba" | "rechazado", "codigo", "mensaje", "id", "hora"}."""
    c = cuota()
    codigo, mensaje, vid = herramienta.subir(
        clave, video, guion["titulo"], huecos.iso(hora), os.path.join(privado.carpeta(), REGISTRO),
        descripcion=descripcion(guion), etiquetas=[h.lstrip("#") for h in guion.get("hashtags", [])][:10],
        categoria=canal.get("categoria", "24"), ia=canal.get("aviso_ia", True), prueba=prueba,
        idioma=canal.get("idioma", "es")[:2])
    if prueba:
        return {"resultado": "prueba", "codigo": codigo, "mensaje": mensaje, "hora": huecos.iso(hora)}
    c["intentos"] = c.get("intentos", 0) + 1
    if codigo == 0 and vid:
        c["subidas"] += 1
    if codigo == 3:
        c["agotada_hasta"] = huecos.iso(_manana_california())
    _guardar_cuota(c)
    if codigo == 0:
        privado.apuntar_titulo(clave, guion["titulo"])
        return {"resultado": "subido", "codigo": 0, "mensaje": mensaje, "id": vid, "hora": huecos.iso(hora),
                "url": f"https://youtu.be/{vid}" if vid else None}
    return {"resultado": "rechazado", "codigo": codigo, "mensaje": mensaje, "hora": huecos.iso(hora)}


def encolar(clave, video, guion, motivo, juicio=None):
    """Guarda el vídeo en el Almacén para subirlo en otra ronda."""
    nombre = f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')}-{clave}.mp4"
    almacen.guardar("cola", video, nombre)
    privado.escribir(os.path.join("cola", nombre.replace(".mp4", ".json")),
                     {"canal": clave, "archivo": nombre, "guion": guion, "motivo": motivo, "juicio": juicio,
                      "encolado": privado.ahora()})
    return nombre


def en_cola():
    carpeta = os.path.join(privado.carpeta(), "cola")
    if not os.path.isdir(carpeta):
        return []
    items = []
    for n in sorted(os.listdir(carpeta)):
        if n.endswith(".json"):
            d = privado.leer(os.path.join("cola", n), None)
            if d:
                items.append(d)
    return items


def vaciar_cola(ajustes, revisiones, trabajo, avisar=print):
    """Sube lo que espera en la cola, el más antiguo primero, mientras haya cupo. Devuelve cuántos subió."""
    registro = privado.leer(REGISTRO, []) or []
    hechos = 0
    for item in en_cola():
        if not hay_cupo(ajustes):
            break
        clave = item["canal"]
        canal = privado.canal(clave)
        if canal.get("pausado"):
            continue
        ocupadas = huecos.ocupados(revisiones.get(clave), registro, [], clave)
        hora = huecos.siguiente(canal["horas"], ocupadas, dias_maximos=ajustes["dias_maximos"])
        if not hora:
            continue
        try:
            video = almacen.bajar("cola", item["archivo"], trabajo)
        except RuntimeError as e:
            avisar(f"cola: no puedo bajar un vídeo de {clave} ({e})")
            continue
        r = subir(clave, canal, video, item["guion"], hora)
        avisar(f"cola: {clave} → {r['resultado']} (código {r['codigo']})")
        if r["resultado"] == "subido":
            almacen.borrar("cola", item["archivo"])
            os.remove(os.path.join(privado.carpeta(), "cola", item["archivo"].replace(".mp4", ".json")))
            registro = privado.leer(REGISTRO, []) or []
            hechos += 1
        elif r["codigo"] in (2, 4, 5):
            item.update(ultimo_intento=privado.ahora(), motivo=r["mensaje"])
            privado.escribir(os.path.join("cola", item["archivo"].replace(".mp4", ".json")), item)
        if os.path.exists(video):
            os.remove(video)
    return hechos
