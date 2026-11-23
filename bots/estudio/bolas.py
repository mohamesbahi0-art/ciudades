"""«Bolas» (el Dibujante de mapas): vídeos de humor «¿Qué pasaría si un país desapareciera?» con
bolas-país de verdad (su bandera, sus ojos y su cara) sobre un mapa del mundo de verdad, en series de 3 partes.

- El Archivero de mapas (archivero_mapas.py) dice qué país y qué parte tocan, y lo que pasó en las partes anteriores.
- El guionista escribe 8-11 escenas: lo que dice el narrador, el plano (mundo, zona, país o las bolas de cerca), el país
  al que mira la cámara, lo que pasa (desaparece, lloran, se pelean por el hueco…) y las bolas con su cara y su bocadillo.
- El Cartógrafo (cartografo.py) pone a cada escena su encuadre y a cada bola su sitio en el mapa.
- bolas.html lo dibuja: el país se borra del mapa y deja el hueco, la cámara va de un sitio a otro y las bolas saltan,
  lloran, se pelean y hablan, con los subtítulos al ritmo de la voz.
Mapas: Natural Earth (dominio público). Banderas: flag-icons (MIT). Música: la de la fábrica (compuesta o dominio público).
"""
import json

from bots.comun import ia
from bots.estudio import archivero_mapas, cartografo

MUSICA = "energia"
PLANOS = ("mundo", "zona", "pais", "bolas")
ACCIONES = ("desaparece", "salta", "llora", "rie", "pelea", "corre", "celebra", "tiembla", "mira", "habla")
EXPRESIONES = ("feliz", "triste", "enfadado", "sorprendido", "malvado", "asustado", "neutral")
PALETA = ["#F7C873", "#9AD3A8", "#F4A6A6", "#A9C6F5", "#D7B4F3", "#F9E48B", "#8FD6D1", "#F5B98A", "#C5E384",
          "#E8A7C9", "#B5C7D3", "#F2D0A4"]

PLANTILLA = """Eres el guionista de «{nombre}», un canal de YouTube Shorts de humor con bolas-país (countryballs): «¿Qué
pasaría si un país desapareciera?». Hoy toca {pais_nombre}: PARTE {parte} DE {partes}.
{anteriores}
Así son los vídeos:
- De 30 a 45 segundos, de 8 a 11 escenas, una o dos frases cortas por escena. Narrador con gracia y ritmo.
- Consecuencias en cadena, cada una más loca que la anterior, con cosas reales de fondo (lo que exporta, su comida, su
  música, su fútbol, su geografía, sus récords). Los vecinos reaccionan: se pelean por el hueco, lloran, lo celebran.
- Parte 1: la desaparición y lo primero que pasa. Parte 2: el caos en el resto del mundo. Parte 3: el final, qué acaba
  ocupando el hueco. Si no es la última parte, la última escena deja con ganas de la siguiente («y lo que pasó después…»).
- Humor blanco y sin odio: tópicos simpáticos de comida, fútbol, música y costumbres. Nada de religión, etnias,
  pobreza, guerras, terrorismo ni violencia de verdad, ni burlas que ofendan a la gente de un país.

Lo que ha aprendido el canal (lo del dueño manda):
{lecciones}

REGLAS DEL GUION
- "plano": "mundo" (el mapa entero), "zona" (el país y sus vecinos), "pais" (de cerca) o "bolas" (las bolas hablando
  de cerca, con el mapa detrás). Empieza con "zona" o "pais"; alterna planos y no repitas el mismo dos veces seguidas.
- "foco": el código ISO de 2 letras del país al que mira la cámara (normalmente {pais}, o el de la consecuencia).
- "accion": una de {acciones}. {regla_desaparece}
- "bolas": de 1 a 4 bolas en escena, cada una {{"pais": "FR", "expresion": una de {expresiones}, "dice": "bocadillo de
  5 palabras como mucho, o vacío"}}. Países de verdad y que pegan (vecinos, rivales, socios). {regla_bola}
- "texto": de 1 a 3 palabras grandes en pantalla, la clave de la escena.
- "voz": lo que dice el narrador (números escritos como se dicen).
Vecinos de {pais_nombre}: {vecinos}.
Ya hechos en el canal (no repitas chistes ni títulos):
{hechos}

Devuelve SOLO un JSON:
{{"titulo": "{pais_nombre} desaparece y … (un final gracioso, con 1 o 2 emojis)",
  "texto_pantalla": "el gancho de arriba, como mucho 40 caracteres (p. ej. ¿Y SI {mayus} DESAPARECIERA?)",
  "descripcion": "2 frases con gancho y de 3 a 5 hashtags (#shorts #countryballs …)",
  "escenas": [{{"voz": "…", "plano": "zona", "foco": "{pais}", "accion": "desaparece", "texto": "…",
               "bolas": [{{"pais": "{pais}", "expresion": "triste", "dice": "¡Adiós!"}}]}}]}}"""


