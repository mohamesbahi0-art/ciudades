"""Voz gratis con edge-tts y el momento exacto de cada palabra (para los subtítulos).

Uso:
  python voz.py --texto "Nadie se dio cuenta..." --salida carpeta/        (o --archivo guion.txt)
  Opciones: --voz es-MX-JorgeNeural  --velocidad +10%  --tono +0Hz
Deja en la carpeta: voz.mp3 y palabras.json ([{"palabra","inicio","fin"}] en segundos).
Si la máquina pasa por un proxy con certificado propio, pon su CA en la variable EDGE_TTS_CA.
"""
import argparse, asyncio, json, os, ssl, sys

import edge_tts
import edge_tts.communicate as ec


async def generar(texto, voz, velocidad, tono, carpeta):
    if os.environ.get("EDGE_TTS_CA"):
        ec._SSL_CTX = ssl.create_default_context(cafile=os.environ["EDGE_TTS_CA"])
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    com = edge_tts.Communicate(texto, voz, rate=velocidad, pitch=tono, boundary="WordBoundary", proxy=proxy)
    palabras = []
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "voz.mp3"), "wb") as audio:
        async for trozo in com.stream():
            if trozo["type"] == "audio":
                audio.write(trozo["data"])
            elif trozo["type"] == "WordBoundary":
                ini = trozo["offset"] / 1e7
                palabras.append({"palabra": trozo["text"], "inicio": round(ini, 3),
                                 "fin": round(ini + trozo["duration"] / 1e7, 3)})
    with open(os.path.join(carpeta, "palabras.json"), "w", encoding="utf-8") as f:
        json.dump(palabras, f, ensure_ascii=False, indent=1)
    return palabras


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--texto")
    g.add_argument("--archivo")
    p.add_argument("--salida", required=True)
    p.add_argument("--voz", default="es-MX-JorgeNeural")
    p.add_argument("--velocidad", default="+10%")
    p.add_argument("--tono", default="+0Hz")
    a = p.parse_args()
    texto = a.texto if a.texto else open(a.archivo, encoding="utf-8").read()
    palabras = asyncio.run(generar(texto.strip(), a.voz, a.velocidad, a.tono, a.salida))
    if not palabras:
        sys.exit("No llegó ninguna palabra: revisa el texto o la conexión.")
    print(f"OK voz.mp3 y {len(palabras)} palabras en {a.salida}")


if __name__ == "__main__":
    main()
