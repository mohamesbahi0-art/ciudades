"""«Bolas» (el Dibujante de mapas): vídeos de humor «¿Qué pasaría si un país desapareciera?» con
bolas-país de verdad (su bandera, sus ojos y su cara) sobre un mapa del mundo de verdad, en series de 3 partes.

- El Archivero de mapas (archivero_mapas.py) dice qué país y qué parte tocan. Cada vídeo se entiende solo.
- El guionista escribe 8-10 escenas de 12 palabras de voz como mucho (35-45 s) y solo con lo que el formato sabe dibujar;
  `revisar` le devuelve con números lo que no cumple y `limpiar` arregla lo que quede (parte la voz larga, quita la bola
  del país borrado, pone como objeto lo que prometa el título).
- El Cartógrafo (cartografo.py) pone a cada escena su encuadre y a cada bola su sitio en el mapa.
- bolas.html lo dibuja: el país YA está borrado en el primer fotograma (hueco negro con borde rojo y vecinos asomados),
  la toma cambia cada 2,3 s como mucho (la primera, en el segundo 1,25) y el mapa cambia a la vista: entra el agua, el
  hueco crece, una bola se cae dentro, un vecino conquista un trozo o un objeto (un emoji) cae y lo tapa.
Mapas: Natural Earth (dominio público). Banderas: flag-icons (MIT). Música: la de la fábrica (compuesta o dominio público).
"""
import json
import re

from bots.comun import ia
from bots.estudio import archivero_mapas, cartografo

MUSICA = "energia"
PLANOS = ("mundo", "zona", "pais", "bolas")
# Lo que bolas.html SABE dibujar. Las cinco últimas cambian el mapa a la vista (y lo que cambian se queda cambiado).
ACCIONES = ("salta", "llora", "rie", "pelea", "corre", "celebra", "tiembla", "mira", "habla",
            "agua", "crece", "cae", "conquista", "tapa")
CAMBIAN = ("agua", "crece", "cae", "conquista", "tapa")
EXPRESIONES = ("feliz", "triste", "enfadado", "sorprendido", "malvado", "asustado", "neutral")
PALETA = ["#F7C873", "#9AD3A8", "#F4A6A6", "#A9C6F5", "#D7B4F3", "#F9E48B", "#8FD6D1", "#F5B98A", "#C5E384",
          "#E8A7C9", "#B5C7D3", "#F2D0A4"]
PALABRAS_ESCENA = 12            # lo pidió el Cerebro: 12 palabras de voz como mucho por escena…
PALABRAS_VIDEO = (65, 100)      # …y de 35 a 45 segundos (lo que dicen el narrador y las bolas, todo junto)
PREGUNTA = "¿QUIÉN SE QUEDA EL HUECO? 👇"
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿][️\U0001F3FB-\U0001F3FF]?")
_CARAS = re.compile("[\U0001F600-\U0001F64F\U0001F910-\U0001F92F\U0001F970-\U0001F97A\U0001F9D0\U0001FAE0-\U0001FAE8"
                    "\U0001F440\U0001F446-\U0001F449\U0001F525❓-❗⭐✨\U0001F4A5\U0001F30D-\U0001F30F"
                    "\U0001F5FA]")      # caras, flechas, fuego, mundo…: adornos del título, no promesas que haya que dibujar
_DEPENDE = re.compile(r"\bparte\s*(\d|uno|dos|tres|anterior|siguiente)|\b(como vimos|seguimos con|continuamos|"
                      r"en el v[ií]deo anterior|lo que pas[oó] despu[eé]s|ma[ñn]ana,? la)", re.I)

