"""Formato «ciencia» del estudio (Wist je dat): curiosidades ciertas y sorprendentes en neerlandés, contadas con una
ilustración brillante sobre fondo oscuro, gráficas que se dibujan solas (ondas, deslizadores, medidores, escalas,
barras, número grande), etiquetas con línea y el texto arriba palabra a palabra con la palabra clave en recuadro.
Acaba con una pregunta, dos botones y una caja de comentario. Es la versión mejorada de los vídeos de la cuenta.

Lo dibuja ciencia.html. estudio.hacer() lo usa cuando el barrio tiene formato_estudio = "ciencia":
guionizar → voz escena a escena → render → música y efectos (eventos).
"""
import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import ia, privado  # noqa: E402
from bots.estudio.estudio import SIN_MIEDO  # noqa: E402

MUSICA = "calma"
PLANOS = ("gancho", "pregunta", "numero", "vs", "primerplano", "grande", "dato", "grafica", "lado", "banda", "final")
ILUSTRACIONES = ("pie pluma cerebro estomago corazon ojo mano pulmones diente celula tejido tierra luna sol gota rayo "
                 "planta gato reloj bateria virus adn atomo termometro planeta cohete bombilla trofeo piramide telefono "
                 "platano taza pez columna").split()
COLORES = ("blauw", "roze", "oranje", "groen", "paars", "rood", "geel")
PUNTOS = ("arriba", "abajo", "izquierda", "derecha", "centro", "cerebelo", "delante", "detras", "tronco", "acido", "pared",
          "esofago", "salida", "talon", "dedos", "planta", "aorta", "ventriculo", "pupila", "iris", "nucleo", "membrana",
          "mitocondria", "esmalte", "raiz", "atmosfera", "corona", "anillos", "filamento", "motor", "ventana", "traquea",
          "disco", "vertebra")
BOTONES = ["wist ik al", "nieuw voor mij"]

