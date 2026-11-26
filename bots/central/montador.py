"""El Montador: junta dibujos, voz y subtítulos en un Short vertical 1080x1920.
Cada dibujo se mueve despacio (acercándose o alejándose) mientras suena su trozo de narración; arriba sale el texto
gancho los 2,5 primeros segundos y abajo los subtítulos palabra a palabra."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import musica  # noqa: E402  (herramientas/musica.py)
import subtitulos  # noqa: E402  (herramientas/subtitulos.py)

FPS = 30
FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def duracion(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def duraciones_escenas(escenas, palabras_voz, total):
    """Cada escena dura lo que tarda la voz en decir sus palabras."""
    cuentas = [max(1, len(re.findall(r"\w+", e["texto"]))) for e in escenas]
    escala = len(palabras_voz) / sum(cuentas) if palabras_voz else 0
    inicios, acumulado = [], 0
    for c in cuentas:
        k = min(len(palabras_voz) - 1, int(round(acumulado * escala))) if palabras_voz else 0
        inicios.append(0.0 if not inicios or not palabras_voz else palabras_voz[k]["inicio"])
        acumulado += c
    duraciones = [(inicios[i + 1] if i + 1 < len(inicios) else total) - inicios[i] for i in range(len(inicios))]
    return [max(1.0, d) for d in duraciones]


def rellenar(imagenes):
    """Si falta algún dibujo, usa el de al lado."""
    hay = [i for i in imagenes if i]
    if not hay:
        raise ValueError("No hay ningún dibujo")
    salida, ultimo = [], None
    for i, img in enumerate(imagenes):
        ultimo = img or ultimo or next(x for x in imagenes[i:] if x)
        salida.append(ultimo)
    return salida


def trozos(imagenes, duraciones, primero=2.5, maximo=3.5):
    """Parte las escenas largas para que la imagen cambie a menudo (el Juzgado lo pidió: un primer cambio tardío hace
    que la gente se vaya). El primer cambio llega a los 2,5 s y ninguna toma dura más de unos 3,5 s."""
    segmentos = []
    for n, (img, d) in enumerate(zip(imagenes, duraciones)):
        partes, resto = [], d
        if n == 0 and d > primero + 1.0:
            partes.append(primero)
            resto -= primero
        while resto > maximo + 1.0:
            partes.append(maximo)
            resto -= maximo
        partes.append(resto)
        segmentos += [(img, p) for p in partes]
    return segmentos


MOVIMIENTOS = [   # cada toma empieza con un encuadre distinto de cómo acabó la anterior, para que se note el cambio
    ("1+0.12*on/{c}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),            # se acerca despacio
    ("1.40-0.10*on/{c}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),         # salto a primer plano
    ("1.20", "(iw-iw/zoom)*on/{c}", "ih/2-(ih/zoom/2)"),                   # barrido de izquierda a derecha
]


PRIMER_CORTE = 1.2        # segundos del primer plano
PLANO_MAXIMO = 2.4        # segundos que dura un plano como mucho


def _gancho(texto, ancho_max=15):
    # sin emojis ni símbolos raros: la letra del rótulo no los tiene y salían como un recuadro roto
    texto = "".join(c for c in str(texto) if ord(c) < 0x2190 and c not in "#").strip() or str(texto)
    lineas, actual = [], ""
    for p in texto.upper().split():
        if actual and len(actual) + 1 + len(p) > ancho_max:
            lineas.append(actual)
            actual = p
        else:
            actual = f"{actual} {p}".strip()
    return "\n".join(lineas + [actual])


def _repite_voz(rotulo, palabras_voz, segundos=2.5):
    """¿El rótulo de arriba repite lo que dice la voz en esos mismos segundos? Entonces sobra (sale el texto dos veces)."""
    norm = lambda t: re.sub(r"[^\w]", "", str(t).lower())
    del_rotulo = {norm(w) for w in str(rotulo).split() if len(norm(w)) > 2}
    dichas = {norm(w["t"]) for w in palabras_voz if w["i"] < segundos}
    return bool(del_rotulo) and len(del_rotulo & dichas) * 2 >= len(del_rotulo)


def montar(guion, imagenes, voz, palabras_json, salida, ambiente=None):
    tmp = tempfile.mkdtemp()
    try:
        palabras_voz = subtitulos.cargar(palabras_json)
        total = duracion(voz) + 0.4
        imagenes = rellenar(imagenes)
        durs = duraciones_escenas(guion["escenas"], [{"inicio": w["i"]} for w in palabras_voz], total)
        clips = []
        # Ningún plano quieto de más: el primero se corta a 1,2 s (en el segundo 1 es cuando se va la gente) y los
        # demás, cada 2,4 s como mucho. El corte es la misma imagen con otro encuadre y otro movimiento.
        piezas = []
        for n, (img, d) in enumerate(trozos(imagenes, durs)):
            tope = PRIMER_CORTE if n == 0 else PLANO_MAXIMO
            if d > tope + 0.5:
                partes = [PRIMER_CORTE] if n == 0 else []
                resto = d - sum(partes)
                cuantas = max(1, int(-(-resto // PLANO_MAXIMO)))
                partes += [resto / cuantas] * cuantas
                piezas += [(img, x) for x in partes]
            else:
                piezas.append((img, d))
        for n, (img, d) in enumerate(piezas):
            cuadros = max(1, round(d * FPS))
            zoom, x, y = (m.format(c=cuadros) for m in MOVIMIENTOS[n % len(MOVIMIENTOS)])
            clip = os.path.join(tmp, f"c{n:02d}.mp4")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", img, "-vf",
                            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,scale=2160:3840,"
                            f"zoompan=z='{zoom}':x='{x}':y='{y}':d={cuadros}:s=1080x1920:fps={FPS},"
                            "format=yuv420p", "-frames:v", str(cuadros), "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "20", clip], check=True)
            clips.append(clip)
        with open(os.path.join(tmp, "lista.txt"), "w") as f:
            f.writelines(f"file '{c}'\n" for c in clips)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "lista.txt", "-c", "copy",
                        "imagen.mp4"], cwd=tmp, check=True)
        subtitulos.escribir_ass(palabras_voz, os.path.join(tmp, "s.ass"), mayus=True)
        # Una línea por drawtext: con varias líneas en un mismo texto, el ffmpeg nuevo pinta un cuadradito en el salto.
        fuente = f":fontfile={FUENTE}" if os.path.exists(FUENTE) else ""
        filtro = "[0:v]ass=s.ass"
        rotulo = _gancho(guion.get("texto_pantalla") or guion["titulo"])
        if _repite_voz(rotulo, palabras_voz):     # el rótulo diría lo mismo que el subtítulo a la vez: los jueces lo ven doble
            rotulo = ""
        for n, linea in enumerate(rotulo.split("\n") if rotulo else []):
            with open(os.path.join(tmp, f"gancho{n}.txt"), "w", encoding="utf-8") as f:
                f.write(linea)
            filtro += (f",drawtext=textfile=gancho{n}.txt" + fuente +
                       ":fontsize=88:fontcolor=white:borderw=8:bordercolor=black"
                       f":x=(w-text_w)/2:y=h*0.13+{n * 104}:enable='lt(t,2.5)'")
        filtro += "[v]"
        entradas = ["-i", "imagen.mp4", "-i", os.path.abspath(voz)]
        audio = "1:a"
        pista = musica.crear(ambiente, total, os.path.join(tmp, "musica.m4a")) if ambiente else None
        if pista:                                    # música propia, muy por debajo de la voz
            entradas += ["-i", pista]
            filtro += ";[2:a]volume=0.35[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
            audio = "[a]"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas,
                        "-filter_complex", filtro, "-map", "[v]", "-map", audio, "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}",
                        "-movflags", "+faststart", os.path.abspath(salida)], cwd=tmp, check=True)
        return salida
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