PLANTILLA = """Eres el guionista de «{nombre}», un canal de YouTube Shorts de humor con bolas-país (countryballs): «¿Qué
pasaría si un país desapareciera?». Hoy toca {pais_nombre}. Ángulo de hoy: {angulo}
{anteriores}
Así son los vídeos:
- El vídeo SE ENTIENDE SOLO: quien lo ve no ha visto ningún otro. Nada de «Parte 2», «como vimos», «seguimos» ni
  «mañana la siguiente»; la primera frase presenta la premisa ({pais_nombre} ha desaparecido y hay un hueco).
- Desde el primer fotograma {pais_nombre} YA está borrado: se ve el hueco negro con el borde rojo y los vecinos asomados.
  El país no vuelve a salir pintado y su bola no sale (ya no existe): no la pongas.
- De 35 a 45 segundos: de 8 a 10 escenas y entre 75 y 95 palabras en total. Cada "voz" tiene {maximo} PALABRAS COMO MUCHO
  (una sola frase corta). La imagen cambia cada 2 segundos: en cada escena tiene que PASAR algo en el mapa.
- Consecuencias en cadena, cada una más loca que la anterior, con cosas reales de fondo (lo que exporta, su comida, su
  música, su fútbol, su geografía, sus récords). Un dato solo entra si en esa misma escena se ve su consecuencia en el
  hueco o en una bola vecina. Nada de desvíos que no tocan el hueco.
- Los últimos 4 segundos son el pago: se ve quién o qué se queda el hueco, y acaba con una pregunta corta.
- Humor blanco y sin odio: tópicos simpáticos de comida, fútbol, música y costumbres. Nada de religión, etnias,
  pobreza, guerras, terrorismo ni violencia de verdad, ni burlas que ofendan a la gente de un país.

Lo que ha aprendido el canal (lo del dueño manda):
{lecciones}

LO ÚNICO QUE SE PUEDE DIBUJAR (si la voz o el título prometen otra cosa, NO vale: cámbialo por algo de esta lista)
- El mapa de verdad, el hueco de {pais_nombre} y bolas-país con su bandera, su cara y su bocadillo.
- "accion" de la escena, una de: {acciones}.
  · "agua": el mar entra en el hueco y lo va llenando.  · "crece": el hueco se hace más grande y se come la frontera.
  · "cae": la primera bola de la escena se cae dentro del hueco.
  · "conquista": la primera bola estira su color y se queda un trozo del hueco (el mapa cambia de color a la vista).
  · "tapa": el "objeto" de la escena cae gigante sobre el hueco y lo tapa (y ahí se queda).
  · "pelea", "corre" (hacia el hueco), "salta", "llora", "rie", "celebra" (confeti), "tiembla", "mira", "habla".
  Usa "agua", "crece", "cae", "conquista" o "tapa" al menos en 4 escenas, y no repitas la misma acción dos veces seguidas.
- "objeto": UN emoji (o vacío) que cae del cielo sobre el hueco en esa escena: 🫓, ⚽, 🌮, 👑, 🚢… Es la única manera de
  enseñar una cosa que no sea una bola. Si la voz nombra una cosa (una arepa, un balón, un barco), esa escena lleva su
  emoji en "objeto". Si no hay emoji para algo, no lo prometas.
- El título solo promete lo que se ve: bolas, banderas, colores, agua, el hueco o un "objeto" que salga en una escena.

REGLAS DEL GUION
- "plano": "mundo" (el mapa entero), "zona" (el hueco y sus vecinos), "pais" (el hueco de cerca) o "bolas" (las bolas
  hablando de cerca, con el mapa detrás). La primera escena es "pais"; alterna planos y no repitas el mismo dos veces seguidas.
- "foco": el código ISO de 2 letras del país al que mira la cámara (normalmente {pais}, o el de la consecuencia).
- "bolas": de 1 a 4 bolas en escena, cada una {{"pais": "FR", "expresion": una de {expresiones}, "dice": "bocadillo de
  5 palabras como mucho, o vacío"}}. Países de verdad y que pegan (vecinos, rivales, socios), cada uno con SU código.
- "texto": de 1 a 3 palabras grandes en pantalla, la clave de la escena.
- "voz": lo que dice el narrador (números escritos como se dicen), {maximo} palabras como mucho.
- Lo que "dice" cada bola SE OYE: lo dice ella con la voz de su país, justo después del narrador. Que sea una réplica
  corta y con gracia (de 2 a 5 palabras, como hablaría ese país), y que el narrador no la repita. Como mucho 4 bolas
  hablan en todo el vídeo.
Vecinos de {pais_nombre}: {vecinos}.
Ya hechos en el canal (no repitas chistes ni títulos):
{hechos}

Devuelve SOLO un JSON:
{{"titulo": "{pais_nombre} desaparece y … (un final gracioso QUE SE VEA en el vídeo, con 1 o 2 emojis)",
  "texto_pantalla": "el gancho de arriba, como mucho 40 caracteres (p. ej. ¿Y SI {mayus} DESAPARECIERA?)",
  "pregunta": "la pregunta corta del final, como mucho 30 caracteres (p. ej. ¿Quién se queda el hueco? 👇)",
  "donde_se_ve": "el número de la escena en la que se ve lo que promete el título",
  "descripcion": "2 frases con gancho y de 3 a 5 hashtags (#shorts #countryballs …)",
  "escenas": [{{"voz": "…", "plano": "pais", "foco": "{pais}", "accion": "crece", "objeto": "", "texto": "…",
               "bolas": [{{"pais": "{ejemplo}", "expresion": "sorprendido", "dice": "¿Y el vecino?"}}]}}]}}"""
