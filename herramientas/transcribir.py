"""Transcribe el audio de un vídeo (por ejemplo, el de un creador con permiso) con faster-whisper, gratis
y en la propia máquina, y guarda cada palabra con su tiempo para subtitulos.py o para elegir cortes.

Uso:  python transcribir.py video_o_audio --salida palabras.json [--modelo small] [--idioma es]
La primera vez descarga el modelo (small, unos 500 MB). En GitHub Actions conviene guardarlo en caché.
"""
import argparse, json

from faster_whisper import WhisperModel


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("entrada")
    p.add_argument("--salida", required=True)
    p.add_argument("--modelo", default="small")
    p.add_argument("--idioma", default="es")
    a = p.parse_args()
    modelo = WhisperModel(a.modelo, device="cpu", compute_type="int8")
    segmentos, info = modelo.transcribe(a.entrada, language=a.idioma, word_timestamps=True, vad_filter=True)
    palabras = []
    for s in segmentos:
        for w in s.words or []:
            palabras.append({"palabra": w.word.strip(), "inicio": round(w.start, 3), "fin": round(w.end, 3),
                             "prob": round(w.probability, 3)})
    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump(palabras, f, ensure_ascii=False, indent=1)
    print(f"OK {len(palabras)} palabras ({info.language}) en {a.salida}")


if __name__ == "__main__":
    main()
