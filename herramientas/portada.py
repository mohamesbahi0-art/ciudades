"""Portadas y miniaturas gratis (versión casera de los creadores de miniaturas de pago).

Hace una imagen con un fondo (foto, fotograma de vídeo o color), un degradado oscuro para que se lea
el texto y 2-5 palabras enormes con borde negro. La palabra entre *asteriscos* sale en color.

Uso:
  python portada.py --texto "El *detalle* que nadie vio" --salida portada.png
  Opciones: --fondo foto.jpg | --fondo video.mp4 --segundo 2.5 | (sin fondo: color liso)
            --formato short (1080x1920, también sirve de primer fotograma) | largo (1280x720)
            --color "#FFD400" (la palabra destacada)  --fondo-color "#14202E"  --fuente ruta.ttf
"""
import argparse, os, re, subprocess, tempfile

from PIL import Image, ImageDraw, ImageFont

TAMANOS = {"short": (1080, 1920), "largo": (1280, 720)}
FUENTES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
           "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
           "C:/Windows/Fonts/arialbd.ttf"]


def fuente(ruta, tam):
    for f in ([ruta] if ruta else []) + FUENTES:
        if f and os.path.exists(f):
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default(tam)


def fondo(origen, segundo, tam, color):
    if not origen:
        return Image.new("RGB", tam, color)
    if origen.lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
        tmp = os.path.join(tempfile.mkdtemp(), "f.png")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(segundo), "-i", origen, "-frames:v", "1", tmp],
                       check=True)
        origen = tmp
    img = Image.open(origen).convert("RGB")
    esc = max(tam[0] / img.width, tam[1] / img.height)
    img = img.resize((round(img.width * esc), round(img.height * esc)), Image.LANCZOS)
    x, y = (img.width - tam[0]) // 2, (img.height - tam[1]) // 2
    return img.crop((x, y, x + tam[0], y + tam[1]))


def oscurecer(img, formato):
    w, h = img.size
    capa = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(capa)
    for i in range(h):
        if formato == "short":   # más oscuro en el centro, donde va el texto
            t = 1 - abs(i - h * 0.42) / (h * 0.42)
        else:                    # más oscuro abajo
            t = i / h
        d.line([(0, i), (w, i)], fill=int(170 * max(0.0, min(1.0, t))))
    negro = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(negro, img, capa)


def partir(palabras, f, ancho, draw):
    lineas, actual = [], []
    for p in palabras:
        prueba = " ".join(x for x, _ in actual + [p])
        if actual and draw.textlength(prueba, font=f) > ancho:
            lineas.append(actual)
            actual = [p]
        else:
            actual.append(p)
    if actual:
        lineas.append(actual)
    return lineas


def componer(texto, tam, formato, color, ruta_fuente, img):
    draw = ImageDraw.Draw(img)
    palabras, dentro = [], False
    for t in texto.split():                      # *una o varias palabras* entre asteriscos van en color
        sin_signos = t.rstrip(".,;:!?…")
        empieza, acaba = t.startswith("*"), sin_signos.endswith("*") and len(sin_signos) > 1
        if empieza:
            dentro = True
        limpia = t.replace("*", "").upper()
        if limpia.isdigit() and palabras:        # «GTA 6» no se separa en dos líneas
            prev, col = palabras[-1]
            palabras[-1] = (prev + "\u00a0" + limpia, col or dentro)
        elif limpia:
            palabras.append((limpia, dentro))
        if acaba:
            dentro = False
    ancho = tam[0] * 0.86
    for t in range(int(tam[1] * (0.11 if formato == "short" else 0.2)), 20, -4):
        f = fuente(ruta_fuente, t)
        lineas = partir(palabras, f, ancho, draw)
        alto = len(lineas) * t * 1.08
        mas_ancha = max(draw.textlength(" ".join(p for p, _ in l), font=f) for l in lineas)
        if len(lineas) <= 3 and mas_ancha <= ancho and alto < tam[1] * (0.4 if formato == "short" else 0.75):
            break
    borde = max(4, t // 12)
    y = tam[1] * (0.42 if formato == "short" else 0.5) - alto / 2
    for linea in lineas:
        frase = " ".join(p for p, _ in linea)
        x = (tam[0] - draw.textlength(frase, font=f)) / 2
        for p, destacada in linea:
            draw.text((x, y), p, font=f, fill=color if destacada else "white", stroke_width=borde, stroke_fill="black")
            x += draw.textlength(p + " ", font=f)
        y += t * 1.08
    return img


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--texto", required=True)
    a.add_argument("--salida", required=True)
    a.add_argument("--fondo")
    a.add_argument("--segundo", type=float, default=1.0)
    a.add_argument("--formato", choices=TAMANOS, default="short")
    a.add_argument("--color", default="#FFD400")
    a.add_argument("--fondo-color", dest="fondo_color", default="#14202E")
    a.add_argument("--fuente")
    o = a.parse_args()
    tam = TAMANOS[o.formato]
    img = oscurecer(fondo(o.fondo, o.segundo, tam, o.fondo_color), o.formato)
    componer(o.texto, tam, o.formato, o.color, o.fuente, img).save(o.salida)
    print(f"OK portada {tam[0]}x{tam[1]}: {o.salida}")


if __name__ == "__main__":
    main()
