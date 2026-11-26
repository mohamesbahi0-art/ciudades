"""Trae vídeos públicos de una cuenta de referencia que eligió el dueño (para copiar el ESTILO, nunca para subirlos).

La dirección de la cuenta está solo en el repositorio privado (referencias/pedidas.json → {"<nombre>": "<url>"}), porque
este repositorio y sus registros son públicos. Mira la cuenta sin iniciar sesión, como una persona (yt-dlp normal, sin
cookies ni disfraces; si la red dice que no, se para). Elige los vídeos con más visitas, deja de cada uno una hoja de
fotogramas (.jpg) y sus datos en privado/referencias/<nombre>/ y el vídeo en la estantería «referencias». En el registro
público solo salen cifras.

    python herramientas/traer_referencias.py <nombre> [cuantos]
"""
import json
import os
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from bots.comun import almacen, privado  # noqa: E402


_MODELO = []


def transcribir(ruta):
    """Lo que se dice en el vídeo, con faster-whisper (gratis, en la máquina de GitHub)."""
    from faster_whisper import WhisperModel
    if not _MODELO:
        _MODELO.append(WhisperModel("small", device="cpu", compute_type="int8"))
    import numpy as np                  # el audio ya decodificado (así no hace falta la librería av, que choca de versión)
    crudo = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", ruta, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                           capture_output=True, check=True).stdout
    segs, _ = _MODELO[0].transcribe(np.frombuffer(crudo, dtype=np.float32), vad_filter=True)
    return " ".join(x.text.strip() for x in segs)


def main(nombre, cuantos=4):
    pedidas = privado.leer(os.path.join("referencias", "pedidas.json"), {}) or {}
    url = pedidas.get(nombre)
    if not url:
        print("no hay dirección para esa referencia")
        return 1
    r = subprocess.run(["yt-dlp", "-J", "--flat-playlist", "--playlist-end", "40", "--no-warnings", url],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"la red no deja ver la cuenta ahora (código {r.returncode}); no se insiste")
        return 1
    lista = (json.loads(r.stdout) or {}).get("entries") or []
    print(f"vídeos vistos: {len(lista)}")
    lista.sort(key=lambda e: e.get("view_count") or 0, reverse=True)
    carpeta = os.path.join(privado.carpeta(), "referencias", nombre)
    os.makedirs(carpeta, exist_ok=True)
    datos, tmp = [], tempfile.mkdtemp()
    for n, e in enumerate(lista[:cuantos], 1):
        u = e.get("url") or e.get("webpage_url")
        ruta = os.path.join(tmp, f"ref-{nombre}-{n}.mp4")
        d = subprocess.run(["yt-dlp", "-f", "b[height<=720]/b", "-o", ruta, "--no-warnings", "--no-playlist", u],
                           capture_output=True, text=True, timeout=300)
        if d.returncode != 0 or not os.path.exists(ruta):
            continue
        hoja = os.path.join(carpeta, f"{n}.jpg")
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                                   capture_output=True, text=True).stdout.strip() or 10)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", ruta, "-vf",
                        f"fps={12 / max(dur, 1):.4f},scale=270:-2,tile=6x2", "-frames:v", "1", hoja], check=False)
        try:
            almacen.guardar("referencias", ruta, os.path.basename(ruta))
        except Exception:
            pass
        texto = ""
        if os.environ.get("TRANSCRIBIR"):          # lo que dice en voz (para fijarse en lo que transmite)
            try:
                texto = transcribir(ruta)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                texto = f"(no se pudo transcribir: {type(ex).__name__}: {str(ex)[:200]})"
        datos.append({"n": n, "url": u, "titulo": e.get("title"), "descripcion": e.get("description"),
                      "visitas": e.get("view_count"), "segundos": round(dur, 1), "texto": texto})
    json.dump({"url": url, "videos": datos}, open(os.path.join(carpeta, "datos.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"traídos: {len(datos)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 4))
