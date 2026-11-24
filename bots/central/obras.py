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
ESPERA_HORAS = 12             # un vídeo «esperando» (sin IA) que nadie retoma en este tiempo se quita de la lista
PASOS = {"reportero_gta6": "idea", "investigador": "idea", "sala_ideas": "sala_ideas", "escritor": "guion",
         "guionista": "guion", "jurado_popular": "jurado", "locutor": "voz", "dibujante": "dibujos",
         "editor_video": "montaje", "montador": "montaje", "portero_clips": "montaje", "juez_guardia": "juzgado",
         "jueces_sala": "juzgado", "juez_mayor": "juzgado", "coliseo": "coliseo", "subidor": "sale",
         "publicador": "para_subir"}


def _leer():
    return privado.leer(ARCHIVO, {}) or {}


def retomar(canal):
    """El vídeo de esta cuenta que se quedó «esperando» (sin IA o sin dibujos) en la ronda anterior: el turno nuevo sigue
    en esa misma ficha en vez de abrir otra (así la app no se llena de intentos a medias). None si no hay."""
    try:
        esperando = [(str(o.get("actualizado") or ""), k) for k, o in (_leer().get("obras") or {}).items()
                     if o.get("canal") == canal and o.get("estado") == "esperando"]
        return max(esperando)[1] if esperando else None
    except Exception:
        return None


def pausar(motivo, hasta=None):
    """La fábrica está parada (sin IA): la app lo enseña arriba («⏸️ en pausa hasta…») en vez de parecer rota."""
    try:
        d = _leer()
        ahora = privado.ahora()
        antes = d.get("pausa") or {}
        d["pausa"] = {"activa": True, "motivo": str(motivo)[:240], "hasta": hasta, "actualizado": ahora,
                      "desde": antes.get("desde") if antes.get("activa") else ahora}
        d["actualizado"] = ahora
        privado.escribir(ARCHIVO, d)
    except Exception as e:
        print(f"obras: no se ha podido apuntar la pausa ({type(e).__name__})", flush=True)


def reanudar():
    """La fábrica vuelve a trabajar: se quita la pausa (si la había)."""
    try:
        d = _leer()
        if (d.get("pausa") or {}).get("activa"):
            ahora = privado.ahora()
            d["pausa"] = {"activa": False, "actualizado": ahora}
            d["actualizado"] = ahora
            privado.escribir(ARCHIVO, d)
    except Exception as e:
        print(f"obras: no se ha podido quitar la pausa ({type(e).__name__})", flush=True)


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
        espera = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=ESPERA_HORAS)
        for k in [k for k, v in obras.items() if k != id_obra and (
                (v.get("estado") in ("terminado", "descartado")
                 and str(v.get("actualizado", "")) < limite.strftime("%Y-%m-%dT%H:%M:%SZ")) or
                (v.get("estado") == "esperando"                  # una espera vieja ya no dice nada: fuera
                 and str(v.get("actualizado", "")) < espera.strftime("%Y-%m-%dT%H:%M:%SZ")))]:
            obras.pop(k)
        d["actualizado"] = ahora
        privado.escribir(ARCHIVO, d)
        return o
    except Exception as e:                    # «Ahora en la fábrica» nunca para un vídeo
        print(f"obras: no se ha podido apuntar ({type(e).__name__})", flush=True)
        return None