VOCABULARIO = f"""plano (cómo se reparte la pantalla; ALTERNA, que no se repita el mismo dos veces seguidas):
- "gancho": SOLO la primera escena. Una afirmación o cifra ENORME que entra de golpe: "golpe": {{"texto": "-1 cm",
  "sub": "kleiner dan vanochtend"}} (texto de 1 a 3 palabras o una cifra), con una ilustración pequeña debajo
- "pregunta": un «?» gigante; para abrir la pregunta del vídeo («Maar waarom?») justo después del gancho
- "numero": una cifra a pantalla completa que sube contando: "contador": {{"desde": 0, "hasta": 100000, "decimales": 0,
  "prefijo": "", "sufijo": "", "label": "slagen per dag"}}, con ilustración pequeña arriba
- "vs": pantalla partida para comparar: ilustracion e ilustracion2, "izquierda"/"derecha" (texto corto de cada lado,
  y si quieres "izquierda_sub"/"derecha_sub"), "color2" para el lado derecho
- "primerplano": la ilustración enorme, casi saliéndose de la pantalla (para un detalle)
- "grande": una ilustración grande (y si acaso una etiqueta o un número debajo)
- "dato": ilustración más pequeña arriba y UN componente debajo (número, deslizador, medidor, barras…)
- "grafica": el componente manda (una o dos ondas, una escala, barras) y la ilustración va pequeña arriba
- "lado": dos ilustraciones para comparar (ilustracion e ilustracion2)
- "banda": una franja de tejido a todo lo ancho (ácido, capa de moco y células); ilustracion "tejido"
- "final": cierre con la ilustración, dos botones y una caja de comentario (solo la última escena)
ilustracion / ilustracion2: {", ".join(ILUSTRACIONES)}.
  Si ninguna encaja, "emoji:<un emoji>" (p. ej. "emoji:🦒", "emoji:🍕", "emoji:🏰", "emoji:🧊", "emoji:🐝").
  "pluma" como ilustracion2 junto a "pie" o "mano" = cosquillas. "columna" = columna vertebral; con "animar":
  "comprimir" (los discos se aplastan) o "expandir" (se hinchan).
"aviso" (opcional, en UNA escena hacia la mitad): adelanto corto en neerlandés, p. ej. "het gekste komt nog".
puntos con nombre para las etiquetas: cerebro (cerebelo, delante, detras, tronco), estomago (acido, pared, esofago,
  salida), pie (talon, dedos, planta), corazon (aorta, ventriculo), ojo (pupila, iris), celula (nucleo, membrana,
  mitocondria), diente (esmalte, raiz), planeta (anillos), cohete (motor, ventana), bombilla (filamento); en cualquier
  otra: arriba, abajo, izquierda, derecha o centro.
color del resplandor: {", ".join(COLORES)}.
componentes (0 a 2 por escena; los textos en neerlandés, cortos):
- {{"tipo": "etiqueta", "texto": "slijmlaag", "sub": "dik & glibberig", "punto": "pared"}}
- {{"tipo": "numero", "valor": "pH 1,5", "titulo": "maagzuur", "sub": "zoutzuur (HCl)"}}   (una cifra clave)
- {{"tipo": "onda", "label": "VOORSPELLING", "color": "blauw", "picos": 3}}   (señales, ritmos, latidos; picos 0 = línea plana)
- {{"tipo": "deslizador", "label": "vertraging", "desde": 0, "hasta": 0.2, "max": 0.3, "unidad": "s", "decimales": 1}}
- {{"tipo": "medidor", "label": "KIETELMETER", "valor": 0.15, "texto": "bijna niks"}}   (valor de 0 a 1)
- {{"tipo": "escala", "desde": 0, "hasta": 14, "izquierda": "zuurder", "derecha": "basischer",
   "marcas": [{{"valor": 2.2, "texto": "citroen", "sub": "pH 2,2", "color": "geel"}}]}}
- {{"tipo": "barras", "items": [{{"label": "afbraak", "valor": 35, "color": "rood"}}, {{"label": "opbouw", "valor": 35, "color": "groen"}}]}}
- {{"tipo": "pildora", "texto": "schild tegen het zuur"}}"""

EJEMPLO = {"titulo": "Waarom ben je ’s avonds kleiner?", "escenas": [
    {"voz": "Vanavond ben je een centimeter kleiner dan vanochtend.", "clave": ["kleiner"], "plano": "gancho",
     "golpe": {"texto": "-1 cm", "sub": "kleiner dan vanochtend"}, "ilustracion": "columna", "color": "blauw"},
    {"voz": "Maar waarom eigenlijk?", "clave": ["waarom"], "plano": "pregunta", "color": "paars"},
    {"voz": "Eerst dit: je hart klopt zo'n honderdduizend keer per dag.", "clave": ["honderdduizend"], "plano": "numero",
     "ilustracion": "corazon", "color": "rood", "contador": {"desde": 0, "hasta": 100000, "label": "slagen per dag"}},
    {"voz": "En het gekste komt nog.", "clave": ["gekste"], "plano": "primerplano", "ilustracion": "columna",
     "color": "geel", "aviso": "het gekste komt nog"}]}
EJEMPLO_VIEJO = {"titulo": "Waarom kun je jezelf niet kietelen?", "escenas": [
    {"voz": "Probeer jezelf maar eens te kietelen.", "clave": ["kietelen."], "plano": "grande", "ilustracion": "pie",
     "ilustracion2": "pluma", "color": "oranje", "componentes": [{"tipo": "etiqueta", "texto": "jij zelf", "punto": "planta"}]},
    {"voz": "Dat komt door je kleine hersenen.", "clave": ["hersenen."], "plano": "grande", "ilustracion": "cerebro",
     "color": "blauw", "componentes": [{"tipo": "etiqueta", "texto": "kleine hersenen", "sub": "cerebellum", "punto": "cerebelo"}]},
    {"voz": "Die voorspellen precies wat je gaat voelen.", "clave": ["voorspellen"], "plano": "grafica",
     "ilustracion": "cerebro", "color": "blauw", "componentes": [{"tipo": "onda", "label": "VOORSPELLING", "color": "blauw"},
                                                                {"tipo": "onda", "label": "GEVOEL", "color": "wit"}]},
    {"voz": "Wist jij dit al? Laat het weten in de comments!", "clave": ["comments!"], "plano": "final",
     "ilustracion": "pie", "ilustracion2": "pluma", "color": "oranje", "botones": ["lukt niet", "lukt wél?!"]}]}

