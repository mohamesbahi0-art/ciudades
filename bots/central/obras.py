"""«Ahora en la fábrica»: lo que se está creando ahora mismo, vídeo a vídeo (lo pidió el dueño).

Cada turno apunta aquí cada paso de su vídeo (qué robot lo tiene, qué hace y cómo va) en estado/obras.json del
repositorio privado; la ronda de Claude lo copia a la app (colección obras/{id}). Los terminados se quedan 36 horas
para «Recién terminados» y luego se borran solos. Nunca para un turno: si algo falla aquí, se sigue.
"""
import datetime as dt
import os

from bots.comun import privado

ARCHIVO = os.path.join("estado", "obras.json")
GUARDA_HORAS = 36
PASOS = {"reportero_gta6": "idea", "investigador": "idea", "sala_ideas": "sala_ideas", "escritor": "guion",
         "guionista": "guion", "jurado_popular": "jurado", "locutor": "voz", "dibujante": "dibujos",
         "editor_video": "montaje", "montador": "montaje", "portero_clips": "montaje", "juez_guardia": "juzgado",
         "jueces_sala": "juzgado", "juez_mayor": "juzgado", "coliseo": "coliseo", "subidor": "sale",
         "publicador": "para_subir"}


def _leer():
    return privado.leer(ARCHIVO, {}) or {}


def apuntar(id_obra, canal, robot=None, detalle=None, titulo=None, estado="en_marcha", paso=None):
    """Pone al día un vídeo en marcha. Devuelve el documento (o None si algo falla)."""
    try:
        d = _leer()
        obras = d.setdefault("obras", {})
        ahora = privado.ahora()
        o = obras.setdefault(id_obra, {"canal": canal, "empezado": ahora, "estado": "en_marcha"})
        if robot:
            o["robot"] = robot
            o["paso"] = paso or PASOS.get(robot, o.get("paso", "guion"))
        elif paso:
            o["paso"] = paso
        if detalle:
            o["detalle"] = str(detalle)[:160]
        if titulo:
            o["titulo"] = str(titulo)[:120]
        o["estado"], o["actualizado"] = estado, ahora
        limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=GUARDA_HORAS)
        for k in [k for k, v in obras.items() if v.get("estado") in ("terminado", "descartado")
                  and str(v.get("actualizado", "")) < limite.strftime("%Y-%m-%dT%H:%M:%SZ")]:
            obras.pop(k)
        d["actualizado"] = ahora
        privado.escribir(ARCHIVO, d)
        return o
    except Exception as e:                    # «Ahora en la fábrica» nunca para un vídeo
        print(f"obras: no se ha podido apuntar ({type(e).__name__})", flush=True)
        return None
