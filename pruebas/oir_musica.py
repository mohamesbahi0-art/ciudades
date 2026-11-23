"""Oído de la Policía: compone cada música de fondo y se la hace escuchar a Gemini para que diga si suena bien.

Nosotros no tenemos oídos; Gemini sí puede escuchar. Así se revisa la música nueva (herramientas/musica.py) antes de
que llegue a los vídeos. Solo imprime la nota y los problemas.

    GEMINI_API_KEY=... python pruebas/oir_musica.py [inspira energia tension calma]
"""
import json
import os
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import musica  # noqa: E402
from bots.comun import gemini  # noqa: E402

USOS = {"inspira": "historias motivadoras de famosos (TikTok, con voz encima)",
        "energia": "vídeos de videojuegos y datos curiosos (YouTube Shorts, con voz encima)",
        "tension": "historias de terror (YouTube Shorts, con voz encima)",
        "calma": "vídeos informativos tranquilos (con voz encima)"}
PREGUNTA = """Eres productor musical. Escucha esta música de fondo de 20 segundos, compuesta por ordenador para {uso}.
Sé sincero y exigente. Puntúa de 1 a 10 si sonaría bien de fondo en un vídeo así (10 = como una música de biblioteca
profesional; 1 = molesta). Di a qué suena, y lista los problemas concretos (ruidos, desafinaciones, golpes raros,
volumen irregular, aburrida, demasiado aguda...) y cómo arreglarlos.
Devuelve SOLO un JSON: {{"nota": 0, "suena_a": "...", "problemas": ["..."], "arreglos": ["..."]}}"""


def main(nombres):
    notas = {}
    with tempfile.TemporaryDirectory() as tmp:
        for n in nombres:
            m4a, mp3 = os.path.join(tmp, f"{n}.m4a"), os.path.join(tmp, f"{n}.mp3")
            musica.crear(n, 20, m4a)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", m4a, "-b:a", "128k", mp3], check=True)
            r = gemini.preguntar(PREGUNTA.format(uso=USOS.get(n, "vídeos cortos")), audio=mp3, temperatura=0.3)
            notas[n] = r.get("nota") if isinstance(r, dict) else None
            print(f"== {n}: {json.dumps(r, ensure_ascii=False)}", flush=True)
    print("NOTAS", notas)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or list(musica.PIEZAS)))
