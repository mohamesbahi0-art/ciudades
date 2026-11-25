"""La Sala de espera del Juzgado.

Cuando a los jueces de primera (Gemini de primera y Claude) no les queda cupo, juzgan los suplentes (la IA gratis de
reserva). Un suplente puede suspender un vídeo y decir qué arreglar, pero su aprobado no basta para publicar: el vídeo
ya montado se guarda aquí, con su guion y lo que dijo el suplente, hasta que un juez de primera lo confirma. Así la
fábrica sigue trabajando las 24 horas sin bajar el listón del dueño (nada sale sin 90 de un juez de primera).

- El vídeo va a la estantería «espera» del almacén privado; la ficha, a estado/espera/<alias>.json.
- Cada cuenta puede tener POR_CUENTA vídeos esperando; con la sala llena, la cuenta espera al juez en vez de hacer más.
- En el siguiente turno de la cuenta con juez de primera, el vídeo se juzga otra vez (solo jueces de primera) y, si
  aprueba, sigue su camino de siempre: Coliseo y subida o bandeja. Lo que lleva CADUCA_HORAS sin confirmarse se quita.
"""
import datetime as dt
import json
import os

from bots.comun import almacen, privado

ESTANTE = "espera"
CARPETA = os.path.join("estado", "espera")
POR_CUENTA = 2
CADUCA_HORAS = 36


def _ruta(clave):
    return os.path.join(CARPETA, f"{privado.alias(clave)}.json")


def _tope():
    try:
        return max(1, int(((privado.ajustes() or {}).get("juzgado") or {}).get("espera_por_cuenta", POR_CUENTA)))
    except Exception:
        return POR_CUENTA


def _vivos(clave, limpiar=False):
    """Las fichas de la cuenta que siguen valiendo, de la más antigua a la más nueva."""
    d = privado.leer(_ruta(clave), {}) or {}
    if d.get("clave") not in (None, clave):          # el alias puede pasar a otra cuenta: se comprueba
        return []
    limite = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=CADUCA_HORAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    todos = [e for e in d.get("videos") or [] if isinstance(e, dict) and e.get("video") and e.get("guion")]
    vivos = [e for e in todos if str(e.get("fecha") or "") >= limite]
    if limpiar and len(vivos) != len(todos):
        for e in todos:
            if e not in vivos:
                try:
                    almacen.borrar(ESTANTE, e["video"])
                except Exception:
                    pass
        _escribir(clave, vivos)
    return sorted(vivos, key=lambda e: str(e.get("fecha") or ""))


def _escribir(clave, videos):
    privado.escribir(_ruta(clave), {"clave": clave, "videos": videos, "actualizado": privado.ahora()})


def cuantos(clave):
    try:
        return len(_vivos(clave))
    except Exception:
        return 0


def llena(clave):
    return cuantos(clave) >= _tope()


def siguiente(clave):
    """El vídeo de la cuenta que más lleva esperando (None si no hay). Quita de paso los caducados."""
    try:
        vivos = _vivos(clave, limpiar=True)
        return vivos[0] if vivos else None
    except Exception:
        return None


def guardar(clave, video, guion, veredicto, segundos, id_guion=None, obra=None, extra=None):
    """Deja el vídeo en la sala. Devuelve su ficha. Lanza si no se puede guardar (el turno entonces espera sin más)."""
    sello = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S-%f")[:-3]      # con milésimas: nunca se repite
    nombre = f"{privado.alias(clave)}-{sello}.mp4".replace("/", "-")
    almacen.guardar(ESTANTE, video, nombre)
    ficha = {"id": sello, "video": nombre, "fecha": privado.ahora(), "segundos": segundos, "id_guion": id_guion,
             "obra": obra, "nota": veredicto.get("nota_suplente"), "suplente": veredicto.get("suplente"),
             "publico": veredicto.get("publico"), "consejo": veredicto.get("consejo"),
             "id_suplente": veredicto.get("id_suplente"),
             "guion": json.loads(json.dumps(guion, ensure_ascii=False, default=str))}
    ficha.update(extra or {})
    _escribir(clave, (_vivos(clave) + [ficha])[-_tope():])
    return ficha


def bajar(ficha, carpeta):
    return almacen.bajar(ESTANTE, ficha["video"], carpeta)


def quitar(clave, ficha):
    """El vídeo ya tiene sentencia de un juez de primera (o no se ha podido bajar): sale de la sala."""
    try:
        _escribir(clave, [e for e in _vivos(clave) if e.get("id") != ficha.get("id")])
    finally:
        try:
            almacen.borrar(ESTANTE, ficha["video"])
        except Exception:
            pass


def resumen():
    """Para la app y para la Élite: cuántos vídeos esperan y de qué cuentas (por alias)."""
    salida = {}
    carpeta = os.path.join(privado.carpeta(), CARPETA)
    if not os.path.isdir(carpeta):
        return salida
    for f in sorted(os.listdir(carpeta)):
        if f.endswith(".json"):
            d = privado.leer(os.path.join(CARPETA, f), {}) or {}
            n = len(_vivos(d.get("clave"))) if d.get("clave") else 0
            if n:
                salida[f[:-5]] = n
    return salida
