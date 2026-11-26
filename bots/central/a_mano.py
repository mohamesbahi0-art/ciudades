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


def mirar(clave):
    """El siguiente guion a mano de la cuenta SIN quitarlo (para una muestra de prueba que no se publica), o None."""
    try:
        d = privado.leer(_ruta(clave), {}) or {}
        guiones = [g for g in d.get("guiones") or [] if isinstance(g, dict) and g.get("escenas")]
        return dict(guiones[0], cerebro="claude (a mano)") if guiones else None
    except Exception:
        return None


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


def devolver(clave, guion, veredicto=None, maximo=1):
    """El guion a mano suspendió por poco y no queda IA para la segunda oportunidad: vuelve a la mesa (al final, con lo
    que dijo el juez) en vez de perderse. Como mucho `maximo` vueltas. Devuelve True si ha vuelto."""
    try:
        vueltas = int(guion.get("vueltas") or 0)
        if vueltas >= maximo:
            return False
        d = privado.leer(_ruta(clave), {}) or {}
        guiones = [g for g in d.get("guiones") or [] if isinstance(g, dict)]
        g = {k: v for k, v in guion.items() if k not in ("cerebro",)}
        g["vueltas"] = vueltas + 1
        if veredicto:
            g["ultimo_juicio"] = {k: veredicto.get(k) for k in ("total", "consejo", "fallos_graves")}
        guiones.append(g)
        d["guiones"] = guiones
        d["actualizado"] = privado.ahora()
        privado.escribir(_ruta(clave), d)
        return True
    except Exception:
        return False

