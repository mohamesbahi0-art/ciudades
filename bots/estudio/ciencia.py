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
    («-1 cm», «3 harten», «100.000×»). Nada de introducciones. Su frase, como mucho 6 palabras: así el primer
    cambio de plano llega antes de los 2 segundos (los jueces lo miden).
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
- Si el tema es un clásico muy visto (por qué el estómago no se digiere, las uñas, las arañas…), no lo cuentes como
  siempre: dale un giro que casi nadie sabe (un dato extremo, una comparación chocante, un experimento). Los jueces
  castigan lo «muy visto».
- Que nada se pise: en cada escena, la ilustración, la etiqueta y la cifra van en sitios distintos y caben enteras.

REPASO ANTES DE ENTREGAR (lo que más suspenden los jueces; compruébalo escena a escena):
1. Cada cifra que sale en pantalla (contador, barras, etiquetas, gráfica) es EXACTAMENTE la que dice la voz en esa escena.
2. La primera escena enseña ya, entera y en grande, lo más chocante (la cifra final o la paradoja); nada de empezar en 0.
3. Ningún rótulo o etiqueta pasa de 3 palabras ni repite lo que ya dice el texto grande de esa escena.
4. El tema no está en la lista de ya hechos ni se parece: si es un clásico del nicho, cámbialo o dale un giro nuevo.
5. Cada escena cambia lo que se ve (otra pieza, otro plano, otro color): nunca dos escenas seguidas iguales.
6. Lo que se lee y lo que se oye dicen lo mismo con las mismas palabras (si la voz dice «duizend keer», en pantalla
   «1000×», no otra cifra); ninguna palabra sale dos veces en la primera escena.

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
    """Recorta a n caracteres sin dejar media palabra («DANI FUMADOR EMP» → «DANI FUMADOR»): los jueces lo ven."""
    t = str(v or "").strip()
    if len(t) <= n:
        return t
    if " " not in t[:n + 1]:
        return t[:n]
    corte = t[:n + 1].rsplit(" ", 1)[0].rstrip(" ,.;:-–")
    # nada de dejar la frase colgando de un «van de» o un «uit de» («18–35% van de», «zuurstof rechtstreeks uit de»)
    while " " in corte and _norm(corte.rsplit(" ", 1)[1]) in COLGANTES:
        corte = corte.rsplit(" ", 1)[0].rstrip(" ,.;:-–")
    return corte if len(corte) >= max(3, n // 3) else t[:n]


COLGANTES = set("de het een van voor met en of om te naar bij tot dan per zonder tussen tegen omdat maar want uit in op "
                "aan door over als die dat je zijn haar hun".split())
_UNIDADES = {"nul": 0, "een": 1, "twee": 2, "drie": 3, "vier": 4, "vijf": 5, "zes": 6, "zeven": 7, "acht": 8, "negen": 9,
             "tien": 10, "elf": 11, "twaalf": 12, "dertien": 13, "veertien": 14, "vijftien": 15, "zestien": 16,
             "zeventien": 17, "achttien": 18, "negentien": 19, "twintig": 20, "dertig": 30, "veertig": 40, "vijftig": 50,
             "zestig": 60, "zeventig": 70, "tachtig": 80, "negentig": 90}


def _numero_nl(p):
    """Una cifra escrita en neerlandés («veertigduizend», «tweehonderddrieenveertig») → número; None si no lo es."""
    if p in _UNIDADES:
        return _UNIDADES[p]
    for nombre, valor in (("miljard", 10 ** 9), ("miljoen", 10 ** 6), ("duizend", 1000), ("honderd", 100)):
        if nombre in p:
            antes, despues = p.split(nombre, 1)
            a, d = (_numero_nl(antes) if antes else 1), (_numero_nl(despues) if despues else 0)
            return None if a is None or d is None else a * valor + d
    if "en" in p:                                   # «vijfendertig» = vijf + dertig
        for i in range(2, len(p) - 4):
            if p[i:i + 2] == "en" and p[:i] in _UNIDADES and _UNIDADES.get(p[i + 2:], 0) >= 20:
                return _UNIDADES[p[:i]] + _UNIDADES[p[i + 2:]]
    return None


def _cifras_voz(voz):
    """Las cifras que dice la voz de una escena, en número («40.000», «veertigduizend», «zes miljard»)."""
    salida, palabras = [], str(voz or "").split()
    for i, p in enumerate(palabras):
        limpia = p.strip(".,;:!?()«»\"'")
        m = re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?", limpia)
        v = float(limpia.replace(".", "").replace(",", ".")) if m else _numero_nl(_norm(limpia))
        if v is None or (v == 1 and not m):          # «een» casi siempre es el artículo
            continue
        siguiente = _norm(palabras[i + 1]) if i + 1 < len(palabras) else ""
        salida.append(float(v) * {"miljard": 10 ** 9, "miljoen": 10 ** 6, "duizend": 1000}.get(siguiente, 1))
    return salida


def _cifra_que_dice(voz, valor):
    """La cifra de un contador o de un deslizador tiene que ser la que dice la voz: si la voz dice otra del mismo orden
    (o la misma con los ceros bailados), manda la voz. Si no está claro, se queda como venía."""
    dichas = [x for x in _cifras_voz(voz) if x > 0]
    if not dichas or valor <= 0 or any(abs(x - valor) <= 0.02 * max(x, valor) for x in dichas):
        return valor
    for x in sorted(dichas, key=lambda x: abs(x - valor)):
        if 0.5 <= x / valor <= 2 or any(abs(x / valor - f) < 1e-9 for f in (10, 100, 1000, 0.1, 0.01, 0.001)):
            return x
    return valor


def _fichas(texto):
    t = re.sub(r"(\d)\.(?=\d{3}(\D|$))", r"\1", str(texto or "").lower())
    return [_norm(x) for x in re.findall(r"\d+(?:,\d+)?|[^\W\d_]+", t) if _norm(x)]


def _repite(texto, voz):
    """¿Este rótulo (de dos palabras o más) ya lo dice, tal cual, la frase de arriba? Los jueces lo ven como repetido."""
    a, b = _fichas(texto), _fichas(voz)
    return len(a) >= 2 and any(b[i:i + len(a)] == a for i in range(len(b) - len(a) + 1))


def _sin_repetir(c, voz):
    """Quita de un componente los rótulos que repiten la frase de arriba; None si se queda sin nada que enseñar."""
    for campo in ("sub", "titulo", "label"):
        if c.get(campo) and _repite(c[campo], voz):
            c[campo] = ""
    if c["tipo"] in ("etiqueta", "pildora") and _repite(c.get("texto"), voz):
        return None
    if c["tipo"] == "deslizador":
        c["hasta"] = _cifra_que_dice(voz, c["hasta"])
        c["max"] = max(c["max"], c["hasta"])
    return c


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
                "texto": _texto(o.get("texto"), 26)}
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
        comps = [c for c in (_sin_repetir(c, voz) for c in comps) if c]       # ningún rótulo repite la frase de arriba
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
            x["contador"] = {"desde": _num(c.get("desde"), 0), "hasta": _cifra_que_dice(voz, _num(c.get("hasta"), 0)), "decimales": int(_num(c.get("decimales"), 0, 0, 2)),
                             "prefijo": _texto(c.get("prefijo"), 4), "sufijo": _texto(c.get("sufijo"), 6), "label": _texto(c.get("label"), 28)}
        if plano == "vs":
            for k in ("izquierda", "derecha", "izquierda_sub", "derecha_sub"):
                if e.get(k):
                    x[k] = _texto(e[k], 18)
            x["color2"] = e.get("color2") if e.get("color2") in COLORES else ("roze" if x["color"] != "roze" else "blauw")
        if _texto(e.get("aviso"), 30) and not _repite(e.get("aviso"), voz):     # si la frase ya lo dice, no se duplica
            x["aviso"] = _texto(e.get("aviso"), 30)
        escenas.append(x)
    if len(escenas) < 3:
        raise ValueError("el guion tiene muy pocas escenas")
    for e in escenas[:-1]:
        if e["plano"] == "final":
            e["plano"] = "grande"
    ultima = escenas[-1]
    ultima["plano"] = "final"
    botones = [_texto(b, 22) for b in ((g.get("escenas") or [{}])[-1].get("botones") or []) if str(b).strip()]
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


