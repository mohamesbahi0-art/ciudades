"""El Escritor: escribe el guion de un vídeo corto para un canal o un barrio, con gancho, escenas para el Dibujante y
final en bucle. Lee antes sus lecciones (memoria), los títulos ya hechos (para no repetir) y, en los canales de datos o
noticias, las fuentes que le trae el Reportero (solo puede contar lo que dicen)."""
import re

from bots.comun import gemini

ESTILOS = {
    "historias": "historias cortas de ficción con un giro final que cambia todo lo anterior",
    "noticias": "noticias reales y comprobadas, el dato más fuerte primero",
    "datos": "datos curiosos reales que casi nadie sabe, contados como un secreto",
    "versus": "comparaciones entre dos cosas, punto por punto, y quién gana en cada uno",
    "mapas": "«¿Qué pasaría si…?» con una cadena de consecuencias, cada una peor que la anterior",
    "acertijos": "un acertijo con cuenta atrás y la respuesta tras una pausa",
    "motivacion": "vídeos de motivación: una idea que cambia cómo ves un hábito, contada con una mini historia",
    "supervivencia": "situaciones extremas en las que el espectador tiene que decidir qué haría para salir con vida",
}

REGLAS_TIPO = {
    "noticias": "- Cuenta SOLO hechos que estén en las fuentes de abajo. Si un dato no está en ellas, no lo digas. "
                "Nada de rumores como si fueran verdad: si la fuente dice que es un rumor, dilo.\n"
                "- Habla del juego por su nombre, pero los dibujos no copian personajes, logotipos ni capturas: "
                "escenas originales (ciudad tropical de neón, playas, coches, policía, atardeceres).",
    "datos": "- Cuenta SOLO datos que estén en las fuentes de abajo; no inventes ninguno.\n"
             "- Los dibujos son escenas originales, sin personajes ni logotipos de nadie.",
    "versus": "- Compara SOLO con datos que estén en las fuentes de abajo; no inventes ninguno.\n"
              "- Cada escena enseña un solo lado (nunca pantalla partida); alterna un lado y el otro.\n"
              "- Los dibujos son escenas originales, sin personajes ni logotipos de nadie.",
    "motivacion": "- Habla de tú, cercano y directo, sin frases de taza ni sermones.\n"
                  "- Una sola idea práctica que se pueda hacer hoy.",
    "supervivencia": "- Habla de tú. Plantea la situación, da opciones y deja que el espectador piense antes de la respuesta.\n"
                     "- Consejos de supervivencia correctos y prudentes; nada peligroso de imitar.",
}

IDIOMAS = {"es": "español de España", "nl": "neerlandés (de los Países Bajos)", "en": "inglés"}

PLANTILLA = """Eres el Escritor de {donde} llamado «{nombre}» ({tema}).
Escribe UN guion nuevo para un vídeo vertical de {seg_min} a {seg_max} segundos. Idioma de todo lo que se dice y se lee: {idioma}.

Reglas que funcionan:
- Los 2 primeros segundos son el gancho: una frase que abre una pregunta o empieza en mitad de la acción. Nada de saludos ni «en este vídeo».
- Frases cortas (12 palabras como mucho), una idea por frase. Algo nuevo cada 3-5 segundos.
- El final remata y, si puede ser, enlaza con la primera frase para que el vídeo se vea dos veces.
- Escribe los números como se dicen en voz alta.
- Contenido original. Sin miedo (lo pide el dueño): temas duros, oscuros, incómodos o polémicos, sí, contados con crudeza y sin moralina. Solo tres límites: lo que se diga de gente real tiene que ser verdad, nada de odio contra grupos de personas y nada que rompa las normas de YouTube o TikTok (por ejemplo, gore explícito).
{reglas_tipo}
- La narración tiene entre {pal_min} y {pal_max} palabras.

Lo que ha aprendido este canal (síguelo; lo del dueño manda):
{lecciones}

Títulos ya hechos en este canal (imita su estilo, con sus emojis y su final, pero NO repitas sus temas):
{titulos}
{fuentes}
Devuelve SOLO un JSON con esta forma:
{{"idea": "una línea con la idea",
  "titulo": "título de 70 caracteres como mucho, con gancho{fin_titulo}",
  "texto_pantalla": "de 2 a 5 palabras para los 2 primeros segundos",
  "narracion": "el texto completo que dirá la voz",
  "escenas": [{{"texto": "las frases exactas de la narración que cubre esta escena",
               "dibujo": "descripción en INGLÉS de la imagen vertical de esa escena: estilo {estilo_dibujo}, sin letras ni texto"}}],
  "descripcion": "una o dos frases para la descripción",
  "hashtags": ["#3 a 5 hashtags del tema"]{extra}{fuentes_usadas}}}
Entre {esc_min} y {esc_max} escenas, en orden, que juntas cubran toda la narración."""

EXTRA_REDES = """,
  "texto_instagram": "la descripción para Instagram: gancho en la primera línea, 2-4 líneas, una pregunta al final para que comenten",
  "texto_tiktok": "la descripción para TikTok: una o dos frases cortas con gancho\""""


def palabras(texto):
    return re.findall(r"\w+", texto, flags=re.UNICODE)


def medidas(canal):
    seg_min, seg_max = canal.get("segundos", [30, 45])
    pal_min, pal_max = int(seg_min * 2.4), int(seg_max * 2.8)
    esc_min, esc_max = (3, 5) if seg_max <= 25 else (5, 8)
    return {"seg_min": seg_min, "seg_max": seg_max, "pal_min": pal_min, "pal_max": pal_max,
            "esc_min": esc_min, "esc_max": esc_max}


