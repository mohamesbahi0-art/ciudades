"""El Escritor: escribe el guion de un Short para un canal, con gancho, escenas para el Dibujante y final en bucle.
Lee antes sus lecciones (memoria) y los títulos ya hechos, para no repetir."""
import re

from bots.comun import gemini

ESTILOS = {
    "historias": "historias cortas de ficción con un giro final que cambia todo lo anterior",
    "noticias": "noticias reales y comprobadas, el dato más fuerte primero",
    "datos": "datos curiosos reales, con cuenta atrás",
    "mapas": "«¿Qué pasaría si…?» con una cadena de consecuencias, cada una peor que la anterior",
    "acertijos": "un acertijo con cuenta atrás y la respuesta tras una pausa",
}

PLANTILLA = """Eres el Escritor de un canal de YouTube Shorts en español de España llamado «{nombre}» ({tema}).
Escribe UN guion nuevo para un Short de 30 a 45 segundos.

Reglas que funcionan:
- Los 2 primeros segundos son el gancho: una frase que abre una pregunta o empieza en mitad de la acción. Nada de saludos ni «en este vídeo».
- Frases cortas (12 palabras como mucho), una idea por frase. Algo nuevo cada 3-5 segundos.
- El final remata y, si puede ser, enlaza con la primera frase para que el vídeo se vea dos veces.
- Escribe los números como se dicen en voz alta.
- Contenido original: nada de personajes, juegos o series de otros. Para todos los públicos: miedo sí, gore no.
- La narración tiene entre 85 y 125 palabras.

Lo que ha aprendido este canal (síguelo; lo del dueño manda):
{lecciones}

Títulos ya publicados en este canal (no repitas sus temas):
{titulos}

Devuelve SOLO un JSON con esta forma:
{{"idea": "una línea con la idea",
  "titulo": "título de 60 caracteres como mucho, con gancho",
  "texto_pantalla": "de 2 a 5 palabras para los 2 primeros segundos",
  "narracion": "el texto completo que dirá la voz",
  "escenas": [{{"texto": "las frases exactas de la narración que cubre esta escena",
               "dibujo": "descripción en INGLÉS de la imagen vertical de esa escena: estilo {estilo_dibujo}, sin letras ni texto"}}],
  "descripcion": "una o dos frases para la descripción de YouTube",
  "hashtags": ["#3 a 5 hashtags del tema"]}}
Entre 5 y 8 escenas, en orden, que juntas cubran toda la narración."""


def palabras(texto):
    return re.findall(r"\w+", texto, flags=re.UNICODE)


def validar(g):
    problemas = []
    n = len(palabras(g.get("narracion", "")))
    if not 70 <= n <= 150:
        problemas.append(f"la narración tiene {n} palabras")
    if not 4 <= len(g.get("escenas", [])) <= 9:
        problemas.append(f"hay {len(g.get('escenas', []))} escenas")
    if any(not e.get("texto") or not e.get("dibujo") for e in g.get("escenas", [])):
        problemas.append("alguna escena no tiene texto o dibujo")
    if not g.get("titulo") or len(g["titulo"]) > 100:
        problemas.append("el título falta o pasa de 100 caracteres")
    return problemas


def escribir(canal, lecciones, titulos, intentos=3):
    estilo = ESTILOS.get(canal.get("tipo"), ESTILOS["historias"])
    dibujo = canal.get("estilo_dibujo") or "dark cinematic illustration, moody lighting, high detail"
    texto = PLANTILLA.format(nombre=canal["nombre"], tema=canal.get("tema") or estilo, lecciones=lecciones,
                             titulos="\n".join(f"- {t}" for t in titulos) or "- (ninguno todavía)", estilo_dibujo=dibujo)
    ultimo = []
    for _ in range(intentos):
        g = gemini.preguntar(texto)
        ultimo = validar(g)
        if not ultimo:
            g["titulo"] = g["titulo"].strip()[:100]
            return g
        texto += f"\n\nEl intento anterior no valía ({'; '.join(ultimo)}). Corrígelo."
    raise ValueError("El Escritor no consiguió un guion válido: " + "; ".join(ultimo))