PLANTILLA = """Eres el guionista de «{nombre}», una cuenta de TikTok e Instagram en NEERLANDÉS de curiosidades («Wist je
dat?»). Cuenta datos ciertos y sorprendentes de cualquier tema: cuerpo humano, animales, espacio, comida, historia,
objetos de casa, récords, inventos… Vídeos de 22 a 28 segundos, con ritmo de TikTok: el dueño dice que tienen que
ser «interesantes, que te apetezca quedarte». Así son los vídeos del dueño (sacado de sus propios vídeos):
{formula}

Lo que ha aprendido la cuenta (lo del dueño manda):
{lecciones}

Ya hechos (no repitas tema):
{hechos}

REGLAS
- Todo lo que se dice y se lee va en neerlandés natural de los Países Bajos.
- {sin_miedo}
- Solo datos ciertos y comprobables; las cifras, las de verdad. Nada inventado ni exagerado.
- RETENCIÓN, lo primero:
  · Gancho en 1,5 segundos: la escena 1 es plano "gancho" con lo MÁS sorprendente en una cifra o afirmación enorme
    («-1 cm», «3 harten», «100.000×»). Nada de introducciones.
  · Bucle de curiosidad: la escena 2 abre una pregunta (plano "pregunta", p. ej. «Maar waarom eigenlijk?») que solo
    se responde al final, justo antes del cierre.
  · 2 o 3 datos que van subiendo de nivel (del curioso al que deja con la boca abierta), mejor con cifras.
  · Hacia la mitad, un adelanto en "aviso" («het gekste komt nog…»).
  · De 8 a 10 escenas, UNA frase corta por escena (de 4 a 11 palabras): algo nuevo cada 2 segundos.
  · La última es una pregunta a quien lo ve, con plano "final" y dos botones que peguen con el tema (p. ej.
    «wist ik al» / «nieuw voor mij», «lukt niet» / «lukt wél?!»).
- Lo más importante: CADA ESCENA ENSEÑA LO QUE DICE. Elige la ilustración y el componente que lo explican: una cifra →
  "numero"; una comparación → "barras", "escala" o plano "lado"; algo que cambia → "deslizador"; algo que se mide →
  "medidor"; una señal o un ritmo → "onda"; una parte concreta → "etiqueta" con su punto.
- "clave": la palabra más importante de la frase (copiada tal cual de "voz", con su signo si lo lleva).
- Varía los planos y los colores: alterna gancho, primer plano, gráfica, pantalla partida («vs») y cifra que sube
  («numero»); nunca el mismo plano dos veces seguidas. Nada de repetir la misma ilustración en dos escenas seguidas
  salvo que se siga hablando de lo mismo.
- Temas que enganchan de verdad: el propio cuerpo de quien lo ve, cosas cotidianas con un dato que choca, récords
  y comparaciones con cifras. Mejor «3 dingen die je niet wist over …» que un solo dato suelto.

Lo que puedes usar:
{vocabulario}

Ejemplo de la FORMA (no copies el tema):
{ejemplo}

Devuelve SOLO un JSON:
{{"titulo": "título corto con gancho, en neerlandés",
 "escenas": [{{"voz": "...", "clave": ["..."], "plano": "...", "ilustracion": "...", "ilustracion2": null, "color": "...",
              "componentes": [], "botones": null}}],
 "descripcion": "1-2 frases en neerlandés", "hashtags": ["#wistjedat", "3-5 más"],
 "texto_tiktok": "texto para pegar al subirlo (gancho + hashtags)", "texto_instagram": "lo mismo para Instagram"}}"""


