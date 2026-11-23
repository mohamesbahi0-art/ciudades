"""La Sala de Ideas: antes de gastar dibujos y montaje, se juzgan las ideas. Para cada idea, la defensa dice por qué
funcionaría y la fiscalía por qué no; los tres jueces votan y gana la mejor. Una sola llamada a la IA (de las ligeras).
Si la IA no contesta, se queda la primera idea (ningún canal se queda sin vídeos)."""
import datetime as dt

from bots.comun import gemini, privado

PLANTILLA = """Eres la Sala de Ideas del Juzgado de «{nombre}» ({tema}). Estas son las ideas para el próximo vídeo corto:
{ideas}

Lo que ya se sabe del canal (datos reales):
{pruebas}

Para CADA idea: la letrada Sofía Vargas dice en una frase por qué funcionaría y el fiscal Héctor Duro, por qué no.
Después votan la jueza Carmen Gancho (¿para el dedo en 2 segundos?), el juez Ramón Reloj (¿se verá entero?) y la jueza
Lola Calle (¿le importa a la gente ahora?), con nota de 0 a 100 cada uno.
Devuelve SOLO un JSON: {{"juicios": [{{"n": 1, "defensa": "...", "fiscalia": "...", "gancho": 0, "reloj": 0, "calle": 0}}]}}"""


def elegir(clave, canal, ideas, pruebas=""):
    """Devuelve (idea elegida, juicio para la app o None)."""
    if len(ideas) < 2:
        return (ideas[0] if ideas else None), None
    lista = "\n".join(f"{n}. {i.get('titulo')} — {i.get('idea')} (gancho: {i.get('gancho')})" for n, i in enumerate(ideas, 1))
    try:
        r = gemini.preguntar(PLANTILLA.format(nombre=canal["nombre"], tema=canal.get("tema", ""), ideas=lista,
                                              pruebas=pruebas or "- todavía hay pocos datos"), temperatura=0.4,
                             ligero_primero=True)
        juicios = [j for j in r.get("juicios", []) if isinstance(j, dict)]
    except (gemini.SinIA, AttributeError):
        return ideas[0], None
    puntos = []
    for j in juicios:
        try:
            n = int(j.get("n", 0))
            notas = [max(0, min(100, int(j.get(k, 0)))) for k in ("gancho", "reloj", "calle")]
        except (TypeError, ValueError):
            continue
        if 1 <= n <= len(ideas):
            puntos.append((sum(notas) / 3, n, j, notas))
    if not puntos:
        return ideas[0], None
    media, n, j, notas = max(puntos)
    elegida = ideas[n - 1]
    ahora = dt.datetime.now(dt.timezone.utc)
    juicio = {"canal": clave, "tipo": "idea", "titulo": elegida.get("titulo"), "defensa": j.get("defensa", ""),
              "fiscalia": j.get("fiscalia", ""),
              "votos": [{"juez": nombre, "voto": "sube" if nota >= 60 else "no", "nota": nota}
                        for nombre, nota in zip(("Jueza Carmen Gancho", "Juez Ramón Reloj", "Jueza Lola Calle"), notas)],
              "sentencia": "sube", "fecha": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "resumen": f"Ganó entre {len(ideas)} ideas con {round(media)}/100 de media.",
              "otras": [i.get("titulo") for k, i in enumerate(ideas, 1) if k != n]}
    id_juicio = f"{ahora.strftime('%Y%m%d-%H%M')}-{clave}-idea".replace(".", "-")
    privado.guardar_estado(f"juzgado/juicios/{id_juicio}.json", juicio)
    c = privado.cuaderno("sala_ideas")
    c.apuntar("eleccion", {"canal": clave, "elegida": elegida.get("titulo"), "media": round(media), "ideas": len(ideas)})
    c.guardar()
    return elegida, id_juicio
