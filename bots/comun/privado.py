"""Acceso a lo privado (repositorio ciudades-memoria, que los turnos sacan en la carpeta de la variable PRIVADO):
configuración de canales, estado para la app y memoria de los robots."""
import datetime as dt
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import memoria  # noqa: E402  (herramientas/memoria.py)


def carpeta():
    return os.environ.get("PRIVADO") or os.path.join(RAIZ, "..", "ciudades-memoria")


def ahora():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canal(clave):
    with open(os.path.join(carpeta(), "config", "canales.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    if clave not in cfg["canales"]:
        raise SystemExit(f"No conozco el canal «{clave}». Están: {', '.join(cfg['canales'])}")
    datos = dict(cfg["canales"][clave])
    datos["clave"] = clave
    return datos


def cuaderno(robot):
    os.environ.setdefault("MEMORIA_DIR", os.path.join(carpeta(), "memoria"))
    return memoria.Cuaderno(robot)


def guardar_estado(ruta_relativa, datos):
    """Deja el estado de un robot o de un canal en estado/ del repositorio privado (lo copia a la app una ronda de Claude)."""
    ruta = os.path.join(carpeta(), "estado", ruta_relativa)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    datos = dict(datos, actualizado=ahora())
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)


def titulos_recientes(clave, cuantos=40):
    """Títulos ya hechos en ese canal, para no repetir temas."""
    ruta = os.path.join(carpeta(), "estado", "titulos", f"{clave}.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)[-cuantos:]
    except (FileNotFoundError, ValueError):
        return []


def apuntar_titulo(clave, titulo):
    ruta = os.path.join(carpeta(), "estado", "titulos", f"{clave}.json")
    lista = titulos_recientes(clave, 10_000)
    lista.append(titulo)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(lista[-500:], f, ensure_ascii=False, indent=1)
