"""El Juez de guardia: juicio rápido de un vídeo ya montado. Mide el vídeo con fotogramas.py, mira los 7 fotogramas
y pone nota de 0 a 100 (gancho, retención, claridad y final, de 0 a 25 cada uno). Suspende con fallo grave o menos de 50.
Si la IA no contesta, el vídeo pasa sin juicio (regla del Juzgado: ningún canal se queda sin vídeos)."""
import json
import os
import subprocess
import sys

from bots.comun import gemini

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MINIMO = 50

PLANTILLA = """Eres el Juez de guardia del Juzgado de {donde} llamado «{nombre}». El vídeo está en {idioma}.
Juzgas si este vídeo hará que la gente que va pasando vídeos cortos se pare y lo vea entero.
Te paso 7 fotogramas en orden (segundos 0,3 · 1,2 · 2,5, y al 30 %, 55 %, 80 % y el final) y estos datos:
- Título: {titulo}
- Texto en pantalla al empezar: {gancho}
- Narración: {narracion}
- Medidas del vídeo: {medidas}

Lo que ha aprendido el Juzgado (síguelo; lo del dueño manda):
{lecciones}

Puntúa de 0 a 25 cada apartado:
- gancho: ¿los 2 primeros segundos hacen parar el dedo?
- retencion: ¿hay partes muertas, silencios o relleno?
- claridad: ¿se entiende solo y sin sonido? ¿se ve bien?
- final: ¿acaba en algo que dé ganas de verlo otra vez o comentar?
Fallos graves: pantalla negra, sin voz, imágenes rotas o con letras raras, título que no pega, contenido no apto.
Devuelve SOLO un JSON: {{"gancho": 0, "retencion": 0, "claridad": 0, "final": 0, "fallos_graves": [], "consejo": "una frase concreta para mejorarlo"}}"""


def juzgar(video, guion, canal, lecciones, carpeta):
    subprocess.run([sys.executable, os.path.join(RAIZ, "herramientas", "fotogramas.py"), video, "--salida", carpeta],
                   check=True, capture_output=True)
    with open(os.path.join(carpeta, "datos.json"), encoding="utf-8") as f:
        datos = json.load(f)
    medidas = {k: datos.get(k) for k in ("duracion", "cortes_por_minuto", "primer_corte", "pantallas_negras",
                                          "silencios", "volumen_inicio_db")}
    fallos = []
    if datos.get("pantallas_negras"):
        fallos.append("pantalla negra")
    if datos.get("sin_audio"):
        fallos.append("sin voz")
    donde = "un canal de YouTube Shorts" if canal.get("destino", "youtube") == "youtube" else "una cuenta de Instagram y TikTok"
    idioma = {"es": "español", "nl": "neerlandés", "en": "inglés"}.get(canal.get("idioma", "es")[:2], "español")
    texto = PLANTILLA.format(nombre=canal["nombre"], donde=donde, idioma=idioma, titulo=guion["titulo"], gancho=guion.get("texto_pantalla", ""),
                             narracion=guion["narracion"], medidas=json.dumps(medidas, ensure_ascii=False),
                             lecciones=lecciones)
    imagenes = [os.path.join(carpeta, f["archivo"]) for f in datos["fotogramas"]]
    try:
        v = gemini.preguntar(texto, imagenes=imagenes, solo_bueno=True, temperatura=0.3)
        notas = {k: max(0, min(25, int(v.get(k, 0)))) for k in ("gancho", "retencion", "claridad", "final")}
        fallos += [str(x) for x in v.get("fallos_graves", []) if x]
        total = sum(notas.values())
        veredicto = "suspendido" if fallos or total < MINIMO else "aprobado"
        resultado = dict(notas, total=total, veredicto=veredicto, fallos_graves=fallos, consejo=v.get("consejo", ""))
    except gemini.SinIA as e:
        resultado = {"veredicto": "suspendido" if fallos else "sin_juicio", "fallos_graves": fallos,
                     "motivo": f"juicio sin IA: {e}"}
    resultado["medidas"] = medidas
    with open(os.path.join(carpeta, "veredicto.json"), "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)
    return resultado
