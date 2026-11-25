"""«Hipnótico» (el Animador hipnótico): bolas de neón que rebotan con gravedad dentro de un aro que gira, con estela; cada
bote las hace crecer y deja una onda, y de vez en cuando nace otra bola. Encima va la historia narrada, con los
subtítulos grandes al ritmo de la voz. Lo dibuja hipnotico.html.

Sirve para las historias (terror, supervivencia, misterio...): el fondo hipnótico engancha la vista mientras la voz
cuenta. El guion lo escribe el Escritor de siempre (escritor.escribir) con el ENCARGO de este formato, y aquí se adapta
al estudio. Lo que el guionista no controla lo pone el formato solo (lo pidió el Cerebro):
- el gancho, ENTERO y en grande desde el primer fotograma, con el aro y las bolas ya en marcha;
- un plano nuevo cada 3 s como mucho (`planos`): la cámara salta, cambian los colores y las bolas reciben un empujón;
- en el centro del aro, el icono de lo que cuenta la frase (una cama, una puerta, un ojo que sigue a la bola...);
- el final (el giro) en rojo y temblando, y sin fundido a negro: el vídeo vuelve a empezar sin corte.
"""
import re
import unicodedata

from bots.central import escritor
from bots.comun import privado

MUSICA = "tension"
PALABRAS = 12          # palabras de voz por frase como mucho (las más largas se parten: así hay imagen nueva más a menudo)
ESCENAS = 20           # frases como mucho (si salen más, se juntan las más cortas: nunca se corta el final)
GANCHO = 40            # letras del gancho de arriba como mucho (cabe entero en 3 líneas grandes)
PLANO = 2.6            # segundos que dura un plano como mucho
SEGUNDOS = (24, 38)    # lo que se le pide al Escritor: una historia que se aguanta entera

# Lo que sabe dibujar hipnotico.html en el centro del aro, y las palabras que lo piden (sin tildes; vale el principio)
ICONOS = {
    "ojo": ("ojo", "mirada", "observ", "vigil", "eye", "watch", "oog"),
    "puerta": ("puerta", "cerradura", "timbre", "door", "deur"),
    "telefono": ("telefon", "movil", "llamada", "mensaje", "pantalla", "phone", "telefoon"),
    "cama": ("cama", "colchon", "almohada", "dormi", "pesadilla", "bed"),
    "casa": ("casa", "piso", "habitacion", "sotano", "desvan", "atico", "pasillo", "house", "huis"),
    "luna": ("luna", "noche", "anoche", "madrugada", "oscur", "night", "nacht"),
    "llave": ("llave", "candado", "cerrojo", "key", "sleutel"),
    "reloj": ("reloj", "hora", "minuto", "medianoche", "clock", "klok"),
    "espejo": ("espejo", "reflej", "cristal", "mirror", "spiegel"),
    "bosque": ("bosque", "arbol", "carretera", "camino", "monte", "forest", "bos"),
    "sombra": ("sombra", "figura", "silueta", "alguien", "hombre", "mujer", "nino", "nina", "desconocid", "shadow", "iemand"),
    "voz": ("voz", "voces", "susurr", "grit", "ruido", "golpe", "risa", "llant", "llor", "voice", "whisper", "stem"),
    "ventana": ("ventana", "cortina", "window", "raam"),
    "pregunta": (),
}

ENCARGO_FORMATO = """
ENCARGO DE ESTE FORMATO (manda sobre las reglas generales si chocan). No hay dibujos: se ve un aro de neón con bolas que
rebotan, el gancho escrito arriba y los subtítulos; la historia tiene que entenderse y dar miedo SOLO con la voz.
- Gancho inmediato: la PRIMERA frase (10 palabras como mucho) ya mete dentro de la situación, sin presentar a nadie ni
  explicar nada antes. Prohibido empezar con «Hola», «Esta es la historia de», «Te voy a contar» o «¿Sabías que?».
- "texto_pantalla": el gancho escrito, de 3 a 5 palabras y 32 letras como mucho. Se lee ENTERO en el primer fotograma:
  que prometa la historia sin destriparla y que no repita palabra por palabra la primera frase de la voz.
- Frases de 12 palabras como mucho. Cada frase añade UN detalle concreto que se pueda imaginar (una hora, un ruido, un
  objeto, un gesto). Nada de relleno ni de explicar lo que se siente («sentí mucho miedo», «algo no iba bien»).
- "escenas": de 6 a 8, de una o dos frases cada una (el "dibujo" aquí no se usa: pon una línea cualquiera).
- En cada escena añade "icono": lo que se verá dibujado en neón dentro del aro mientras suena. Elige el que nombra la
  frase, solo de esta lista: {iconos}.
- Sin despedidas, sin moraleja y sin pedir «suscríbete» ni «sígueme»."""

