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


EMOCIONES = ("serio", "enfadado", "sorprendido", "contento", "triste", "pensativo")


def _emocion(escena):
    e = str(escena.get("emocion") or "").strip().lower()
    if e in EMOCIONES:
        return e
    t = str(escena.get("texto") or "")
    return "sorprendido" if "!" in t else "pensativo" if "?" in t else "serio"


PISTAS_SHOW = [   # si el guion no dice qué hace el chico, se adivina por lo que cuenta la frase (neerlandés y español)
    (("sigaret", "rook", "roken", "cigarr", "fuma", "tabaco"), "fumar", "habitacion"),
    (("voetbal", "ajax", "wk ", " wk", "doelpunt", "scoor", "fútbol", "futbol", "gol", "balón", "stadion", "estadio"), "balon", "estadio"),
    (("won", "wint", "kampioen", "beker", "goud", "cup", "medaille", "ganó", "campe", "trofeo", "oro"), "trofeo", "plato"),
    (("miljoen", "miljard", "gulden", " euro", "dollar", "geld", "rijk", "record", "betaald", "millon", "millón", "dinero", "€", "$"), "dinero", "banco"),
    (("operatie", "ziek", "hart", "ziekenhuis", "hospital", "enferm", "corazón"), None, "hospital"),
    (("bel", "telefoon", "llam", "teléfono"), "telefono", "oficina"),
    (("rende", "rennen", "sprint", "snel", "corri", "carrera"), "correr", "calle"),
    (("bedrijf", "kantoor", "baas", "directeur", "empresa", "oficina", "jefe"), None, "oficina"),
]


def _pista(texto):
    t = f" {str(texto).lower()} "
    for palabras, accion, fondo in PISTAS_SHOW:
        if any(p in t for p in palabras):
            return accion, fondo
    return None, None


def show(guion, imagenes, palabras_voz, durs, total, carpeta):
    """El Show: el chico de traje es el protagonista y la foto sale en una tarjeta (bots/estudio/show.html).
    Devuelve el vídeo mudo (sin voz ni subtítulos)."""
    tramos, t = [], 0.0
    for n, (e, d) in enumerate(zip(guion["escenas"], durs)):
        accion, fondo = _pista(e.get("texto"))
        if e.get("emocion") in ("enfadado", "triste", "sorprendido") and accion not in ("fumar",):
            accion = None                          # la cara manda: se enfada, llora o se sorprende
        tramos.append({"desde": round(t, 2), "hasta": round(t + d, 2), "emocion": _emocion(e),
                       "accion": e.get("accion") if e.get("accion") in ACCIONES_SHOW else accion or
                       ("senala" if _emocion(e) == "serio" and n % 2 else None), "foto": n,
                       "fondo": e.get("fondo") if e.get("fondo") in FONDOS_SHOW else fondo,
                       "pop": str(e.get("pop"))[:8] if e.get("pop") else None,
                       "leccion": str(e.get("leccion"))[:70] if e.get("leccion") else None,
                       "titulo_leccion": str(e.get("titulo_leccion") or "")[:8] or None})
        t += d
    k = 0
    for tr in tramos:
        if tr["leccion"] and not tr["titulo_leccion"]:
            k += 1
            tr["titulo_leccion"] = f"LES {k}" if str(guion.get("idioma", "nl")).startswith("nl") else f"LECCIÓN {k}"
    datos = os.path.join(carpeta, "show.json")
    with open(datos, "w", encoding="utf-8") as f:
        json.dump({"duracion": total, "tramos": tramos, "fotos": [os.path.abspath(i) for i in imagenes],
                   "palabras": [{"i": w["i"], "f": w["f"]} for w in palabras_voz]}, f)
    salida = os.path.join(carpeta, "imagen.mp4")
    subprocess.run(["node", os.path.join(RAIZ, "bots", "estudio", "show.js"), datos, salida, "30"], check=True, timeout=3000)
    return salida


ACCIONES_SHOW = ("senala", "dinero", "fumar", "trofeo", "telefono", "balon", "correr")
FONDOS_SHOW = ("habitacion", "oficina", "estadio", "calle", "banco", "hospital", "plato")


