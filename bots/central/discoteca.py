"""La Discoteca: música de fondo de verdad, compuesta por músicos y regalada al dominio público (CC0), para que los vídeos
no suenen a ordenador. Se puede usar en cualquier vídeo, gratis y sin nombrar a nadie.

Baja piezas de FreePD.com (música de dominio público) por estilos, el oído de la Policía (Gemini) escucha un trozo de
cada una y solo se quedan las que sirven de fondo y no tienen voz cantada. Se guardan como archivos de la release
«musica» del repositorio privado y la lista en estado/musica/biblioteca.json. La fábrica las baja al empezar cada ronda
(preparar) y herramientas/musica.py las usa; si no hay ninguna, compone la suya.

Uso:  python bots/central/discoteca.py [--por-ambiente 6]      (en GitHub Actions)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import almacen, gemini, privado  # noqa: E402

WEB = "https://freepd.com/"
ESTANTERIA = "musica"
LISTA = os.path.join("estado", "musica", "biblioteca.json")
LICENCIA = "CC0 · dominio público (FreePD.com): se puede usar sin pedir permiso ni nombrar al autor"
CABECERAS = {"User-Agent": "Mozilla/5.0 (compatible; music-library-fetch/1.0)"}
# palabras de la sección de la web → ambientes de herramientas/musica.py
ESTILOS = [("epic", "inspira"), ("scoring", "inspira"), ("inspir", "inspira"), ("motiv", "inspira"),
           ("upbeat", "energia"), ("electronic", "energia"), ("action", "energia"),
           ("horror", "tension"), ("mystery", "tension"), ("suspense", "tension"), ("dark", "tension"),
           ("romantic", "calma"), ("world", "calma"), ("calm", "calma"), ("piano", "calma")]
USOS = {"inspira": "historias motivadoras de famosos en TikTok, con una voz contando la historia encima",
        "energia": "vídeos de videojuegos (GTA) y datos curiosos en YouTube Shorts, con voz encima",
        "tension": "historias de terror en YouTube Shorts, con voz encima",
        "calma": "vídeos informativos tranquilos, con voz encima"}
OIDO = """Escucha este trozo de 30 segundos de una música de dominio público. Queremos usarla DE FONDO, bajita, debajo de
una voz que narra, en {uso}. Sé exigente: puntúa de 1 a 10 si queda bien así (10 = perfecta y profesional).
Di también si tiene voz cantada o letra (entonces no sirve) y para cuáles de estos usos valdría: inspira (motivación,
emoción, épica), energia (videojuegos, ritmo, curiosidades), tension (terror, misterio), calma (información tranquila).
Devuelve SOLO un JSON: {{"nota": 0, "voz_cantada": false, "sirve_para": ["inspira"], "suena_a": "una frase"}}"""


def _bajar(url, destino=None, limite=15_000_000):
    req = urllib.request.Request(url, headers=CABECERAS)
    with urllib.request.urlopen(req, timeout=60) as r:
        datos = r.read(limite + 1)
    if len(datos) > limite:
        raise ValueError("demasiado grande")
    if destino:
        with open(destino, "wb") as f:
            f.write(datos)
        return destino
    return datos.decode("utf-8", "replace")


def _enlaces(html, base, final):
    vistos = []
    for h in re.findall(r'href\s*=\s*["\']([^"\']+)["\']', html, flags=re.I):
        url = urllib.parse.urljoin(base, h)
        if url.lower().split("?")[0].endswith(final) and url.startswith(WEB) and url not in vistos:
            vistos.append(url)
    return vistos


def _ambiente(pagina):
    nombre = pagina.lower().rsplit("/", 1)[-1]
    return next((a for clave, a in ESTILOS if clave in nombre), None)


def _segundos(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def _slug(texto):
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")[:40] or "pieza"


def llenar(por_ambiente=6, avisar=print):
    portada = _bajar(WEB)
    if not re.search(r"public domain|cc0|creative commons zero", portada, flags=re.I):
        raise RuntimeError("La web ya no dice que su música sea de dominio público: no se baja nada.")
    avisar("discoteca: la web confirma que su música es de dominio público")
    todos = []
    for h in re.findall(r'href\s*=\s*["\']([^"\']+)["\']', portada, flags=re.I):
        url = urllib.parse.urljoin(WEB, h)
        if url.startswith(WEB) and url not in todos:
            todos.append(url)
    paginas = [p for p in todos if _ambiente(p) and not p.lower().endswith(".mp3")]
    avisar(f"discoteca: secciones útiles: {', '.join(p.rsplit('/', 1)[-1] for p in paginas) or 'ninguna'}")
    if not paginas:                        # la web ha cambiado: se enseña su índice para arreglarlo
        avisar("discoteca: enlaces de la portada: " + " | ".join(u[len(WEB):] for u in todos[:80]))
    lista = privado.leer(LISTA, {}) or {}
    pistas = {p["fuente"]: p for p in lista.get("pistas", [])}
    cuenta = {a: sum(1 for p in pistas.values() if p.get("vale") and p.get("ambiente") == a) for a in USOS}
    with tempfile.TemporaryDirectory() as tmp:
        for pagina in paginas:
            amb = _ambiente(pagina)
            try:
                mp3s = _enlaces(_bajar(pagina), pagina, ".mp3")
            except Exception as e:      # una sección caída no para las demás
                avisar(f"discoteca: {pagina.rsplit('/', 1)[-1]} no carga ({type(e).__name__})")
                continue
            for url in mp3s:
                if cuenta.get(amb, 0) >= por_ambiente:
                    break
                if url in pistas:
                    continue
                titulo = urllib.parse.unquote(url.rsplit("/", 1)[-1])[:-4]
                crudo, m4a, trozo = (os.path.join(tmp, "crudo.mp3"), os.path.join(tmp, f"{_slug(titulo)}.m4a"),
                                     os.path.join(tmp, "trozo.mp3"))
                try:
                    _bajar(url, crudo)
                    seg = _segundos(crudo)
                    if seg < 40:
                        continue
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", crudo, "-ac", "2", "-c:a", "aac",
                                    "-b:a", "128k", m4a], check=True)
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(seg * 0.25), "-t", "30", "-i", crudo,
                                    "-ac", "1", "-b:a", "64k", trozo], check=True)
                    oido = gemini.preguntar(OIDO.format(uso=USOS[amb]), audio=trozo, temperatura=0.2)
                except gemini.SinIA as e:
                    avisar(f"discoteca: el oído no contesta ({e}); se para aquí")
                    break
                except Exception as e:
                    avisar(f"discoteca: «{titulo}» no se ha podido bajar ({type(e).__name__})")
                    continue
                oido = oido if isinstance(oido, dict) else {}
                nota = oido.get("nota") if isinstance(oido.get("nota"), (int, float)) else 0
                vale = nota >= 6 and not oido.get("voz_cantada")
                nombre = f"{amb}-{_slug(titulo)}.m4a"
                entrada = {"nombre": nombre, "titulo": titulo, "fuente": url, "ambiente": amb,
                           "ambientes": sorted({amb, *[a for a in oido.get("sirve_para", []) if a in USOS]}),
                           "segundos": round(seg, 1), "nota": nota, "vale": vale, "suena_a": oido.get("suena_a", ""),
                           "fecha": privado.ahora()}
                if vale:
                    os.replace(m4a, os.path.join(tmp, nombre))
                    almacen.guardar(ESTANTERIA, os.path.join(tmp, nombre), nombre)
                    cuenta[amb] = cuenta.get(amb, 0) + 1
                pistas[url] = entrada
                avisar(f"discoteca: {amb} · «{titulo}» · {nota}/10 · {'se queda' if vale else 'no vale'}")
                time.sleep(2)
    privado.guardar_estado("musica/biblioteca.json", {"licencia": LICENCIA, "actualizado": privado.ahora(),
                                                      "pistas": sorted(pistas.values(), key=lambda p: p["nombre"])})
    c = privado.cuaderno("discoteca")
    c.apuntar("llenar", {"buenas": cuenta})
    c.guardar()
    gemini.apuntar_portero()
    return cuenta


def preparar(carpeta):
    """Baja las piezas buenas a una carpeta y deja MUSICA_DIR apuntando a ella (para herramientas/musica.py)."""
    lista = privado.leer(LISTA, {}) or {}
    buenas = [p for p in lista.get("pistas", []) if p.get("vale")]
    if not buenas:
        return 0
    os.makedirs(carpeta, exist_ok=True)
    almacen._gh("release", "download", ESTANTERIA, "--dir", carpeta, "--clobber")
    buenas = [p for p in buenas if os.path.exists(os.path.join(carpeta, p["nombre"]))]
    with open(os.path.join(carpeta, "biblioteca.json"), "w", encoding="utf-8") as f:
        json.dump({"licencia": LICENCIA, "pistas": buenas}, f, ensure_ascii=False)
    os.environ["MUSICA_DIR"] = os.path.abspath(carpeta)
    return len(buenas)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--por-ambiente", type=int, default=6)
    a = p.parse_args()
    cuenta = llenar(a.por_ambiente)
    print(f"discoteca: piezas buenas por ambiente: {cuenta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