def _iso(x):
    x = str(x or "").strip().upper()
    return x if len(x) == 2 and cartografo.tiene_bandera(x) else None


def _color(iso):
    return PALETA[sum(ord(c) for c in iso) % len(PALETA)]


def limpiar(g):
    """El guion, dentro de lo que sabe dibujar bolas.html (con encuadres y sitios ya calculados)."""
    pais = _iso(g.get("pais")) or "ES"
    parte, partes = int(g.get("parte") or 1), int(g.get("partes") or 1)
    escenas = []
    for e in g.get("escenas") or []:
        if not isinstance(e, dict) or not str(e.get("voz") or "").strip():
            continue
        plano = e.get("plano") if e.get("plano") in PLANOS else "zona"
        foco = _iso(e.get("foco")) if cartografo.existe(_iso(e.get("foco")) or "") else pais
        bolas = []
        for b in (e.get("bolas") or [])[:4]:
            iso = _iso((b or {}).get("pais")) if isinstance(b, dict) else None
            if not iso or any(x["pais"] == iso for x in bolas):
                continue
            bolas.append({"pais": iso, "expresion": b.get("expresion") if b.get("expresion") in EXPRESIONES else "neutral",
                          "dice": str(b.get("dice") or "")[:40]})
        accion = e.get("accion") if e.get("accion") in ACCIONES else "habla"
        escenas.append({"voz": str(e["voz"]).strip(), "texto": str(e.get("texto") or "")[:24], "plano": plano,
                        "foco": foco, "accion": accion, "bolas": bolas})
    if len(escenas) < 5:
        raise ValueError("el guion de bolas necesita al menos 5 escenas con voz")
    escenas = escenas[:12]
    desaparece = [i for i, e in enumerate(escenas) if e["accion"] == "desaparece"]
    for i in desaparece[1:]:
        escenas[i]["accion"] = "habla"                   # el país solo se borra una vez
    if parte == 1 and not desaparece:
        escenas[0]["accion"] = "desaparece"
    g["borrado_desde"] = 0 if parte > 1 else None        # en la Parte 2 y la 3 el hueco ya está desde el principio
    if parte > 1:
        for e in escenas:
            if e["accion"] == "desaparece":
                e["accion"] = "mira"
    m = cartografo.mundo()
    for e in escenas:
        otros = [b["pais"] for b in e["bolas"] if cartografo.existe(b["pais"]) and b["pais"] != e["foco"]]
        e["caja"] = cartografo.encuadre(e["plano"], e["foco"], otros if e["plano"] == "zona" else ())
        for k, b in enumerate(e["bolas"]):
            p = m["paises"].get(b["pais"]) or m["paises"].get(e["foco"]) or {"centro": [m["ancho"] / 2, m["alto"] / 2]}
            b["x"], b["y"] = p["centro"][0] + (0 if b["pais"] in m["paises"] else 60 * (k + 1)), p["centro"][1]
    g["escenas"] = escenas
    g["pais"], g["parte"], g["partes"] = pais, parte, partes
    g["pais_nombre"] = cartografo.nombre(pais)
    g["mapa"] = {iso: {"d": p["d"], "c": _color(iso)} for iso, p in m["paises"].items() if iso not in ("AQ", "TF")}
    g["mundo"] = [m["ancho"], m["alto"]]
    titulo = str(g.get("titulo") or f"{g['pais_nombre']} desaparece").replace("#shorts", "").strip()
    if not titulo.lower().startswith(g["pais_nombre"].lower()):    # el Archivero sigue las series por el título
        titulo = f"{g['pais_nombre']}: {titulo}"
    if partes > 1 and f"(Parte {parte})" not in titulo:
        titulo = archivero_mapas.PARTE.sub("", titulo).strip() + f" (Parte {parte})"
    g["titulo"] = (titulo[:88] + " #shorts").strip()
    g["texto_pantalla"] = str(g.get("texto_pantalla") or f"¿Y SI {g['pais_nombre'].upper()} DESAPARECIERA?")[:40]
    desc = str(g.get("descripcion") or "").strip()
    if "Natural Earth" not in desc:
        desc += "\n\nMapas: Natural Earth (dominio público). Banderas: flag-icons (MIT)."
    g["descripcion"] = desc.strip()
    g["formato"], g["html"] = "bolas", "bolas.html"
    g["narracion"] = " ".join(e["voz"] for e in escenas)
    return g