def narrador(guion, palabras_voz, durs, total, carpeta):
    """Graba el muñeco narrador (bots/estudio/narrador.html) con la boca al ritmo de la voz y la cara de cada escena.
    Devuelve la ruta del .mov con transparencia, o None si no se ha podido (el vídeo sale entonces sin muñeco)."""
    tramos, t = [], 0.0
    for e, d in zip(guion["escenas"], durs):
        tramos.append({"desde": round(t, 2), "hasta": round(t + d, 2), "emocion": _emocion(e)})
        t += d
    datos = os.path.join(carpeta, "narrador.json")
    with open(datos, "w", encoding="utf-8") as f:
        json.dump({"duracion": total, "tramos": tramos,
                   "palabras": [{"i": w["i"], "f": w["f"]} for w in palabras_voz]}, f)
    salida = os.path.join(carpeta, "narrador.mov")
    try:
        subprocess.run(["node", os.path.join(RAIZ, "bots", "estudio", "narrador.js"), datos, salida, "15"],
                       check=True, timeout=1200)
        return salida if os.path.exists(salida) else None
    except Exception as e:
        print(f"montador: el muñeco narrador no ha podido salir ({type(e).__name__}); va sin él", flush=True)
        return None


def montar(guion, imagenes, voz, palabras_json, salida, ambiente=None):
    tmp = tempfile.mkdtemp()
    try:
        palabras_voz = [w for w in subtitulos.cargar(palabras_json) if re.search(r"\w", w["t"])]   # sin «…» sueltos
        total = duracion(voz) + 0.4
        imagenes = rellenar(imagenes)
        durs = duraciones_escenas(guion["escenas"], [{"inicio": w["i"]} for w in palabras_voz], total)
        es_show = guion.get("narrador") == "show"
        clips = []
        # Ningún plano quieto de más: el primero se corta a 1,2 s (en el segundo 1 es cuando se va la gente) y los
        # demás, cada 2,4 s como mucho. El corte es la misma imagen con otro encuadre y otro movimiento.
        piezas = []
        for n, (img, d) in enumerate([] if es_show else trozos(imagenes, durs)):
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
        if es_show:
            show(guion, imagenes, palabras_voz, durs, total, tmp)
        else:
            with open(os.path.join(tmp, "lista.txt"), "w") as f:
                f.writelines(f"file '{c}'\n" for c in clips)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "lista.txt", "-c", "copy",
                            "imagen.mp4"], cwd=tmp, check=True)
        subtitulos.escribir_ass(palabras_voz, os.path.join(tmp, "s.ass"), mayus=True,
                                altura=900 if es_show else 820 if guion.get("narrador") else 560,
                                resalte=None)      # con muñeco, encima de su cabeza
        # Una línea por drawtext: con varias líneas en un mismo texto, el ffmpeg nuevo pinta un cuadradito en el salto.
        fuente = f":fontfile={FUENTE}" if os.path.exists(FUENTE) else ""
        mov = narrador(guion, palabras_voz, durs, total, tmp) if guion.get("narrador") and not es_show else None
        filtro = "[N:v]scale=iw*1.25:-1[nar];[0:v][nar]overlay=x=0:y=main_h-overlay_h:eof_action=pass,ass=s.ass" if mov else "[0:v]ass=s.ass"
        texto_rotulo = str(guion.get("texto_pantalla") or guion["titulo"])
        rotulo = _gancho(texto_rotulo)
        if rotulo.count("\n") >= 3 and ":" in texto_rotulo:     # muy largo: solo lo de antes de los dos puntos
            rotulo = _gancho(texto_rotulo.split(":", 1)[0])
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
        # volumen de TikTok/Instagram (unos -14 LUFS): sin esto, la voz salía a -25 y los jueces la oían floja
        filtro += f";{audio if audio.startswith('[') else '[' + audio + ']'}loudnorm=I=-14:TP=-1.5:LRA=11[voz]"
        audio = "[voz]"
        if mov:                                      # el muñeco va como última entrada
            filtro = filtro.replace("[N:v]", f"[{len(entradas) // 2}:v]", 1)
            entradas += ["-i", mov]
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas,
                        "-filter_complex", filtro, "-map", "[v]", "-map", audio, "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}",
                        "-movflags", "+faststart", os.path.abspath(salida)], cwd=tmp, check=True)
        return salida
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