ENCARGO_TERROR = """
- Es una HISTORIA DE TERROR corta, en primera persona y en pasado, que podría pasarle a cualquiera en su casa: un solo
  sitio, uno o dos personajes sin nombre («mi hija», «mi vecino») y una sola cosa que no encaja. Miedo de lo que no se
  ve; nada de sangre ni de monstruos con explicación.
- La tensión sube en cada frase: lo raro se acerca (primero se oye, después se ve, después está al lado).
- GIRO FINAL: la penúltima frase da la vuelta a todo con un dato que ya estaba delante desde el principio (quien hablaba
  no era quien parecía, el peligro ya estaba dentro...). La última frase, de 10 palabras como mucho, deja el miedo
  abierto (mejor una pregunta) y enlaza con la primera para que el vídeo se vea otra vez. El giro NO se adelanta en el
  título ni en el gancho."""


def encargo(canal):
    """Lo que se le pide de más al Escritor para este formato (con el terror, en los canales de historias)."""
    texto = ENCARGO_FORMATO.format(iconos=", ".join(k for k in ICONOS))
    if (canal or {}).get("tipo", "historias") == "historias":
        texto += ENCARGO_TERROR
    return texto


def _plano(texto):
    """El texto en minúsculas y sin tildes, para buscar palabras."""
    return "".join(c for c in unicodedata.normalize("NFD", str(texto).lower()) if unicodedata.category(c) != "Mn")


def icono_de(frase, pedido=None, heredado=None):
    """El icono de una frase: el que pidió el guionista si se sabe dibujar; si no, el de la primera palabra de la frase
    que tenga dibujo (una pregunta, el interrogante); y si no, el de la escena de la que viene o la sombra."""
    pedido = _plano(pedido or "").strip()
    if pedido in ICONOS:
        return pedido
    llano, mejor = _plano(frase), None
    for nombre, claves in ICONOS.items():
        for c in claves:
            m = re.search(r"\b" + re.escape(c), llano)
            if m and (mejor is None or m.start() < mejor[0]):
                mejor = (m.start(), nombre)
    if str(frase).strip().endswith("?"):
        return "pregunta"
    return mejor[1] if mejor else (heredado or "sombra")


