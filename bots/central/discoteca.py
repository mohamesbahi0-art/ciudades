"""La Discoteca: música de fondo de verdad, compuesta y tocada por músicos y regalada al dominio público (CC0 o «sin
derechos conocidos»), para que los vídeos no suenen a ordenador. Se puede usar gratis y sin nombrar a nadie.

Busca en el Internet Archive (archive.org, con su buscador oficial) piezas de audio cuya licencia es de dominio público,
por estilos; el oído de la Policía (Gemini) escucha 30 segundos de cada una y solo se quedan las que sirven de fondo y
no tienen voz cantada. Se guardan como archivos de la release «musica» del repositorio privado y la lista en
estado/musica/biblioteca.json. La fábrica las baja al empezar cada ronda (preparar) y herramientas/musica.py las usa;
si no hay ninguna, compone la suya.

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

ARCHIVO = "https://archive.org"
ESTANTERIA = "musica"
LISTA = os.path.join("estado", "musica", "biblioteca.json")
LICENCIA = "Dominio público (CC0 o «sin derechos conocidos») según su ficha en archive.org: uso libre y sin nombrar a nadie"
CABECERAS = {"User-Agent": "Mozilla/5.0 (compatible; music-library-fetch/1.0)"}
BUSQUEDAS = {
    "inspira": "(subject:(cinematic OR epic OR inspirational OR motivational OR orchestral OR soundtrack) OR "
               "title:(epic OR inspirational OR cinematic OR hope))",
    "energia": "(subject:(electronic OR upbeat OR \"video game\" OR chiptune OR synthwave OR action OR hiphop) OR "
               "title:(upbeat OR electronic OR action))",
    "tension": "(subject:(horror OR suspense OR \"dark ambient\" OR thriller OR mystery OR creepy) OR "
               "title:(horror OR suspense OR dark OR mystery))",
    "calma": "(subject:(piano OR ambient OR calm OR relaxing OR lofi OR chill) OR title:(piano OR ambient OR calm))",
}
USOS = {"inspira": "historias motivadoras de famosos en TikTok, con una voz contando la historia encima",
        "energia": "vídeos de videojuegos (GTA) y datos curiosos en YouTube Shorts, con voz encima",
        "tension": "historias de terror en YouTube Shorts, con voz encima",
        "calma": "vídeos informativos tranquilos, con voz encima"}
OIDO = """Escucha este trozo de 30 segundos de una música de dominio público. Queremos usarla DE FONDO, bajita, debajo de
una voz que narra, en {uso}. Sé exigente: puntúa de 1 a 10 si queda bien así (10 = perfecta y profesional; baja la nota
si suena mal grabada, a ruido, a aficionado o si no pega).
Di también si se oye ALGUNA voz humana (cantada, hablada, recitada o leída; entonces no sirve) y para cuáles de estos
usos valdría:
inspira (motivación, emoción, épica), energia (videojuegos, ritmo, curiosidades), tension (terror, misterio), calma.
Devuelve SOLO un JSON: {{"nota": 0, "hay_voz": false, "sirve_para": ["inspira"], "suena_a": "una frase"}}"""


def _pedir(url, destino=None, limite=15_000_000):
    req = urllib.request.Request(url, headers=CABECERAS)
    with urllib.request.urlopen(req, timeout=90) as r:
        datos = r.read(limite + 1)
    if len(datos) > limite:
        raise ValueError("demasiado grande")
    if destino:
        with open(destino, "wb") as f:
            f.write(datos)
        return destino
    return json.loads(datos.decode("utf-8", "replace"))


def _es_libre(licencia):
    licencia = (licencia or "").lower()
    return "publicdomain/zero" in licencia or "publicdomain/mark" in licencia


def _candidatos(ambiente, filas=40):
    """Fichas de audio con licencia de dominio público para ese ambiente, las más descargadas primero."""
    q = (f"mediatype:audio AND licenseurl:*publicdomain* AND -collection:librivoxaudio AND "
         f"-subject:(audiobook OR librivox OR poetry OR poem OR radio OR podcast OR speech OR sermon OR lecture OR "
         f"reading OR \"old time radio\") AND {BUSQUEDAS[ambiente]}")
    url = (f"{ARCHIVO}/advancedsearch.php?q={urllib.parse.quote(q)}&fl[]=identifier&fl[]=title&fl[]=licenseurl"
           f"&sort[]=downloads+desc&rows={filas}&output=json")
    docs = _pedir(url).get("response", {}).get("docs", [])
    return [d for d in docs if _es_libre(d.get("licenseurl"))]


def _pistas_de(ident, maximo=2):
    """Los mp3 de una ficha que tienen pinta de pieza musical (de 45 s a 7 min), comprobando otra vez la licencia."""
    meta = _pedir(f"{ARCHIVO}/metadata/{urllib.parse.quote(ident)}")
    if not _es_libre((meta.get("metadata") or {}).get("licenseurl")):
        return []
    buenas = []
    for f in meta.get("files", []):
        nombre = f.get("name", "")
        try:
            largo = float(f.get("length") or 0)
        except ValueError:
            largo = 0
        if nombre.lower().endswith(".mp3") and 45 <= largo <= 420 and int(f.get("size") or 0) < 15_000_000:
            buenas.append((nombre, largo, f.get("title") or nombre[:-4]))
    return buenas[:maximo]


def _segundos(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def _slug(texto):
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")[:40] or "pieza"


def llenar(por_ambiente=6, probar=10, avisar=print):
    lista = privado.leer(LISTA, {}) or {}
    pistas = {p["fuente"]: p for p in lista.get("pistas", [])}
    cuenta = {a: sum(1 for p in pistas.values() if p.get("vale") and p.get("ambiente") == a) for a in USOS}
    validas = {p["nombre"] for p in pistas.values() if p.get("vale")}
    for nombre in almacen.lista(ESTANTERIA):       # fuera de la estantería lo que no está en la lista buena
        if nombre not in validas:
            almacen.borrar(ESTANTERIA, nombre)
            avisar(f"discoteca: quitada de la estantería «{nombre[:60]}»")
    sin_oido = False
    with tempfile.TemporaryDirectory() as tmp:
        for amb in USOS:
            if sin_oido or cuenta[amb] >= por_ambiente:
                continue
            try:
                fichas = _candidatos(amb)
            except Exception as e:
                avisar(f"discoteca: el buscador no contesta para {amb} ({type(e).__name__})")
                continue
            avisar(f"discoteca: {amb}: {len(fichas)} fichas de dominio público")
            probadas = 0
            for ficha in fichas:
                if cuenta[amb] >= por_ambiente or probadas >= probar or sin_oido:
                    break
                try:
                    archivos = _pistas_de(ficha["identifier"])
                except Exception:
                    continue
                for nombre, largo, titulo in archivos:
                    url = f"{ARCHIVO}/download/{urllib.parse.quote(ficha['identifier'])}/{urllib.parse.quote(nombre)}"
                    if url in pistas or cuenta[amb] >= por_ambiente or probadas >= probar:
                        continue
                    probadas += 1
                    crudo, trozo = os.path.join(tmp, "crudo.mp3"), os.path.join(tmp, "trozo.mp3")
                    try:
                        _pedir(url, crudo)
                        seg = _segundos(crudo) or largo
                        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(seg * 0.25), "-t", "30",
                                        "-i", crudo, "-ac", "1", "-b:a", "64k", trozo], check=True)
                        oido = gemini.preguntar(OIDO.format(uso=USOS[amb]), audio=trozo, temperatura=0.2)
                    except gemini.SinIA as e:
                        avisar(f"discoteca: el oído no contesta ({str(e)[:80]}); se para aquí")
                        sin_oido = True
                        break
                    except Exception as e:
                        avisar(f"discoteca: «{titulo[:50]}» no se ha podido bajar ({type(e).__name__})")
                        continue
                    oido = oido if isinstance(oido, dict) else {}
                    nota = oido.get("nota") if isinstance(oido.get("nota"), (int, float)) else 0
                    vale = nota >= 6 and oido.get("hay_voz") is False
                    archivo = f"{amb}-{_slug(ficha['identifier'])[:30]}-{_slug(titulo)[:40]}.m4a"
                    pistas[url] = {"nombre": archivo, "titulo": str(titulo)[:120], "ficha": f"{ARCHIVO}/details/{ficha['identifier']}",
                                   "fuente": url, "licencia": ficha.get("licenseurl"), "ambiente": amb,
                                   "ambientes": sorted({amb, *[a for a in oido.get("sirve_para", []) if a in USOS]}),
                                   "segundos": round(seg, 1), "nota": nota, "vale": vale,
                                   "suena_a": str(oido.get("suena_a", ""))[:160], "fecha": privado.ahora()}
                    if vale:
                        try:
                            m4a = os.path.join(tmp, archivo)
                            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", crudo, "-ac", "2", "-c:a", "aac",
                                            "-b:a", "128k", m4a], check=True)
                            almacen.guardar(ESTANTERIA, m4a, archivo)
                            cuenta[amb] += 1
                        except Exception as e:
                            pistas[url]["vale"] = False
                            avisar(f"discoteca: «{str(titulo)[:50]}» no se ha podido guardar ({type(e).__name__})")
                    avisar(f"discoteca: {amb} · «{str(titulo)[:50]}» · {nota}/10 · {'se queda' if vale else 'no vale'}"
                           f" · {str(oido.get('suena_a', ''))[:70]}")
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
    p.add_argument("--probar", type=int, default=10, help="cuántas piezas escucha como mucho por ambiente")
    a = p.parse_args()
    cuenta = llenar(a.por_ambiente, a.probar)
    print(f"discoteca: piezas buenas por ambiente: {cuenta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