def guionizar(canal, lecciones):
    """El Archivero elige país y parte; el guionista escribe; el Cartógrafo encuadra (en limpiar)."""
    clave = canal.get("clave", "mapas")
    toca = archivero_mapas.siguiente(clave)
    hechos = archivero_mapas.titulos(clave)[-40:]
    anteriores = ("Lo que pasó en las partes anteriores (sigue esa historia, sin repetirla):\n" +
                  "\n".join(f"- {t}" for t in toca["anteriores"])) if toca["anteriores"] else ""
    ultima = toca["parte"] == toca["partes"]
    texto = PLANTILLA.format(
        nombre=canal.get("nombre", clave), pais=toca["pais"], pais_nombre=toca["nombre"], mayus=toca["nombre"].upper(),
        parte=toca["parte"], partes=toca["partes"], anteriores=anteriores, lecciones=lecciones or "(nada todavía)",
        acciones=", ".join(ACCIONES), expresiones=", ".join(EXPRESIONES),
        regla_desaparece=("En la Parte 1, la primera o la segunda escena es \"desaparece\" (solo una vez)."
                          if toca["parte"] == 1 else "En esta parte el país ya no está: no uses \"desaparece\"."),
        regla_bola=(f"La bola de {toca['nombre']} sale al desaparecer (llorando o despidiéndose) y luego ya no."
                    if toca["parte"] == 1 else f"La bola de {toca['nombre']} ya no está (puede salir en un recuerdo)."),
        vecinos=", ".join(f"{cartografo.nombre(v)} ({v})" for v in cartografo.vecinos(toca["pais"], 6)) or "ninguno",
        hechos="\n".join(f"- {t}" for t in hechos) or "- (nada)")
    if ultima and toca["partes"] > 1:
        texto += "\nEs la ÚLTIMA parte: cierra la historia con un final redondo y una pregunta a quien lo ve."
    ultimo = None
    for _ in range(3):
        g = ia.preguntar(texto, papel="guionista", temperatura=0.95)
        if isinstance(g, list) and g:
            g = g[0]
        try:
            if isinstance(g, dict):
                g.update(pais=toca["pais"], parte=toca["parte"], partes=toca["partes"])
                g = limpiar(g)
                archivero_mapas.apuntar(clave, toca, g["titulo"])
                return g
        except (ValueError, TypeError, KeyError) as e:
            ultimo = e
        texto += "\n\nEl intento anterior no tenía la forma pedida. Devuelve SOLO el JSON, con 8 a 11 escenas."
    raise ValueError(f"La IA no dio un guion válido para «bolas» ({ultimo})")


def eventos(g):
    """Golpe al empezar, whoosh en cada cambio de plano, pop cuando habla una bola y un golpe cuando el país se borra."""
    ev = [("golpe", 0.04, 0.7)]
    for i, e in enumerate(g["escenas"]):
        if i:
            ev.append(("whoosh", max(0.0, e["inicio"] - 0.05), 0.35))
        if e["accion"] == "desaparece":
            ev.append(("golpe", e["inicio"] + 0.45, 0.9))
        for k, b in enumerate(e["bolas"]):
            if b.get("dice"):
                ev.append(("pop", e["inicio"] + 0.25 + 0.18 * k, 0.45))
    if g.get("partes", 1) > g.get("parte", 1):
        ev.append(("brillo", max(0.0, g["duracion"] - 1.3), 0.5))
    return ev


if __name__ == "__main__":
    print(json.dumps({"planos": PLANOS, "acciones": ACCIONES, "expresiones": EXPRESIONES}, ensure_ascii=False))
