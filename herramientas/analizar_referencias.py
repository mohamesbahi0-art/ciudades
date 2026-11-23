"""Analiza con Gemini vídeos de referencia (los que más le gustan al dueño) para que el estudio de animación copie su
estilo: escenas con sus tiempos, textos en pantalla, voz, música, colores, formas y ritmo. Cada vídeo se reduce antes
(540p) para que quepa en una petición. Deja un JSON con el análisis de cada uno y la fórmula común.

Uso:  python herramientas/analizar_referencias.py <carpeta> <salida.json>
"""
import base64
import glob
import json
import os
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from bots.comun import gemini  # noqa: E402

UNO = """Analiza este vídeo vertical corto (TikTok/Instagram) con todo detalle, para poder hacer otros iguales por programa.
Devuelve SOLO un JSON:
{"duracion": 0, "tema": "...", "formato": "historia de famoso | comparación A vs B | frases con iconos | otro",
 "gancho": "qué pasa en los 2 primeros segundos",
 "escenas": [{"desde": 0.0, "hasta": 0.0, "texto_pantalla": "texto exacto", "palabras_resaltadas": ["..."],
              "que_se_ve": "personajes, objetos, fondo y cómo se mueven", "transicion": "cómo cambia a la siguiente"}],
 "voz": {"hay": true, "tipo": "mujer/hombre, tono, velocidad", "texto": "lo que dice, si hay"},
 "sonido": "música (estilo, volumen), efectos de sonido y cuándo",
 "estilo_visual": {"colores": ["#hex"], "fondo": "...", "personajes": "cómo están dibujados", "letra": "tipo de letra, tamaño, posición, mayúsculas",
                   "luz": "focos, brillos"},
 "animacion": "qué se mueve, a qué ritmo, efectos (rebotes, aparecer, contadores)",
 "final": "cómo acaba (pregunta, bucle...)",
 "por_que_engancha": "en una frase"}"""

FORMULA = """Estos son los análisis de los vídeos más virales de una cuenta de TikTok/Instagram:
{analisis}
Escribe la FÓRMULA común para hacer vídeos nuevos que se parezcan, como un manual para un programa de animación.
Devuelve SOLO un JSON: {{"formatos": [{{"nombre": "...", "cuando_usarlo": "...", "estructura": ["paso 1", "..."], "duracion": "s"}}],
"estilo_visual": {{...}}, "texto": {{...}}, "sonido": {{...}}, "temas_que_funcionan": ["..."], "ideas_nuevas": ["10 ideas concretas"]}}"""


def reducir(ruta, carpeta):
    salida = os.path.join(carpeta, os.path.basename(ruta) + ".540.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", ruta, "-vf", "scale=540:-2", "-r", "15",
                    "-c:v", "libx264", "-crf", "32", "-preset", "veryfast", "-c:a", "aac", "-b:a", "64k", salida],
                   check=True)
    return salida


def analizar(ruta, carpeta):
    pequeno = reducir(ruta, carpeta)
    with open(pequeno, "rb") as f:
        datos = base64.b64encode(f.read()).decode()
    cuerpo = {"contents": [{"parts": [{"inline_data": {"mime_type": "video/mp4", "data": datos}}, {"text": UNO}]}],
              "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
    import urllib.request
    ultimo = None
    for modelo in [m for m in gemini.BUENOS if m not in gemini.AGOTADOS]:
        req = urllib.request.Request(gemini.URL.format(modelo=modelo), data=json.dumps(cuerpo).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                texto = "".join(p.get("text", "") for p in json.load(r)["candidates"][0]["content"]["parts"])
            return gemini._limpiar_json(texto)
        except Exception as e:  # siguiente modelo
            ultimo = f"{modelo}: {type(e).__name__} {getattr(e, 'code', '')}"
            if getattr(e, "code", None) == 429:
                gemini.AGOTADOS.add(modelo)
    return {"error": ultimo}


def main():
    carpeta, salida = sys.argv[1], sys.argv[2]
    tmp = tempfile.mkdtemp()
    videos = sorted(glob.glob(os.path.join(carpeta, "*.mp4")) + glob.glob(os.path.join(carpeta, "*.mov")))
    resultados = {}
    for v in videos:
        resultados[os.path.basename(v)] = analizar(v, tmp)
        print(f"{os.path.basename(v)}: {'bien' if 'error' not in resultados[os.path.basename(v)] else 'falló'}", flush=True)
    buenos = {k: v for k, v in resultados.items() if "error" not in v}
    formula = None
    if buenos:
        try:
            formula = gemini.preguntar(FORMULA.format(analisis=json.dumps(buenos, ensure_ascii=False)[:60000]),
                                       temperatura=0.4)
        except gemini.SinIA as e:
            formula = {"error": str(e)}
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    with open(salida, "w", encoding="utf-8") as f:
        json.dump({"videos": resultados, "formula": formula}, f, ensure_ascii=False, indent=1)
    print(f"analizados {len(buenos)} de {len(videos)}")


if __name__ == "__main__":
    main()