def _num(v, defecto, a=None, b=None):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return defecto
    if a is not None:
        v = max(a, v)
    if b is not None:
        v = min(b, v)
    return v


def _texto(v, n):
    return str(v or "").strip()[:n]


def _ilustracion(v):
    v = str(v or "").strip()
    if v in ILUSTRACIONES:
        return v
    if v.startswith("emoji:") and 0 < len(v[6:].strip()) <= 8:
        return "emoji:" + v[6:].strip()
    return None


def _componente(o):
    if not isinstance(o, dict):
        return None
    t = o.get("tipo")
    if t == "etiqueta" and _texto(o.get("texto"), 24):
        return {"tipo": t, "texto": _texto(o.get("texto"), 24), "sub": _texto(o.get("sub"), 28),
                "punto": o.get("punto") if o.get("punto") in PUNTOS else "centro"}
    if t == "numero" and _texto(o.get("valor"), 10):
        return {"tipo": t, "valor": _texto(o.get("valor"), 10), "titulo": _texto(o.get("titulo"), 18), "sub": _texto(o.get("sub"), 24)}
    if t == "onda":
        return {"tipo": t, "label": _texto(o.get("label"), 16).upper(), "color": o.get("color") if o.get("color") in COLORES + ("wit",) else "blauw",
                "picos": int(_num(o.get("picos"), 3, 0, 5))}
    if t == "deslizador":
        desde, hasta = _num(o.get("desde"), 0), _num(o.get("hasta"), 1)
        return {"tipo": t, "label": _texto(o.get("label"), 20), "desde": desde, "hasta": hasta,
                "max": max(hasta, _num(o.get("max"), hasta)), "unidad": _texto(o.get("unidad"), 6),
                "decimales": int(_num(o.get("decimales"), 1, 0, 2)), "color": o.get("color") if o.get("color") in COLORES else "geel"}
    if t == "medidor":
        return {"tipo": t, "label": _texto(o.get("label"), 16).upper(), "valor": _num(o.get("valor"), 0.5, 0, 1),
                "texto": _texto(o.get("texto"), 18)}
    if t == "escala":
        marcas = [{"valor": _num(m.get("valor"), 0), "texto": _texto(m.get("texto"), 14), "sub": _texto(m.get("sub"), 14),
                   "color": m.get("color") if m.get("color") in COLORES + ("wit",) else "wit"}
                  for m in (o.get("marcas") or [])[:3] if isinstance(m, dict)]
        return {"tipo": t, "desde": _num(o.get("desde"), 0), "hasta": _num(o.get("hasta"), 14), "marcas": marcas,
                "izquierda": _texto(o.get("izquierda"), 14), "derecha": _texto(o.get("derecha"), 14)}
    if t == "barras":
        items = [{"label": _texto(x.get("label"), 16), "valor": _num(x.get("valor"), 50, 0, 100),
                  "color": x.get("color") if x.get("color") in COLORES else None}
                 for x in (o.get("items") or [])[:4] if isinstance(x, dict) and x.get("label")]
        return {"tipo": t, "items": items} if items else None
    if t == "pildora" and _texto(o.get("texto"), 30):
        return {"tipo": t, "texto": _texto(o.get("texto"), 30)}
    return None


