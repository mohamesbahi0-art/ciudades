"""Subtítulos virales palabra a palabra (estilo karaoke) para vídeos verticales, gratis.

Lee las palabras con sus tiempos (de voz.py o de transcribir.py) y escribe un archivo .ass:
frases de 1 a 3 palabras, letra gruesa con borde negro y la palabra que suena en amarillo
y un poco más grande. Opcionalmente las quema en el vídeo con ffmpeg.

Uso:
  python subtitulos.py palabras.json --ass subs.ass [--video entrada.mp4 --salida final.mp4]
  Para un clip recortado: --desde 83.4 --hasta 109.9 (usa solo ese trozo y lo pone a contar desde 0)
  Opciones: --palabras-por-frase 3  --mayusculas  --fuente "DejaVu Sans"  --tamano 92  --altura 560
Acepta palabras como {"palabra","inicio","fin"} o {"word","start","end"}.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile

AMARILLO, BLANCO, NEGRO = "&H0000FFFF&", "&H00FFFFFF&", "&H00000000&"
FIN_FRASE = tuple(".,;:!?¡¿…")


def cargar(ruta, desde=None, hasta=None):
    """Lee las palabras. Con desde/hasta se queda solo con ese trozo y lo pone a contar desde 0 (para clips)."""
    datos = json.load(open(ruta, encoding="utf-8"))
    if isinstance(datos, dict):
        datos = datos.get("palabras") or datos.get("words") or []
    out = []
    for w in datos:
        txt = str(w.get("palabra", w.get("word", ""))).strip()
        ini = float(w.get("inicio", w.get("start", 0)))
        fin = float(w.get("fin", w.get("end", ini + 0.3)))
        if desde is not None:
            if ini < desde - 0.05 or (hasta is not None and fin > hasta + 0.05):
                continue
            ini, fin = ini - desde, fin - desde
        if txt:
            out.append({"t": txt.replace("{", "(").replace("}", ")"), "i": ini, "f": max(fin, ini + 0.05)})
    return out


def frases(palabras, maximo):
    grupo = []
    for n, w in enumerate(palabras):
        grupo.append(w)
        sig = palabras[n + 1] if n + 1 < len(palabras) else None
        # un número va con la palabra de antes («GTA 6», «capítulo 3»), aunque la frase se pase de largo
        numero_detras = sig is not None and sig["t"].strip(".,!?").isdigit() and sig["i"] - w["f"] < 0.35
        corte = (len(grupo) >= maximo and not numero_detras) or w["t"].endswith(FIN_FRASE) \
            or (sig is not None and sig["i"] - w["f"] > 0.35)
        if corte or sig is None:
            yield grupo
            grupo = []


def tiempo(s):
    s = max(0.0, s)
    h, r = divmod(s, 3600)
    m, r = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{r:05.2f}"


def escribir_ass(palabras, ruta, maximo=3, mayus=False, fuente="DejaVu Sans", tamano=92, altura=560, resalte=None):
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Viral,{fuente},{tamano},{BLANCO},{BLANCO},{NEGRO},&H80000000&,-1,0,0,0,100,100,0,0,1,7,3,2,90,90,{altura},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lineas = []
    lista = list(frases(palabras, maximo))
    for k, g in enumerate(lista):
        fin_grupo = g[-1]["f"] + 0.15
        if k + 1 < len(lista):
            fin_grupo = min(fin_grupo, lista[k + 1][0]["i"])
        for j, w in enumerate(g):
            ini = w["i"]
            fin = g[j + 1]["i"] if j + 1 < len(g) else fin_grupo
            if fin <= ini:
                continue
            trozos = []
            for x, v in enumerate(g):
                t = v["t"].upper() if mayus else v["t"]
                trozos.append("{\\c" + (resalte or AMARILLO) + "\\fscx112\\fscy112}" + t + "{\\r}" if x == j else t)
            lineas.append(f"Dialogue: 0,{tiempo(ini)},{tiempo(fin)},Viral,,0,0,0,,{' '.join(trozos)}")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(cab + "\n".join(lineas) + "\n")
    return len(lineas)


def quemar(video, ass, salida):
    if not shutil.which("ffmpeg"):
        sys.exit("Falta ffmpeg.")
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(ass, os.path.join(tmp, "s.ass"))
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.abspath(video), "-vf", "ass=s.ass",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy",
               os.path.abspath(salida)]
        subprocess.run(cmd, cwd=tmp, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("palabras")
    p.add_argument("--ass", required=True)
    p.add_argument("--video")
    p.add_argument("--salida")
    p.add_argument("--palabras-por-frase", dest="maximo", type=int, default=3)
    p.add_argument("--mayusculas", action="store_true")
    p.add_argument("--fuente", default="DejaVu Sans")
    p.add_argument("--tamano", type=int, default=92)
    p.add_argument("--altura", type=int, default=560, help="distancia al borde de abajo, en píxeles de 1920")
    p.add_argument("--desde", type=float, help="para un clip: segundo del vídeo original donde empieza")
    p.add_argument("--hasta", type=float, help="para un clip: segundo donde acaba")
    a = p.parse_args()
    n = escribir_ass(cargar(a.palabras, a.desde, a.hasta), a.ass, a.maximo, a.mayusculas, a.fuente, a.tamano, a.altura)
    print(f"OK {n} líneas de subtítulos en {a.ass}")
    if a.video:
        if not a.salida:
            sys.exit("Con --video hace falta --salida.")
        quemar(a.video, a.ass, a.salida)
        print(f"OK vídeo con subtítulos: {a.salida}")


if __name__ == "__main__":
    main()
