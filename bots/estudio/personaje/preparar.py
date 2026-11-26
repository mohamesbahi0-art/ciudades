"""Prepara el personaje de El Show a partir de los dibujos hechos con IA (una vez; no corre en la fábrica).

Entrada: una carpeta con las poses (pose.png, 1024x1536, fondo transparente) y otra con la misma pose con la boca
abierta (bocas/pose.png). Salida, en bots/estudio/personaje/:
  - <pose>.webp: la pose, puesta con los ojos en el mismo sitio y la cabeza del mismo tamaño que la pose base
    (así, al cambiar de pose, la cabeza no salta), con el traje alargado hacia abajo hasta el borde;
  - <pose>-boca.webp: solo el trozo de la boca abierta, para hablar (se pone encima de la pose);
  - personaje.json: medidas de cada pose (ojos para parpadear, boca, sitio del trozo de la boca).

Uso: python3 preparar.py carpeta_poses carpeta_bocas
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

AQUI = os.path.dirname(os.path.abspath(__file__))
ANCHO, ALTO = 1200, 1800          # lienzo común (con margen para brazos levantados)
MARGEN_X, MARGEN_Y = 88, 264      # dónde cae el dibujo base dentro del lienzo
SALIDA_ESCALA = 0.62              # tamaño final de los dibujos (de sobra para 1080x1920)
BASE = "explica"
# Sitios de cosas que llevan en la mano, medidos en el dibujo original (de ahí salen el humo y los billetes que vuelan).
ANCLAS = {"fumar": {"brasa": (41, 567)}, "dinero": {"billetes": (228, 632)}}

# Ojos que el buscador automático no encuentra bien (ojos entornados o una taza blanca al lado): centro de cada ojo
# y ancho medio, medidos a mano en el dibujo original.
OJOS_A_MANO = {
    "dinero": [(477, 570, 93, 101), (620, 595, 97, 58)],     # el izquierdo, abierto; el derecho, entornado
    "fumar": [(378, 435, 102), (548, 437, 132)],
    "beber": [(395, 466, 110), (571, 473, 134)],
}


def ojos(im):
    """Los dos ojos: manchas blancas grandes, redondas y a la misma altura. Devuelve [(cx, cy, ancho), ...] o None."""
    a = im[..., 3] > 200
    blanco = a & (im[..., 0] > 228) & (im[..., 1] > 228) & (im[..., 2] > 228)
    top = np.nonzero(a)[0].min()
    lab, _ = ndimage.label(blanco)
    cands = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        area = (lab[sl] == i).sum()
        if area < 1500 or h < 40 or w < 40 or area / (h * w) < 0.55 or not 0.7 < h / w < 1.8:
            continue
        cy, cx = ndimage.center_of_mass(lab == i)
        cands.append(dict(cx=cx, cy=cy, w=w, h=h, area=area))
    mejor = None
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            p, q = cands[i], cands[j]
            dx, dy = abs(p["cx"] - q["cx"]), abs(p["cy"] - q["cy"])
            if dx < 60 or dx > 400 or dy > 0.6 * dx:
                continue
            nota = min(p["area"], q["area"]) / max(p["area"], q["area"]) - dy / dx - (min(p["cy"], q["cy"]) - top) / 3000
            if not mejor or nota > mejor[0]:
                mejor = (nota, p, q)
    if not mejor:
        return None
    _, p, q = mejor
    return [(o["cx"], o["cy"], o["w"], o["h"]) for o in sorted((p, q), key=lambda o: o["cx"])]


def medidas(nombre, im):
    if nombre in OJOS_A_MANO:
        return [(e[0], e[1], e[2], e[3] if len(e) > 3 else e[2] * 0.6) for e in OJOS_A_MANO[nombre]], False
    o = ojos(im)
    if not o:
        raise SystemExit(f"{nombre}: no encuentro los ojos")
    return o, True


def colocar(im, escala, dx, dy):
    """Escala y mueve el dibujo dentro del lienzo común."""
    img = Image.fromarray(im.astype("uint8"), "RGBA")
    w, h = int(round(img.width * escala)), int(round(img.height * escala))
    img = img.resize((w, h), Image.LANCZOS)
    lienzo = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    lienzo.alpha_composite(img, (int(round(dx)), int(round(dy))))
    return lienzo


def alargar(lienzo, centro_x):
    """Si el cuerpo se corta antes del borde de abajo (pose más pequeña), alarga SOLO el tronco (la franja del traje que
    pasa por el centro) repitiendo su última fila; las manos que cuelgan se quedan como están, encima."""
    a = np.asarray(lienzo).copy()
    cx = int(round(centro_x))
    col = np.nonzero(a[:, cx, 3] > 200)[0]
    if not len(col):
        return lienzo
    yb = int(col.max()) - 6                       # un poco por encima del borde (que es semitransparente)
    if yb >= ALTO - 10:
        return lienzo
    fila = a[yb]
    opaca = fila[:, 3] > 200
    x0 = cx
    while x0 > 0 and opaca[x0 - 1]:
        x0 -= 1
    x1 = cx
    while x1 < ANCHO - 1 and opaca[x1 + 1]:
        x1 += 1
    tira = fila[x0:x1 + 1].copy()
    tira[:, 3] = 255
    relleno = np.zeros((ALTO - yb, ANCHO, 4), dtype=np.uint8)
    relleno[:, x0:x1 + 1] = tira[None]
    fondo = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    fondo.paste(Image.fromarray(relleno, "RGBA"), (0, yb))
    fondo.alpha_composite(lienzo)                 # el dibujo original manda encima del relleno
    return fondo


def trozo_boca(cerrada, abierta, cx, cy, radio):
    """El trozo que cambia entre la boca cerrada y la abierta, con el borde suave. Devuelve (imagen, x, y)."""
    c = np.asarray(cerrada).astype(int)
    b = np.asarray(abierta).astype(int)
    dif = np.abs(c - b)[..., :3].sum(axis=2) > 120
    zona = np.zeros_like(dif)
    y0, y1 = int(cy - radio * 0.4), int(cy + radio * 1.6)
    x0, x1 = int(cx - radio * 1.3), int(cx + radio * 1.3)
    zona[max(0, y0):y1, max(0, x0):x1] = True
    dif &= zona
    dif = ndimage.binary_opening(dif, iterations=2)
    lab, n = ndimage.label(dif)
    if not n:
        return None
    tam = ndimage.sum(dif, lab, range(1, n + 1))
    grande = lab == (int(np.argmax(tam)) + 1)
    # lo que esté cerca de la mancha más grande también (dientes y lengua sueltos)
    cerca = ndimage.binary_dilation(grande, iterations=25)
    masc = ndimage.binary_dilation(dif & cerca, iterations=14)
    masc = ndimage.binary_fill_holes(masc)
    m = Image.fromarray((masc * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(6))
    ys, xs = np.nonzero(np.asarray(m) > 4)
    bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    pieza = Image.fromarray(b[by0:by1, bx0:bx1].astype("uint8"), "RGBA")
    alfa = np.minimum(np.asarray(pieza)[..., 3], np.asarray(m)[by0:by1, bx0:bx1])
    pieza.putalpha(Image.fromarray(alfa.astype("uint8")))
    return pieza, int(bx0), int(by0)


def main():
    poses_dir, bocas_dir = sys.argv[1], sys.argv[2]
    nombres = sorted(n[:-4] for n in os.listdir(poses_dir) if n.endswith(".png") and not n.startswith("_"))
    base = np.asarray(Image.open(os.path.join(poses_dir, BASE + ".png")).convert("RGBA")).astype(int)
    ob, _ = medidas(BASE, base)
    mid_b = ((ob[0][0] + ob[1][0]) / 2, (ob[0][1] + ob[1][1]) / 2)
    dist_b = ob[1][0] - ob[0][0]
    anch_b = (ob[0][2] + ob[1][2]) / 2
    datos = {"lienzo": [round(ANCHO * SALIDA_ESCALA), round(ALTO * SALIDA_ESCALA)], "poses": {}}
    for n in nombres:
        im = np.asarray(Image.open(os.path.join(poses_dir, n + ".png")).convert("RGBA")).astype(int)
        o, auto = medidas(n, im)
        dist = o[1][0] - o[0][0]
        anch = (o[0][2] + o[1][2]) / 2
        esc = (dist_b / dist + anch_b / anch) / 2
        esc = min(1.4, max(0.78, esc))
        mid = ((o[0][0] + o[1][0]) / 2, (o[0][1] + o[1][1]) / 2)
        dx = MARGEN_X + mid_b[0] - mid[0] * esc
        dy = MARGEN_Y + mid_b[1] - mid[1] * esc
        k = SALIDA_ESCALA
        centro = MARGEN_X + mid_b[0] - dist_b * 0.25     # la camisa y la corbata, algo a la izquierda de los ojos
        cerrada = alargar(colocar(im, esc, dx, dy), centro)
        cerrada_s = cerrada.resize((round(ANCHO * k), round(ALTO * k)), Image.LANCZOS)
        cerrada_s.save(os.path.join(AQUI, f"{n}.webp"), "WEBP", quality=90, method=6)
        ojos_fin = [{"x": round((x * esc + dx) * k, 1), "y": round((y * esc + dy) * k, 1),
                     "rx": round(w * esc * k / 2, 1), "ry": round(h * esc * k / 2, 1)} for x, y, w, h in o]
        # color de la piel (para el párpado al parpadear): la mejilla, debajo de cada ojo
        arr = np.asarray(cerrada)
        muestras = []
        for x, y, w, h in o:
            X, Y = int(x * esc + dx), int(y * esc + dy + h * esc * 0.95)
            caja = arr[Y:Y + 24, X - 18:X + 18].reshape(-1, 4)
            caja = caja[(caja[:, 3] > 220) & (caja[:, :3].sum(axis=1) > 380)]
            if len(caja):
                muestras.append(np.median(caja[:, :3], axis=0))
        piel = np.median(muestras, axis=0) if muestras else np.array([240, 180, 130])
        ficha = {"escala": round(esc, 3), "ojos": ojos_fin, "ojos_redondos": auto,
                 "piel": "#%02X%02X%02X" % tuple(int(v) for v in piel)}
        for clave, (ax, ay) in ANCLAS.get(n, {}).items():
            ficha[clave] = [round((ax * esc + dx) * k, 1), round((ay * esc + dy) * k, 1)]
        ruta_boca = os.path.join(bocas_dir, n + ".png")
        if os.path.isfile(ruta_boca):
            ab = np.asarray(Image.open(ruta_boca).convert("RGBA")).astype(int)
            abierta = alargar(colocar(ab, esc, dx, dy), centro)
            ojo_d = (dist_b) * 1.0
            # la boca está debajo de los ojos: ~1,05 veces la distancia entre ojos más abajo
            bcx, bcy = MARGEN_X + mid_b[0], MARGEN_Y + mid_b[1] + ojo_d * 0.95
            r = trozo_boca(cerrada, abierta, bcx, bcy, ojo_d * 0.75)
            if r:
                pieza, px, py = r
                pieza = pieza.resize((max(1, round(pieza.width * k)), max(1, round(pieza.height * k))), Image.LANCZOS)
                pieza.save(os.path.join(AQUI, f"{n}-boca.webp"), "WEBP", quality=92, method=6)
                ficha["boca"] = {"x": round(px * k, 1), "y": round(py * k, 1), "w": pieza.width, "h": pieza.height}
        datos["poses"][n] = ficha
        print(n, "escala", ficha["escala"], "boca" if "boca" in ficha else "SIN BOCA")
    datos["cabeza"] = {"x": round((MARGEN_X + mid_b[0]) * SALIDA_ESCALA, 1),
                       "y": round((MARGEN_Y + mid_b[1]) * SALIDA_ESCALA, 1),
                       "ojos": round(dist_b * SALIDA_ESCALA, 1)}
    with open(os.path.join(AQUI, "personaje.json"), "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
