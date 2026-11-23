"""«Hipnótico» (el Animador hipnótico): bolas de neón que rebotan con gravedad dentro de un aro que gira, con estela; cada
bote las hace crecer y deja una onda, y de vez en cuando nace otra bola. Encima va la historia narrada, con los
subtítulos grandes al ritmo de la voz y el gancho los primeros segundos. Lo dibuja hipnotico.html.

Sirve para las historias (terror, supervivencia, nivel oculto...): el fondo hipnótico engancha la vista mientras la voz
cuenta. El guion lo escribe el Escritor de siempre (escritor.escribir) y aquí se adapta al estudio.
"""
from bots.central import escritor
from bots.comun import privado

MUSICA = "tension"


def limpiar(g):
    """El guion, dentro de lo que sabe dibujar hipnotico.html (cada escena, una frase de la voz)."""
    escenas = []
    for e in g.get("escenas") or []:
        if not isinstance(e, dict):
            continue
        voz = str(e.get("voz") or e.get("texto") or "").strip()
        if voz:
            escenas.append({"voz": voz, "texto": voz})
    if len(escenas) < 2:
        raise ValueError("el guion hipnótico necesita al menos 2 escenas con voz")
    g["escenas"] = escenas[:12]
    g["formato"], g["html"] = "hipnotico", "hipnotico.html"
    g["titulo"] = str(g.get("titulo") or "")[:100]
    g["texto_pantalla"] = str(g.get("texto_pantalla") or "")[:60]
    g["narracion"] = " ".join(e["voz"] for e in escenas)
    return g


def guionizar(canal, lecciones):
    """La historia la escribe el Escritor de siempre; el dibujo de cada escena aquí no hace falta."""
    g = escritor.escribir(canal, lecciones, privado.titulos_recientes(canal["clave"]) if canal.get("clave") else [])
    return limpiar(g)


def eventos(g):
    """Golpe al empezar y un barrido suave en cada cambio de frase (la música hace el resto)."""
    ev = [("golpe", 0.04, 0.7)]
    for i, e in enumerate(g["escenas"]):
        if i:
            ev.append(("whoosh", max(0.0, e["inicio"] - 0.06), 0.25))
    return ev