def limpiar(g):
    """Deja el guion dentro de lo que sabe dibujar ciencia.html (corrige o quita lo raro en vez de fallar)."""
    escenas = []
    for i, e in enumerate((g.get("escenas") or [])[:10]):
        if not isinstance(e, dict) or not str(e.get("voz") or "").strip():
            continue
        voz = re.sub(r"\s+", " ", str(e["voz"]).strip())[:160]
        palabras = voz.split()
        claves = [c for c in (e.get("clave") or []) if isinstance(c, str) and c.strip()]
        claves = [c for c in claves if any(c.strip().lower().strip(".,!?") == p.lower().strip(".,!?") for p in palabras)][:2]
        if not claves:
            claves = [max(palabras, key=lambda p: len(p.strip(".,!?")))]
        plano = e.get("plano") if e.get("plano") in PLANOS else "grande"
        if plano == "gancho" and not _texto((e.get("golpe") or {}).get("texto"), 14):
            plano = "grande"
        if plano == "numero" and not isinstance(e.get("contador"), dict):
            plano = "grande"
        ilu = _ilustracion(e.get("ilustracion")) or ("tejido" if plano == "banda" else None if plano in ("pregunta", "gancho", "numero") else "atomo")
        ilu2 = _ilustracion(e.get("ilustracion2"))
        if plano in ("lado", "vs") and not ilu2:
            plano = "grande"
        comps = [c for c in (_componente(o) for o in (e.get("componentes") or [])[:2]) if c]
        x = {"voz": voz, "clave": claves, "plano": plano, "ilustracion": ilu, "color": e.get("color") if e.get("color") in COLORES else COLORES[i % len(COLORES)],
             "componentes": comps}
        if ilu2:
            x["ilustracion2"] = ilu2
        for k in ("resalta", "objeto", "nivel", "rapido"):
            if e.get(k) is not None:
                x[k] = e[k]
        if not x["ilustracion"]:
            x.pop("ilustracion")
        if e.get("animar") in ("comprimir", "expandir"):
            x["animar"] = e["animar"]
        if plano == "gancho":
            x["golpe"] = {"texto": _texto(e["golpe"].get("texto"), 14), "sub": _texto(e["golpe"].get("sub"), 30)}
        if plano == "numero":
            c = e["contador"]
            x["contador"] = {"desde": _num(c.get("desde"), 0), "hasta": _num(c.get("hasta"), 0), "decimales": int(_num(c.get("decimales"), 0, 0, 2)),
                             "prefijo": _texto(c.get("prefijo"), 4), "sufijo": _texto(c.get("sufijo"), 6), "label": _texto(c.get("label"), 28)}
        if plano == "vs":
            for k in ("izquierda", "derecha", "izquierda_sub", "derecha_sub"):
                if e.get(k):
                    x[k] = _texto(e[k], 18)
            x["color2"] = e.get("color2") if e.get("color2") in COLORES else ("roze" if x["color"] != "roze" else "blauw")
        if _texto(e.get("aviso"), 30):
            x["aviso"] = _texto(e.get("aviso"), 30)
        escenas.append(x)
    if len(escenas) < 3:
        raise ValueError("el guion tiene muy pocas escenas")
    for e in escenas[:-1]:
        if e["plano"] == "final":
            e["plano"] = "grande"
    ultima = escenas[-1]
    ultima["plano"] = "final"
    botones = [str(b).strip()[:18] for b in ((g.get("escenas") or [{}])[-1].get("botones") or []) if str(b).strip()]
    ultima["botones"] = botones[:2] if len(botones) >= 2 else BOTONES
    ultima["componentes"] = []
    g["escenas"] = escenas
    g["formato"], g["html"], g["cabecera"] = "ciencia", "ciencia.html", "WIST JE DAT"
    g["titulo"] = _texto(g.get("titulo") or escenas[0]["voz"], 90)
    tags = [t if str(t).startswith("#") else f"#{t}" for t in (g.get("hashtags") or []) if str(t).strip()][:6]
    if "#wistjedat" not in [t.lower() for t in tags]:
        tags.insert(0, "#wistjedat")
    g["hashtags"] = tags
    g["descripcion"] = _texto(g.get("descripcion") or g["titulo"], 300)
    for campo in ("texto_tiktok", "texto_instagram"):
        if not str(g.get(campo) or "").strip():
            g[campo] = f"{g['titulo']} {' '.join(tags)}"
    return g


def referencias(clave):
    d = privado.leer(os.path.join("estado", "referencias", f"{privado.alias(clave)}.json"), {}) or {}
    return json.dumps(d.get("formula") or {}, ensure_ascii=False)[:4000] or "(sin fórmula todavía)"


