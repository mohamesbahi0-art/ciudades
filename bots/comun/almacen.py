"""El Almacén: guarda vídeos en el repositorio PRIVADO como archivos de una «release» de GitHub, para no llenar su
historial. Dos estanterías: «cola» (vídeos que esperan a subirse a YouTube porque hoy no había cupo) y «para-subir»
(los de TikTok e Instagram que sube el dueño a mano). Usa la herramienta gh con la llave GH_SECRETOS.

Solo funciona dentro de GitHub Actions (o con GH_TOKEN y REPO_PRIVADO puestos)."""
import json
import os
import subprocess

TITULOS = {"cola": "Cola de subidas a YouTube", "para-subir": "Para subir (TikTok e Instagram)",
           "espera": "Sala de espera del Juzgado (vídeos que esperan a un juez de primera)"}


def repo():
    if os.environ.get("REPO_PRIVADO"):
        return os.environ["REPO_PRIVADO"]
    duenio = os.environ.get("GITHUB_REPOSITORY_OWNER")
    if not duenio:
        raise RuntimeError("No sé de quién es el repositorio privado (falta GITHUB_REPOSITORY_OWNER o REPO_PRIVADO).")
    return f"{duenio}/ciudades-memoria"


def _gh(*args, comprobar=True):
    env = dict(os.environ)
    env.setdefault("GH_TOKEN", os.environ.get("GH_SECRETOS", ""))
    r = subprocess.run(["gh", *args, "--repo", repo()], capture_output=True, text=True, env=env)
    if comprobar and r.returncode != 0:
        raise RuntimeError(f"gh {args[0]} {args[1] if len(args) > 1 else ''}: {r.stderr.strip()[:300]}")
    return r


def _estanteria(etiqueta):
    if _gh("release", "view", etiqueta, comprobar=False).returncode != 0:
        _gh("release", "create", etiqueta, "--title", TITULOS.get(etiqueta, etiqueta),
            "--notes", "La llenan y la vacían los robots de Las 4 Ciudades. No borres nada a mano.")


def guardar(etiqueta, ruta, nombre=None):
    """Sube el archivo a la estantería y devuelve su enlace de descarga (se abre con la sesión de GitHub iniciada)."""
    _estanteria(etiqueta)
    nombre = nombre or os.path.basename(ruta)
    destino = ruta
    if os.path.basename(ruta) != nombre:
        destino = os.path.join(os.path.dirname(ruta) or ".", nombre)
        os.link(ruta, destino) if not os.path.exists(destino) else None
    _gh("release", "upload", etiqueta, destino, "--clobber")
    return enlace(etiqueta, nombre)


def enlace(etiqueta, nombre):
    return f"https://github.com/{repo()}/releases/download/{etiqueta}/{nombre}"


def bajar(etiqueta, nombre, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    _gh("release", "download", etiqueta, "--pattern", nombre, "--dir", carpeta, "--clobber")
    return os.path.join(carpeta, nombre)


def borrar(etiqueta, nombre):
    _gh("release", "delete-asset", etiqueta, nombre, "--yes", comprobar=False)


def lista(etiqueta):
    r = _gh("release", "view", etiqueta, "--json", "assets", comprobar=False)
    if r.returncode != 0:
        return []
    return [a["name"] for a in json.loads(r.stdout or "{}").get("assets", [])]
