"""Voz con el momento exacto de cada palabra (para los subtítulos y para encajar las escenas).

Dos motores:
- edge-tts (gratis, por defecto): voces como es-ES-AlvaroNeural.
- ElevenLabs (voces más naturales): voz "eleven:<id de la voz>" y el secreto ELEVENLABS_API_KEY. Si falta la llave o
  se acaba el saldo del mes, sale sola la voz gratis de siempre (y lo dice), para que la fábrica nunca se pare.

Uso:
  python voz.py --texto "Nadie se dio cuenta..." --salida carpeta/        (o --archivo guion.txt)
  Opciones: --voz es-MX-JorgeNeural  --velocidad +10%  --tono +0Hz
Deja en la carpeta: voz.mp3 y palabras.json ([{"palabra","inicio","fin"}] en segundos).
Si la máquina pasa por un proxy con certificado propio, pon su CA en la variable EDGE_TTS_CA.
"""
import argparse, asyncio, base64, json, os, ssl, sys, urllib.error, urllib.request

import edge_tts
import edge_tts.communicate as ec


VOZ_GRATIS = "es-ES-AlvaroNeural"
MOTOR = {}          # qué motor sonó la última vez (para apuntarlo): {"motor": "elevenlabs"|"edge", "aviso": ...}


def _eleven(texto, voz_id, velocidad, carpeta):
    """ElevenLabs con tiempos por letra; los junta en palabras. Lanza RuntimeError si no se puede."""
    clave = os.environ.get("ELEVENLABS_API_KEY")
    if not clave:
        raise RuntimeError("falta el secreto ELEVENLABS_API_KEY")
    try:
        rapidez = max(0.7, min(1.2, 1 + float(str(velocidad).strip().rstrip("%") or 0) / 100))
    except ValueError:
        rapidez = 1.0
    cuerpo = {"text": texto, "model_id": os.environ.get("ELEVENLABS_MODELO", "eleven_multilingual_v2"),
              "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True,
                                 "speed": rapidez}}
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{voz_id}/with-timestamps"
                                 "?output_format=mp3_44100_128", data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"xi-api-key": clave, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        detalle = e.read()[:200].decode("utf-8", "replace")
        raise RuntimeError(f"ElevenLabs dice {e.code}: {detalle}")
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "voz.mp3"), "wb") as f:
        f.write(base64.b64decode(d["audio_base64"]))
    al = d.get("alignment") or d.get("normalized_alignment") or {}
    letras, inis, fins = al.get("characters", []), al.get("character_start_times_seconds", []), al.get("character_end_times_seconds", [])
    palabras, actual = [], None
    for c, a, b in zip(letras, inis, fins):
        if c.isspace():
            if actual:
                palabras.append(actual)
            actual = None
        elif actual is None:
            actual = {"palabra": c, "inicio": round(a, 3), "fin": round(b, 3)}
        else:
            actual["palabra"] += c
            actual["fin"] = round(b, 3)
    if actual:
        palabras.append(actual)
    with open(os.path.join(carpeta, "palabras.json"), "w", encoding="utf-8") as f:
        json.dump(palabras, f, ensure_ascii=False, indent=1)
    return palabras


async def generar(texto, voz, velocidad, tono, carpeta):
    if str(voz).startswith("eleven:"):
        voz, _, gratis = str(voz).partition("|")
        try:
            palabras = _eleven(texto, voz.split(":", 1)[1], velocidad, carpeta)
            MOTOR.update(motor="elevenlabs", aviso=None)
            return palabras
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            MOTOR.update(motor="edge", aviso=f"ElevenLabs no ha podido ({str(e)[:120]}); voz gratis")
            print(f"voz: {MOTOR['aviso']}", flush=True)
            voz = gratis or os.environ.get("VOZ_GRATIS", VOZ_GRATIS)
    else:
        MOTOR.update(motor="edge", aviso=None)
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


def apretar(carpeta, hueco_max=0.22, inicio_max=0.08):
    """Quita los silencios largos entre frases (edge-tts deja casi 1 segundo tras cada punto, y eso hace que la gente
    se vaya) y mueve los tiempos de cada palabra para que los subtítulos sigan cuadrando. Devuelve los segundos quitados."""
    import subprocess
    ruta_json, ruta_mp3 = os.path.join(carpeta, "palabras.json"), os.path.join(carpeta, "voz.mp3")
    palabras = json.load(open(ruta_json, encoding="utf-8"))
    if len(palabras) < 2:
        return 0.0
    tramos, quitado, desplaz = [], 0.0, []
    desde = max(0.0, palabras[0]["inicio"] - inicio_max)
    quitado = desde
    for i, p in enumerate(palabras):
        desplaz.append(quitado)
        if i + 1 < len(palabras):
            hueco = palabras[i + 1]["inicio"] - p["fin"]
            if hueco > hueco_max:
                corte_ini = p["fin"] + hueco_max / 2
                corte_fin = palabras[i + 1]["inicio"] - hueco_max / 2
                tramos.append((desde, corte_ini))
                quitado += corte_fin - corte_ini
                desde = corte_fin
    tramos.append((desde, palabras[-1]["fin"] + 0.35))
    if quitado < 0.05:
        return 0.0
    partes = "".join(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{n}];" for n, (a, b) in enumerate(tramos))
    filtro = partes + "".join(f"[a{n}]" for n in range(len(tramos))) + f"concat=n={len(tramos)}:v=0:a=1[s]"
    tmp = ruta_mp3 + ".apretado.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", ruta_mp3, "-filter_complex", filtro, "-map", "[s]",
                    "-c:a", "libmp3lame", "-b:a", "160k", tmp], check=True)
    os.replace(tmp, ruta_mp3)
    for p, d in zip(palabras, desplaz):
        p["inicio"], p["fin"] = round(p["inicio"] - d, 3), round(p["fin"] - d, 3)
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(palabras, f, ensure_ascii=False, indent=1)
    return round(quitado, 2)


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