ANGULOS = ("los vecinos se pelean por quedarse el hueco y se lo van repartiendo.",
           "el caos en el resto del mundo: lo que deja de llegar y quién se cuela en el hueco.",
           "el final más loco: qué acaba ocupando el hueco para siempre.")


def _iso(x):
    x = str(x or "").strip().upper()
    return x if len(x) == 2 and cartografo.tiene_bandera(x) else None


def _color(iso):
    return PALETA[sum(ord(c) for c in iso) % len(PALETA)]


def _palabras(t):
    return len(re.findall(r"\w+", str(t or "")))


def _trocear(voz, maximo=PALABRAS_ESCENA):
    """Una voz larga, en trozos de `maximo` palabras como mucho, cortando por donde se respira."""
    trozos = [voz]
    for corte in (r"(?<=[.!?…])\s+", r"(?<=[,;:])\s+", r"\s+(?=(?:y|pero|porque|mientras)\s)"):
        trozos = [x for t in trozos for x in (re.split(corte, t) if _palabras(t) > maximo else [t]) if x.strip()]
    salida = []
    for t in trozos:
        ws = t.split()
        while len(ws) > maximo:                      # sin sitio donde respirar: a partes iguales
            n = -(-len(ws) // -(-len(ws) // maximo))
            salida.append(" ".join(ws[:n]))
            ws = ws[n:]
        if not ws:
            continue
        if salida and _palabras(salida[-1]) + len(ws) <= maximo:     # los trozos que caben juntos van juntos
            salida[-1] += " " + " ".join(ws)
        else:
            salida.append(" ".join(ws))
    return salida


def _objetos_titulo(titulo):
    """Los emojis del título que prometen una COSA (no las caras ni los adornos)."""
    return [x for x in EMOJI.findall(str(titulo or "")) if not _CARAS.match(x)]


def revisar(g):
    """Lo que el guion recién escrito NO cumple del plan del Cerebro (lista vacía: todo bien). Se le dice al guionista."""
    pegas, escenas = [], [e for e in g.get("escenas") or [] if isinstance(e, dict) and str(e.get("voz") or "").strip()]
    largas = [i + 1 for i, e in enumerate(escenas) if _palabras(e["voz"]) > PALABRAS_ESCENA]
    if largas:
        pegas.append(f"la voz de las escenas {largas} pasa de {PALABRAS_ESCENA} palabras: acórtalas")
    total = sum(_palabras(e["voz"]) + sum(_palabras(b.get("dice")) for b in e.get("bolas") or [] if isinstance(b, dict))
                for e in escenas)
    if not PALABRAS_VIDEO[0] <= total <= PALABRAS_VIDEO[1]:
        pegas.append(f"el vídeo tiene {total} palabras y tiene que tener entre 75 y 95 (de 35 a 45 segundos)")
    if not 7 <= len(escenas) <= 11:
        pegas.append(f"tiene {len(escenas)} escenas y tienen que ser de 8 a 10")
    textos = " ".join([str(g.get("texto_pantalla") or "")] + [f"{e['voz']} {e.get('texto') or ''}" for e in escenas])
    if _DEPENDE.search(textos):
        pegas.append("habla de otra «parte» o de otro vídeo: este se tiene que entender solo")
    if sum(e.get("accion") in CAMBIAN for e in escenas) < 3:
        pegas.append("el mapa casi no cambia: usa «agua», «crece», «cae», «conquista» o «tapa» al menos en 4 escenas")
    objetos = {x for e in escenas for x in EMOJI.findall(str(e.get("objeto") or ""))}
    faltan = [x for x in _objetos_titulo(g.get("titulo")) if x not in objetos]
    if faltan:
        pegas.append(f"el título promete {' '.join(faltan)} y ninguna escena lo lleva en \"objeto\": ponlo o quítalo del título")
    return pegas


def limpiar(g):
    """El guion, dentro de lo que sabe dibujar bolas.html (con encuadres y sitios ya calculados)."""
    pais = _iso(g.get("pais")) or "ES"
    parte, partes = int(g.get("parte") or 1), int(g.get("partes") or 1)
    m = cartografo.mundo()
    cerca = [v for v in cartografo.vecinos(pais, 6) if cartografo.tiene_bandera(v)]
    escenas = []
    for e in g.get("escenas") or []:
        if not isinstance(e, dict) or not str(e.get("voz") or "").strip():
            continue
        plano = e.get("plano") if e.get("plano") in PLANOS else "zona"
        foco = _iso(e.get("foco")) if cartografo.existe(_iso(e.get("foco")) or "") else pais
        bolas = []
        for b in (e.get("bolas") or [])[:5]:
            iso = _iso((b or {}).get("pais")) if isinstance(b, dict) else None
            if not iso or iso == pais or any(x["pais"] == iso for x in bolas):    # la bola del país borrado ya no existe
                continue
            bolas.append({"pais": iso, "expresion": b.get("expresion") if b.get("expresion") in EXPRESIONES else "neutral",
                          "dice": str(b.get("dice") or "")[:40]})
        bolas = bolas[:4]
        if not bolas:                                    # nunca una escena sin nadie: se asoma un vecino
            bolas = [{"pais": v, "expresion": "sorprendido", "dice": ""} for v in cerca[len(escenas) % 2:][:1]]
        accion = e.get("accion") if e.get("accion") in ACCIONES else ("mira" if e.get("accion") == "desaparece" else "habla")
        objeto = (EMOJI.findall(str(e.get("objeto") or "")) or [""])[0]
        if accion == "tapa" and not objeto:
            accion = "mira"
        trozos = _trocear(str(e["voz"]).strip())         # 12 palabras por escena como mucho: la que se pasa, se parte
        for k, voz in enumerate(trozos):
            ultimo = k == len(trozos) - 1
            escenas.append({"voz": voz, "texto": str(e.get("texto") or "")[:24],
                            "plano": plano if k == 0 else ("zona" if plano == "bolas" else "bolas"), "foco": foco,
                            "accion": accion if k == 0 else "mira", "objeto": objeto if k == 0 else "",
                            "bolas": [dict(b, dice=b["dice"] if ultimo else "") for b in bolas]})
    if len(escenas) < 5:
        raise ValueError("el guion de bolas necesita al menos 5 escenas con voz")
    escenas = escenas[:13]
    g["borrado_desde"] = 0                               # el país ya está borrado en el primer fotograma, siempre
    primera = escenas[0]                                 # el arranque: el hueco de cerca y, al menos, dos vecinos asomados
    primera["plano"], primera["foco"] = "pais", pais
    for v in cerca:
        if len(primera["bolas"]) >= 2:
            break
        if all(b["pais"] != v for b in primera["bolas"]):
            primera["bolas"].append({"pais": v, "expresion": "asustado", "dice": ""})
    objetos = {e["objeto"] for e in escenas}
    for x in _objetos_titulo(g.get("titulo")):           # lo que promete el título se ve, como tarde, en el pago final
        destino = next((e for e in reversed(escenas) if not e["objeto"]), None)
        if x not in objetos and destino:
            destino["objeto"], destino["accion"] = x, "tapa"
            objetos.add(x)
    for e in escenas:
        otros = [b["pais"] for b in e["bolas"] if cartografo.existe(b["pais"]) and b["pais"] != e["foco"]]
        e["caja"] = cartografo.encuadre(e["plano"], e["foco"], otros if e["plano"] == "zona" else ())
        if e["plano"] == "pais" and e["foco"] == pais and pais in m["paises"]:   # el hueco, bien grande: media pantalla
            x0, y0, x1, y1 = m["paises"][pais]["caja"]
            lado = max((x1 - x0) * 1.75, (y1 - y0) * 1.5, 40)
            e["caja"] = [round((x0 + x1) / 2 - lado / 2), round((y0 + y1) / 2 - lado / 2),
                         round((x0 + x1) / 2 + lado / 2), round((y0 + y1) / 2 + lado / 2)]
        for k, b in enumerate(e["bolas"]):
            p = m["paises"].get(b["pais"]) or m["paises"].get(e["foco"]) or {"centro": [m["ancho"] / 2, m["alto"] / 2]}
            b["x"], b["y"] = p["centro"][0] + (0 if b["pais"] in m["paises"] else 60 * (k + 1)), p["centro"][1]
    hablan = 0
    for e in escenas:                    # lo que dice cada bola suena con la voz de su país, detrás del narrador
        e["voces"] = [dict(voz_de(b["pais"]), texto=b["dice"], pais=b["pais"]) for b in e["bolas"]
                      if len(re.findall(r"\w", b.get("dice") or "")) >= 2][:1 if hablan < 4 else 0]
        hablan += len(e["voces"])        # una por escena y cuatro en todo el vídeo: lo demás, solo en el bocadillo
    g["escenas"] = escenas
    g["pais"], g["parte"], g["partes"] = pais, parte, partes
    g["pais_nombre"] = cartografo.nombre(pais)
    g["mapa"] = {iso: {"d": p["d"], "c": _color(iso)} for iso, p in m["paises"].items() if iso not in ("AQ", "TF")}
    g["mundo"] = [m["ancho"], m["alto"]]
    hueco, c0 = m["paises"].get(pais) or {}, primera["caja"]
    g["hueco"] = {"caja": hueco.get("caja") or c0,
                  "centro": hueco.get("centro") or [(c0[0] + c0[2]) / 2, (c0[1] + c0[3]) / 2]}
    titulo = str(g.get("titulo") or f"{g['pais_nombre']} desaparece").replace("#shorts", "").strip()
    if not titulo.lower().startswith(g["pais_nombre"].lower()):    # el Archivero sigue las series por el título
        titulo = f"{g['pais_nombre']}: {titulo}"
    if partes > 1 and f"(Parte {parte})" not in titulo:
        titulo = archivero_mapas.PARTE.sub("", titulo).strip() + f" (Parte {parte})"
    g["titulo"] = (titulo[:88] + " #shorts").strip()
    gancho = re.sub(r"\(?\bparte\s*\d+(\s*/\s*\d+)?\)?", "", str(g.get("texto_pantalla") or ""), flags=re.I).strip(" :-·")
    g["texto_pantalla"] = (gancho or f"¿Y SI {g['pais_nombre'].upper()} DESAPARECIERA?")[:40]
    pregunta = str(g.get("pregunta") or "").strip()
    g["pregunta"] = (pregunta if 6 <= len(pregunta) <= 34 and not _DEPENDE.search(pregunta) else PREGUNTA).upper()
    desc = str(g.get("descripcion") or "").strip()
    if "Natural Earth" not in desc:
        desc += "\n\nMapas: Natural Earth (dominio público). Banderas: flag-icons (MIT)."
    g["descripcion"] = desc.strip()
    g["formato"], g["html"] = "bolas", "bolas.html"
    g["narracion"] = " ".join(e["voz"] for e in escenas)
    return g


# Cada bola-país habla con SU voz (lo pidió el dueño): los países que hablan español, con una voz de su país; los
# demás, con una voz de su idioma que sabe hablar español (se le nota el acento) o, si no hay, con una voz propia sacada
# de su código (siempre la misma para ese país: más aguda o más grave, más rápida o más lenta).
VOCES_PAIS = {"ES": "es-ES-AlvaroNeural", "MX": "es-MX-JorgeNeural", "AR": "es-AR-TomasNeural", "CO": "es-CO-GonzaloNeural",
              "VE": "es-VE-SebastianNeural", "CL": "es-CL-LorenzoNeural", "PE": "es-PE-AlexNeural", "CU": "es-CU-ManuelNeural",
              "UY": "es-UY-MateoNeural", "PY": "es-PY-MarioNeural", "BO": "es-BO-MarceloNeural", "EC": "es-EC-LuisNeural",
              "CR": "es-CR-JuanNeural", "PA": "es-PA-RobertoNeural", "DO": "es-DO-EmilioNeural", "GT": "es-GT-AndresNeural",
              "HN": "es-HN-CarlosNeural", "NI": "es-NI-FedericoNeural", "SV": "es-SV-RodrigoNeural", "PR": "es-PR-VictorNeural",
              "GQ": "es-GQ-JavierNeural", "US": "en-US-AndrewMultilingualNeural", "GB": "en-US-BrianMultilingualNeural",
              "FR": "fr-FR-RemyMultilingualNeural", "DE": "de-DE-FlorianMultilingualNeural", "IT": "it-IT-GiuseppeMultilingualNeural",
              "BR": "pt-BR-ThalitaMultilingualNeural", "PT": "pt-BR-ThalitaMultilingualNeural", "KR": "ko-KR-HyunsuMultilingualNeural",
              "CA": "en-US-AvaMultilingualNeural", "AU": "en-AU-WilliamMultilingualNeural", "BE": "fr-FR-VivienneMultilingualNeural",
              "AT": "de-DE-SeraphinaMultilingualNeural", "CH": "de-DE-SeraphinaMultilingualNeural"}
VOCES_RESTO = ("es-ES-ElviraNeural", "es-MX-DaliaNeural", "es-ES-XimenaNeural", "es-US-AlonsoNeural", "es-US-PalomaNeural",
               "es-MX-JorgeNeural", "es-AR-ElenaNeural", "es-CO-SalomeNeural")
RESERVA_VOZ = "es-ES-AlvaroNeural"


def voz_de(pais):
    """La voz de una bola-país: {"voz", "velocidad", "tono"} (siempre la misma para ese país)."""
    iso = str(pais or "").upper()
    if iso in VOCES_PAIS:
        return {"voz": f"{VOCES_PAIS[iso]}|{RESERVA_VOZ}", "velocidad": "+6%", "tono": "+0Hz"}
    n = sum(ord(c) * (i + 3) for i, c in enumerate(iso))
    return {"voz": f"{VOCES_RESTO[n % len(VOCES_RESTO)]}|{RESERVA_VOZ}", "velocidad": f"{(n % 5) * 3:+d}%",
            "tono": f"{((n // 5) % 7 - 3) * 6:+d}Hz"}


def guionizar(canal, lecciones, arreglar=None):
    """El Archivero elige país y parte; el guionista escribe; el Cartógrafo encuadra (en limpiar).
    Con `arreglar` (la versión suspendida y lo que le vieron los jueces) rehace esa misma parte corrigiéndola."""
    clave = canal.get("clave", "mapas")
    toca = archivero_mapas.siguiente(clave)
    hechos = archivero_mapas.titulos(clave)[-40:]
    anteriores = ("Otros vídeos del canal sobre este país (NO los continúes ni los nombres; no repitas sus chistes):\n" +
                  "\n".join(f"- {t}" for t in toca["anteriores"])) if toca["anteriores"] else ""
    cerca = cartografo.vecinos(toca["pais"], 6)
    texto = PLANTILLA.format(
        nombre=canal.get("nombre", clave), pais=toca["pais"], pais_nombre=toca["nombre"], mayus=toca["nombre"].upper(),
        angulo=ANGULOS[(toca["parte"] - 1) % len(ANGULOS)], anteriores=anteriores, lecciones=lecciones or "(nada todavía)",
        acciones=", ".join(ACCIONES), expresiones=", ".join(EXPRESIONES), maximo=PALABRAS_ESCENA,
        ejemplo=next((v for v in cerca if cartografo.tiene_bandera(v)), "FR"),
        vecinos=", ".join(f"{cartografo.nombre(v)} ({v})" for v in cerca) or "ninguno",
        hechos="\n".join(f"- {t}" for t in hechos) or "- (nada)")
    if arreglar:
        from bots.estudio import estudio
        texto += estudio.bloque_arreglo(arreglar)
    ultimo, intentos = None, 3
    for n in range(intentos):
        g = ia.preguntar(texto, papel="arreglo" if arreglar else "guionista", temperatura=0.95)
        if isinstance(g, list) and g:
            g = g[0]
        try:
            if isinstance(g, dict):
                pegas = revisar(g)
                if pegas and n < intentos - 1:          # se le dice con números qué cambiar; a la tercera, va lo que haya
                    texto += ("\n\nEl intento anterior NO vale. Corrige esto y devuelve el JSON entero otra vez:\n" +
                              "\n".join(f"- {p}" for p in pegas))
                    continue
                g.update(pais=toca["pais"], parte=toca["parte"], partes=toca["partes"])
                g = limpiar(g)
                archivero_mapas.apuntar(clave, toca, g["titulo"])
                return g
        except (ValueError, TypeError, KeyError) as e:
            ultimo = e
        texto += "\n\nEl intento anterior no tenía la forma pedida. Devuelve SOLO el JSON, con 8 a 10 escenas."
    raise ValueError(f"La IA no dio un guion válido para «bolas» ({ultimo})")


TOMA = 2.3          # lo pidió el Cerebro: la imagen cambia cada 2,5 s como mucho (lo mismo hace bolas.html)


def cortes(e, primera=False):
    """Los segundos en los que cambia la toma dentro de una escena (igual que `tomas` en bolas.html)."""
    c = [e["inicio"]]
    if primera and e["fin"] - e["inicio"] > 1.9:
        c.append(e["inicio"] + 1.25)                 # el primer corte, antes del segundo 1,5
    resto = e["fin"] - c[-1]
    n = max(1, int(-(-resto // TOMA)))
    return c + [c[-1] + resto * k / n for k in range(1, n)]


def eventos(g):
    """Golpe al empezar y en el primer corte, whoosh en cada cambio de toma, pop cuando habla una bola y un golpe cuando
    el mapa cambia (el hueco crece, entra el agua, cae una bola, alguien conquista un trozo o cae un objeto)."""
    ev = [("golpe", 0.04, 0.7)]
    for i, e in enumerate(g["escenas"]):
        for k, t in enumerate(cortes(e, i == 0)):
            if i == 0 and k == 1:
                ev.append(("golpe", t, 0.6))
            elif i or k:
                ev.append(("whoosh", max(0.0, t - 0.05), 0.35 if k == 0 else 0.22))
        if e["accion"] in CAMBIAN or e.get("objeto"):
            ev.append(("golpe", e["inicio"] + 0.55, 0.8))
        for k, b in enumerate(e["bolas"]):
            if b.get("dice"):
                ev.append(("pop", e["inicio"] + 0.25 + 0.18 * k, 0.45))
    ev.append(("brillo", max(0.0, g["duracion"] - 3.2), 0.5))        # la pregunta del final
    return ev


if __name__ == "__main__":
    print(json.dumps({"planos": PLANOS, "acciones": ACCIONES, "expresiones": EXPRESIONES}, ensure_ascii=False))