def partir(texto):
    """Una escena, en frases de PALABRAS palabras como mucho: por los puntos y, si hace falta, por las comas."""
    frases = [f.strip() for f in re.findall(r"[^.!?…]+[.!?…]*[»\")]*\s*", str(texto)) if f.strip()] or [str(texto).strip()]
    salida = []
    for f in frases:
        while len(f.split()) > PALABRAS:
            ws = f.split()
            comas = [i + 1 for i, w in enumerate(ws[:-2]) if w.endswith((",", ";", ":")) and 3 <= i + 1 <= PALABRAS]
            corte = min(comas, key=lambda i: abs(i - len(ws) / 2)) if comas else min(PALABRAS, (len(ws) + 1) // 2)
            salida.append(" ".join(ws[:corte]))
            f = " ".join(ws[corte:])
        if salida and len(f.split()) < 2:          # una palabra suelta no es una escena: va con la frase anterior
            salida[-1] += " " + f
        else:
            salida.append(f)
    return salida


def gancho_de(g):
    """El gancho de arriba: lo que escribió el guionista (o el título, sin emojis ni #shorts), en mayúsculas y entero."""
    txt = str(g.get("texto_pantalla") or "").strip()
    if not txt:
        txt = re.sub(r"#\w+", "", str(g.get("titulo") or ""))
        txt = "".join(c for c in txt if unicodedata.category(c)[0] in "LNPZ" and ord(c) < 0x2000)
    txt = re.sub(r"\s+", " ", txt).strip(" .,;:-").upper()
    if len(txt) > GANCHO:                          # no cabe: se corta por una palabra entera, sin dejar un «QUE» colgando
        ws = txt[:GANCHO + 1].rsplit(" ", 1)[0].split()
        while len(ws) > 2 and len(ws[-1].strip("¿¡,.")) <= 3:
            ws.pop()
        txt = " ".join(ws).rstrip(" ,;:")
    return txt


def limpiar(g):
    """El guion, dentro de lo que sabe dibujar hipnotico.html (cada escena, una frase corta de la voz con su icono)."""
    escenas = []
    for e in g.get("escenas") or []:
        if not isinstance(e, dict):
            continue
        voz = re.sub(r"\s+", " ", str(e.get("voz") or e.get("texto") or "")).strip()
        if not voz:
            continue
        pedido = e.get("icono") if _plano(e.get("icono") or "").strip() in ICONOS else None
        de_la_escena = icono_de(voz, pedido)
        for k, frase in enumerate(partir(voz)):
            escenas.append({"voz": frase, "texto": frase,
                            "icono": icono_de(frase, pedido if k == 0 else None, heredado=de_la_escena)})
    if len(escenas) < 2:
        raise ValueError("el guion hipnótico necesita al menos 2 escenas con voz")
    while len(escenas) > ESCENAS:                  # demasiadas frases: se juntan las dos seguidas más cortas (no se pierde nada)
        i = min(range(len(escenas) - 1), key=lambda k: len((escenas[k]["voz"] + " " + escenas[k + 1]["voz"]).split()))
        junta = escenas[i]["voz"] + " " + escenas[i + 1]["voz"]
        escenas[i:i + 2] = [{"voz": junta, "texto": junta, "icono": escenas[i]["icono"]}]
    g["escenas"] = escenas
    g["formato"], g["html"] = "hipnotico", "hipnotico.html"
    g["titulo"] = str(g.get("titulo") or "")[:100]
    g["texto_pantalla"] = gancho_de(g)
    g["narracion"] = " ".join(e["voz"] for e in escenas)
    return g


def guionizar(canal, lecciones):
    """La historia la escribe el Escritor de siempre, con el encargo de este formato (gancho inmediato, frases cortas,
    icono por escena y, en las historias, terror con giro final)."""
    seg = canal.get("segundos") or SEGUNDOS
    pedido = dict(canal, segundos=[min(seg[0], SEGUNDOS[0]), min(seg[1], SEGUNDOS[1])], escenas=(6, 8))
    g = escritor.escribir(pedido, (lecciones or "") + "\n" + encargo(canal),
                          privado.titulos_recientes(canal["clave"]) if canal.get("clave") else [])
    return limpiar(g)


def preparar(g):
    """Con la voz ya grabada: los cambios de plano (`planos`, en segundos). Uno en cada frase nueva y, dentro de las
    frases largas, en el arranque de una palabra, para que ningún plano dure más de PLANO segundos."""
    cortes = []
    for i, e in enumerate(g["escenas"]):
        a, b = float(e["inicio"]), float(e["fin"])
        if i:
            cortes.append(a)
        trozos = int((b - a) / PLANO) + 1
        for k in range(1, trozos):
            ideal = a + (b - a) * k / trozos
            cerca = [w["a"] for w in e.get("palabras") or [] if abs(w["a"] - ideal) < 0.45 and a + 0.8 < w["a"] < b - 0.8]
            cortes.append(min(cerca, key=lambda x: abs(x - ideal)) - 0.04 if cerca else ideal)
    g["planos"] = [round(c, 3) for c in sorted(cortes) if 0.5 < c < g["duracion"] - 0.5]
    g["giro"] = round(float(g["escenas"][-1]["inicio"]), 3)          # donde empieza la última frase (el final en rojo)
    return g


def eventos(g):
    """Golpe al empezar y en el giro final, y un barrido suave en cada cambio de plano (la música hace el resto)."""
    ev = [("golpe", 0.04, 0.7)]
    for c in g.get("planos") or [e["inicio"] for e in g["escenas"][1:]]:
        ev.append(("whoosh", max(0.0, c - 0.06), 0.25))
    if g.get("giro"):
        ev.append(("golpe", max(0.0, g["giro"] - 0.02), 0.8))
    return ev
