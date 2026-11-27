"""Dibuja el icono neutro del «Panel de cifras» (cuatro barras de gráfico) para la app de Meta: 1024x1024 px, PNG.

    python vuelta/hacer_icono.py            → vuelta/public/icono.png

El dueño lo descarga de <web del buzón>/icono.png. Fondo entero (sin transparencias), porque cada plataforma le pone
sus propias esquinas redondeadas.
"""
import os
import sys

from PIL import Image, ImageDraw

LADO = 1024
AUMENTO = 4                       # se dibuja 4 veces más grande y se reduce: bordes suaves
FONDO = (29, 78, 137)
BARRAS = [(0.27, (126, 196, 255)), (0.41, (164, 214, 255)), (0.35, (126, 196, 255)), (0.56, (255, 255, 255))]
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "icono.png")


def dibujar():
    lado = LADO * AUMENTO
    img = Image.new("RGB", (lado, lado), FONDO)
    d = ImageDraw.Draw(img)
    margen, base = int(lado * 0.20), int(lado * 0.76)
    hueco = int(lado * 0.05)
    ancho = (lado - 2 * margen - hueco * (len(BARRAS) - 1)) // len(BARRAS)
    radio = ancho // 4
    for i, (alto, color) in enumerate(BARRAS):
        x = margen + i * (ancho + hueco)
        d.rounded_rectangle([x, base - int(lado * alto), x + ancho, base], radius=radio, fill=color)
    grosor = int(lado * 0.018)
    d.rounded_rectangle([margen - hueco, base + hueco // 2, lado - margen + hueco, base + hueco // 2 + grosor],
                        radius=grosor // 2, fill=(255, 255, 255))
    return img.resize((LADO, LADO), Image.LANCZOS)


def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else SALIDA
    dibujar().save(ruta, "PNG", optimize=True)
    print(f"Icono guardado ({LADO}x{LADO}).")


if __name__ == "__main__":
    main()