def guionizar(canal, lecciones):
    clave = canal["clave"]
    hechos = (privado.leer(os.path.join("estado", "estudio", f"{privado.alias(clave)}.json"), {}) or {}).get("videos", [])
    texto = PLANTILLA.format(nombre=canal.get("nombre", clave), formula=referencias(clave),
                             lecciones=lecciones or "(nada todavía)",
                             hechos="\n".join(f"- {h.get('titulo')}" for h in hechos[-40:]) or "- (nada)",
                             sin_miedo=SIN_MIEDO, vocabulario=VOCABULARIO, ejemplo=json.dumps(EJEMPLO, ensure_ascii=False))
    ultimo = None
    for _ in range(3):
        g = ia.preguntar(texto, papel="guionista", temperatura=0.9)
        if isinstance(g, list) and g:
            g = g[0]
        try:
            if isinstance(g, dict):
                return limpiar(g)
        except (ValueError, TypeError, KeyError) as e:
            ultimo = e
        texto += "\n\nEl intento anterior no tenía la forma pedida. Devuelve SOLO el JSON, con 7 a 9 escenas."
    raise ValueError(f"La IA no dio un guion válido para «ciencia» ({ultimo})")


def _clave_en(e):
    """Cuándo se dice la palabra clave (segundos desde el principio del vídeo)."""
    claves = {c.lower().strip(".,!?") for c in e.get("clave", [])}
    for w in e.get("palabras", []):
        if w["p"].lower().strip(".,!?") in claves:
            return w["a"]
    return e["inicio"] + 0.6


def eventos(g):
    """Golpes de sonido para que nada pase en silencio (sin música): whoosh en cada corte, golpe en el gancho y en las
    cifras, pop en la palabra clave y en cada cosa que sale, tic-tic mientras sube un contador, brillo en el «?», el
    aviso y el final."""
    ev = []
    for i, e in enumerate(g["escenas"]):
        a, plano = e["inicio"], e.get("plano")
        if i:
            ev.append(("whoosh", max(0.0, a - 0.08), 0.55))
        tk = _clave_en(e)
        ev.append(("pop", max(0.0, tk - 0.02), 0.3))
        arranque = a + (0.15 if plano in ("dato", "grafica") else max(0.12, min(0.55, tk - a - 0.12)))
        for k, c in enumerate(e.get("componentes", [])):
            ev.append(("pop", arranque + 0.09 * k, 0.32))
            if c["tipo"] in ("deslizador", "medidor"):
                ev.append(("tic", arranque + 0.5 + 0.09 * k, 0.4))
            if c["tipo"] == "numero":
                ev.append(("golpe", arranque + 0.09 * k, 0.5))
        if plano == "gancho":
            ev += [("golpe", a + 0.04, 0.95), ("brillo", a + 0.25, 0.3)]
        elif plano == "pregunta":
            ev.append(("brillo", a + 0.05, 0.4))
        elif plano == "numero":
            ev += [("tic", a + 0.15 + 0.11 * n, 0.2) for n in range(10)] + [("golpe", a + 1.28, 0.6)]
        elif plano == "vs":
            ev += [("pop", a + 0.05, 0.35), ("pop", a + 0.14, 0.35), ("golpe", a + 0.2, 0.4)]
        elif plano == "final":
            ev += [("brillo", a + 0.35, 0.35), ("pop", a + 0.5, 0.3), ("tic", a + 1.6, 0.45)]
        if e.get("aviso"):
            ev.append(("brillo", a + 0.08, 0.35))
        if e["fin"] - a > 2.4:      # el reencuadre de la cámara a mitad de escena
            ev.append(("whoosh", a + 1.5, 0.25))
        if e["fin"] - a > 3.1:      # y el tercer golpe de cámara en las escenas largas
            ev.append(("whoosh", a + 2.55, 0.22))
        if plano == "final":
            ev += [("pop", a + 1.4 + 0.16 * n, 0.18) for n in range(4)]
    return ev
