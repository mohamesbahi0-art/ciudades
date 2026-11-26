"""La Mesa de guiones a mano: guiones que escribe Claude (en un chat, con cuidado) para una cuenta que no arranca.

Van en el repositorio privado, en estado/a_mano/<alias>.json → {"guiones": [ {guion}, ... ]}. En el siguiente turno de
esa cuenta, el primero de la lista se graba TAL CUAL (sin ensayo ni Jurado popular, que lo reescribirían) y pasa por el
Juzgado como todos: solo se publica si llega a la nota mínima del dueño. Se quita de la lista al cogerlo, salga como
salga, para no repetirlo si suspende (sus fallos quedan para el arreglo, como cualquier otro vídeo).
"""
import os

from bots.comun import privado

CARPETA = os.path.join("estado", "a_mano")


def _ruta(clave):
    return os.path.join(CARPETA, f"{privado.alias(clave)}.json")


def cuantos(clave):
    try:
        return len((privado.leer(_ruta(clave), {}) or {}).get("guiones") or [])
    except Exception:
        return 0


def tomar(clave):
    """El siguiente guion a mano de la cuenta (y lo quita de la lista), o None."""
    try:
        d = privado.leer(_ruta(clave), {}) or {}
        guiones = [g for g in d.get("guiones") or [] if isinstance(g, dict) and g.get("escenas")]
        if not guiones:
            return None
        g = guiones.pop(0)
        d["guiones"] = guiones
        d["actualizado"] = privado.ahora()
        privado.escribir(_ruta(clave), d)
        g = dict(g)
        g.setdefault("cerebro", "claude (a mano)")
        return g
    except Exception as e:
        print(f"a mano: no he podido leer la mesa ({type(e).__name__})", flush=True)
        return None