def guionizar(canal, lecciones, arreglar=None):
    from bots.estudio import estudio
    clave = canal["clave"]
    hechos = (privado.leer(os.path.join("estado", "estudio", f"{privado.alias(clave)}.json"), {}) or {}).get("videos", [])
    texto = PLANTILLA.format(nombre=canal.get("nombre", clave), formula=referencias(clave),
                             lecciones=lecciones or "(nada todavía)",
                             hechos="\n".join(f"- {t}" for t in dict.fromkeys([h.get("titulo") for h in hechos[-40:]] +
                                                                                privado.intentados(clave)) if t) or "- (nada)",
                             sin_miedo=SIN_MIEDO, vocabulario=VOCABULARIO, ejemplo=json.dumps(EJEMPLO, ensure_ascii=False))
    texto += estudio.bloque_arreglo(arreglar)
    ultimo = None
    for _ in range(3):
        g = ia.preguntar(texto, papel="arreglo" if arreglar else "guionista", temperatura=0.9)
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


def _norm(texto):
    import unicodedata
    texto = unicodedata.normalize("NFD", str(texto).lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in texto if not unicodedata.combining(c)))


def _entradas(e):
    """Cuándo entra cada componente, igual que en ciencia.html: encadenados (cada uno cuando aterriza el anterior) o
    justo cuando la voz dice lo suyo."""
    a, plano = e["inicio"], e.get("plano")
    arranque = a + (0.15 if plano in ("dato", "grafica") else max(0.12, min(0.55, _clave_en(e) - a - 0.12)))
    salida = []
    for c in (e.get("componentes") or [])[:3]:
        previo = salida[-1] + 0.24 if salida else arranque
        buscar = [_norm(str(v).split()[0]) for v in (c.get("hasta"), c.get("valor"), c.get("texto"), c.get("label"))
                  if v not in (None, "") and str(v).split()]
        dicho = next((w["a"] for w in e.get("palabras", []) if _norm(w.get("p", "")) in buscar), None)
        salida.append(max(previo, dicho - 0.08) if dicho is not None else previo)
    return salida


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
        for c, t0 in zip((e.get("componentes") or [])[:3], _entradas(e)):     # cada uno cuando entra (encadenados)
            ev.append(("pop", t0, 0.32))
            if c["tipo"] in ("deslizador", "medidor"):
                ev.append(("tic", t0 + 0.5, 0.4))
            if c["tipo"] == "numero":
                ev.append(("golpe", t0, 0.5))
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