def validar(g, canal=None):
    m = medidas(canal or {})
    problemas = []
    n = len(palabras(g.get("narracion", "")))
    if not int(m["pal_min"] * 0.85) <= n <= int(m["pal_max"] * 1.15):
        problemas.append(f"la narración tiene {n} palabras y debe tener entre {m['pal_min']} y {m['pal_max']}")
    escenas = g.get("escenas", [])
    if not m["esc_min"] - 1 <= len(escenas) <= m["esc_max"] + 1:
        problemas.append(f"hay {len(escenas)} escenas y deben ser entre {m['esc_min']} y {m['esc_max']}")
    if any(not e.get("texto") or not e.get("dibujo") for e in escenas):
        problemas.append("alguna escena no tiene texto o dibujo")
    if not g.get("titulo") or len(g["titulo"]) > 100:
        problemas.append("el título falta o pasa de 100 caracteres")
    if (canal or {}).get("destino") == "parasubir" and not g.get("texto_instagram"):
        problemas.append("falta texto_instagram")
    return problemas


IDEAS = """Eres el Escritor de {donde} llamado «{nombre}» ({tema}). Propón {n} ideas DISTINTAS para el próximo vídeo
vertical de {seg_min} a {seg_max} segundos, en {idioma}. Que cada una pueda parar el dedo de alguien en 2 segundos.
Sin miedo (lo pide el dueño): temas duros, oscuros, incómodos o polémicos, sí, contados con crudeza y sin moralina. Solo tres límites: lo que se diga de gente real tiene que ser verdad, nada de odio contra grupos de personas y nada que rompa las normas de YouTube o TikTok (por ejemplo, gore explícito).
{reglas_tipo}
Lo que ha aprendido este canal (lo del dueño manda):
{lecciones}

Títulos ya hechos (no repitas sus temas):
{titulos}
{fuentes}
Devuelve SOLO un JSON: {{"ideas": [{{"idea": "una línea", "titulo": "título con gancho", "gancho": "lo que se ve y se oye en los 2 primeros segundos"}}]}}"""


def ideas(canal, lecciones, titulos, fuentes=None, n=3):
    """Varias ideas cortas para que la Sala de Ideas elija la mejor antes de gastar dibujos en ella."""
    tipo = canal.get("tipo", "historias")
    youtube = canal.get("destino", "youtube") == "youtube"
    texto = IDEAS.format(donde="un canal de YouTube Shorts" if youtube else "una cuenta de Instagram y TikTok",
                         nombre=canal["nombre"], tema=canal.get("tema") or ESTILOS.get(tipo, ESTILOS["historias"]), n=n,
                         idioma=IDIOMAS.get(canal.get("idioma", "es")[:2], "español"), reglas_tipo=REGLAS_TIPO.get(tipo, ""),
                         lecciones=lecciones, titulos="\n".join(f"- {t}" for t in titulos) or "- (ninguno todavía)",
                         fuentes=f"\nFUENTES (lo único que puedes contar como hecho):\n{fuentes}\n" if fuentes else "",
                         **medidas(canal))
    r = gemini.preguntar(texto, ligero_primero=True)
    lista = r.get("ideas", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])
    return [i for i in lista if isinstance(i, dict) and i.get("idea")][:n]


def escribir(canal, lecciones, titulos, fuentes=None, intentos=3, idea=None):
    tipo = canal.get("tipo", "historias")
    estilo = ESTILOS.get(tipo, ESTILOS["historias"])
    dibujo = canal.get("estilo_dibujo") or "dark cinematic illustration, moody lighting, high detail"
    youtube = canal.get("destino", "youtube") == "youtube"
    texto = PLANTILLA.format(
        donde="un canal de YouTube Shorts" if youtube else "una cuenta de Instagram y TikTok",
        nombre=canal["nombre"], tema=canal.get("tema") or estilo, idioma=IDIOMAS.get(canal.get("idioma", "es")[:2], "español"),
        reglas_tipo=REGLAS_TIPO.get(tipo, ""), lecciones=lecciones,
        titulos="\n".join(f"- {t}" for t in titulos) or "- (ninguno todavía)",
        fuentes=f"\nFUENTES (lo único que puedes contar como hecho):\n{fuentes}\n" if fuentes else "",
        fin_titulo=", con 1 o 2 emojis y acabado en #shorts" if youtube else "",
        estilo_dibujo=dibujo, extra="" if youtube else EXTRA_REDES,
        fuentes_usadas=',\n  "fuentes_usadas": ["los números de las fuentes que has usado"]' if fuentes else "",
        **medidas(canal))
    if idea:
        texto += (f"\n\nLa Sala de Ideas ha elegido ESTA idea: escribe su guion.\nIdea: {idea.get('idea')}\n"
                  f"Título propuesto: {idea.get('titulo')}\nGancho: {idea.get('gancho')}")
    ultimo = []
    for _ in range(intentos):
        g = gemini.preguntar(texto)
        if isinstance(g, list) and g:
            g = g[0]
        ultimo = validar(g, canal) if isinstance(g, dict) else ["no devolvió un JSON con la forma pedida"]
        if not ultimo:
            g["titulo"] = g["titulo"].strip()[:100]
            return g
        texto += f"\n\nEl intento anterior no valía ({'; '.join(ultimo)}). Corrígelo."
    raise ValueError("El Escritor no consiguió un guion válido: " + "; ".join(ultimo))
