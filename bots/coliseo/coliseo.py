"""El Coliseo (sexta ciudad, la pidió el dueño el 23 nov): solo entran los vídeos que el Juzgado ha aprobado con 90 o más.
El vídeo ya está hecho y no se toca; lo que se juega es su SALIDA: el título, el texto que lo acompaña y los hashtags,
que es lo que más decide si la gente se para a verlo y lo comparte.

1. El Organizador de los juegos mira si hoy queda sitio (tope diario en config/fabrica.json → "coliseo") y saca a los
   8 gladiadores, cada uno con su carta (curiosidad, polémica, dato bomba, historia…): cada uno propone su salida.
2. Combates por parejas (8 → 4 → 2 → 1): cada uno ataca la salida del otro, se defiende y corrige la suya.
3. El Juez ciego, que no sabe quién escribió cada salida ni con qué carta, decide quién pasa.
4. La salida campeona es la que se publica (YouTube) o la que llega a «Para subir» (TikTok e Instagram). Si algo falla,
   el vídeo sale con su salida de siempre: el Coliseo nunca para un vídeo aprobado.
Cada torneo queda en estado/coliseo/torneos/<id>.json y la cuenta de qué cartas ganan, en estado/coliseo/resumen.json
(la ronda de Claude lo copia a la app). Los gladiadores piensan con el cerebro de las ideas (Claude si hay llave y
presupuesto; si no, Gemini gratis) y el juez, con Gemini gratis (Claude de reserva).
"""
import datetime as dt
import json
import os
import random
import re

from bots.comun import gemini, ia, privado

DEFECTO = {"encendido": True, "por_dia": 6, "gladiadores": 8}
CARTAS = [
    ("Máximo", "Curiosidad", "abre una pregunta que solo se cierra viendo el vídeo entero"),
    ("Espartaco", "Polémica", "toma una postura fuerte que invita a opinar y comentar (sin odio contra nadie)"),
    ("Valeria", "Dato bomba", "pone delante un número o un dato concreto que deja con la boca abierta"),
    ("Tito", "Historia", "un protagonista y un conflicto en una sola línea"),
    ("Octavia", "Miedo a perdérselo", "lo que pierde quien no lo sepa, con urgencia"),
    ("Casio", "Humor", "un giro gracioso o una ironía que hace sonreír"),
    ("Livia", "Directo al grano", "el beneficio claro y simple para quien lo ve"),
    ("Lucio", "Tendencia", "engancha con lo que está de moda ahora en su nicho (temas, sonidos, hashtags)"),
]
IDIOMAS = {"es": "español de España", "nl": "neerlandés", "en": "inglés"}
RELLENO = {"fyp", "foryou", "foryoupage", "parati", "paratii", "viral", "viralvideo", "trending", "fy", "xyzbca", "reels",
           "explore", "explorepage", "tiktok", "shorts", "youtube", "youtubeshorts", "instagram"}

GLADIADOR = """Eres {gladiador}, gladiador del Coliseo de una fábrica de vídeos cortos. Tu carta es «{carta}»: {como}.
El vídeo ya está hecho y el Juzgado le ha dado {nota}/100: lo que se ve y lo que se oye NO se puede cambiar. Tu trabajo
es la mejor SALIDA para que la gente se pare a verlo, lo vea entero y lo comparta, jugando tu carta.
Cuenta: «{cuenta}» ({donde}). Idioma: {idioma}. Tema: {tema}.
Lo que se ve y se lee al empezar: {gancho}
Lo que cuenta el vídeo: {narracion}
Salida que tiene ahora: título «{titulo}» · texto: {texto} · hashtags: {hashtags}
Lo que funciona ahora en su nicho: {nicho}
{reglas}
Devuelve SOLO un JSON: {{"titulo": "...", "texto": "el texto que acompaña al vídeo: 1 a 3 frases cortas, la primera con
gancho", "hashtags": ["#...", "#..."], "por_que": "una frase"}}"""

COMBATE = """Coliseo, combate de {ronda}. Dos salidas para el MISMO vídeo (no se sabe quién escribió cada una).
Vídeo: «{cuenta}» ({donde}, en {idioma}). Al empezar se ve: {gancho}. Cuenta: {narracion}
SALIDA A: {a}
SALIDA B: {b}
Primero, A ataca a B: el fallo más grave de B para conseguir visitas y que se comparta (una frase). Después, B ataca
a A igual. Por último, cada una se defiende corrigiendo SU salida con la crítica recibida (sin copiar la de la otra).
{reglas}
Devuelve SOLO un JSON: {{"critica_a_b": "...", "critica_b_a": "...",
"a": {{"titulo": "...", "texto": "...", "hashtags": ["#..."]}}, "b": {{"titulo": "...", "texto": "...", "hashtags": ["#..."]}}}}"""

JUEZ = """Eres el Juez ciego del Coliseo. No sabes quién ha escrito cada salida ni con qué estrategia.
Vídeo: «{cuenta}» ({donde}, en {idioma}). Al empezar se ve: {gancho}. Cuenta: {narracion}
SALIDA 1: {uno}
SALIDA 2: {dos}
¿Cuál hará que más gente se pare, lo vea entero y lo comparta en {donde}, sin engañar (el vídeo tiene que cumplir lo que
promete la salida)? Mira sobre todo el título y la primera frase del texto.
Devuelve SOLO un JSON: {{"ganador": 1 o 2, "razon": "una frase", "nota_1": 0-100, "nota_2": 0-100}}"""


def ajustes():
    a = dict(DEFECTO)
    a.update((privado.ajustes() or {}).get("coliseo") or {})
    return a


def _hoy():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def hay_sitio():
    a = ajustes()
    if not a.get("encendido", True):
        return False
    r = privado.leer(os.path.join("estado", "coliseo", "resumen.json"), {}) or {}
    hoy = r.get("hoy") or {}
    return hoy.get("dia") != _hoy() or int(hoy.get("torneos", 0)) < int(a.get("por_dia", DEFECTO["por_dia"]))


def _narracion(g):
    texto = g.get("narracion") or " ".join(str(e.get("voz", "")) if isinstance(e, dict) else str(e)
                                           for e in g.get("escenas") or [])
    return texto.strip()[:1500]


CREDITOS = ("🎙️ Voz:", "🎙 Voz:", "🎬 Clip:")      # menciones obligatorias: la voz gratis y el creador del clip (CC BY)


def _credito(texto):
    """Las menciones obligatorias (la voz del plan gratis de ElevenLabs y el creador de un clip con licencia CC BY)
    tienen que seguir al final del texto, gane quien gane el torneo."""
    return "\n".join(l.strip() for l in (texto or "").splitlines() if l.strip().startswith(CREDITOS))


def _sin_creditos(texto):
    return "\n".join(l for l in (texto or "").splitlines() if not l.strip().startswith(CREDITOS)).strip()


def _limpia(salida, youtube, original):
    """La salida campeona dentro de las reglas; si no vale, None (y se queda la de siempre)."""
    if not isinstance(salida, dict):
        return None
    titulo = re.sub(r"\s+", " ", str(salida.get("titulo") or "")).strip()
    texto = str(salida.get("texto") or "").strip()
    etiquetas = []
    for h in salida.get("hashtags") or []:
        h = "#" + re.sub(r"[^\w]", "", str(h).lstrip("#"), flags=re.UNICODE)
        if len(h) > 2 and h[1:].lower() not in RELLENO and h.lower() not in [e.lower() for e in etiquetas]:
            etiquetas.append(h)
    if youtube:
        titulo = re.sub(r"\s*#shorts\b", "", titulo, flags=re.I).strip()
        titulo = f"{titulo[:90].rstrip()} #shorts"
    if not 12 <= len(titulo) <= 100 or len(texto) < 10:
        return None
    return {"titulo": titulo, "texto": texto[:600], "hashtags": (etiquetas or original["hashtags"])[:5]}


def _texto_salida(s):
    return json.dumps({k: s.get(k) for k in ("titulo", "texto", "hashtags")}, ensure_ascii=False)


def luchar(clave, canal, g, juicio, paso=print, prueba=False):
    """Torneo para la salida de un vídeo aprobado. Devuelve el guion con la salida campeona (o el de siempre)."""
    a = ajustes()
    alias = privado.alias(clave)
    if juicio.get("veredicto") != "aprobado":
        return g
    if not hay_sitio():
        paso("coliseo", "hoy el Coliseo ya ha hecho todos sus torneos: sale con su salida de siempre")
        return g
    youtube = canal.get("destino", "youtube") == "youtube"
    donde = "YouTube Shorts" if youtube else "TikTok e Instagram"
    idioma = IDIOMAS.get((canal.get("idioma") or "es")[:2], "español de España")
    texto_actual = g.get("descripcion") if youtube else (g.get("texto_tiktok") or g.get("texto_instagram") or "")
    credito = _credito(texto_actual)
    texto_actual = _sin_creditos(texto_actual)
    original = {"titulo": g.get("titulo", ""), "texto": texto_actual, "hashtags": list(g.get("hashtags") or [])}
    receta = ((privado.leer(os.path.join("estado", "influencers", "recetas.json"), {}) or {}).get("canales") or {}).get(clave) or {}
    nicho = {p: {k: (receta.get(p) or {}).get(k) for k in ("lo_que_funciona", "ganchos", "temas", "sonidos")
                 if (receta.get(p) or {}).get(k)} for p in ("radar", "ojeador") if receta.get(p)}
    comun = {"cuenta": canal.get("nombre", clave), "donde": donde, "idioma": idioma,
             "gancho": g.get("texto_pantalla") or next((e.get("texto", "") for e in (g.get("escenas") or [])[:1]
                                                        if isinstance(e, dict)), ""),
             "narracion": _narracion(g)}
    reglas = (f"Reglas: todo en {idioma}; título de 30 a 90 caracteres"
              + (", con 1 o 2 emojis (#shorts lo añade la fábrica)" if youtube else "")
              + "; no prometas nada que el vídeo no cumpla; sin miedo (temas duros sí) pero con tres límites: verdad "
              "sobre gente real, nada de odio contra grupos y nada que rompa las normas de la plataforma; máximo 5 "
              "hashtags, del nicho y no de relleno (nada de #fyp o #viral).")
    ahora = dt.datetime.now(dt.timezone.utc)
    torneo = {"id": f"{ahora.strftime('%Y%m%d-%H%M%S')}-{alias}".replace(".", "-"), "canal": alias, "clave": clave,
              "fecha": privado.ahora(), "prueba": prueba, "video": original["titulo"], "nota_juzgado": juicio.get("total"),
              "antes": original, "gladiadores": [], "combates": []}
    paso("coliseo", f"torneo de {a['gladiadores']} gladiadores para la salida del vídeo")
    # 1. Cada gladiador propone su salida
    luchadores = []
    for nombre, carta, como in CARTAS[:int(a.get("gladiadores", 8))]:
        try:
            s = ia.preguntar(GLADIADOR.format(gladiador=nombre, carta=carta, como=como, nota=juicio.get("total"),
                                              titulo=original["titulo"], texto=original["texto"] or "(sin texto)",
                                              hashtags=" ".join(original["hashtags"]) or "(ninguno)",
                                              nicho=json.dumps(nicho, ensure_ascii=False)[:1200] or "(todavía nada)",
                                              tema=(canal.get("tema") or "")[:200], reglas=reglas, **comun),
                             papel="ideas", temperatura=1.0, ligero_primero=True)
        except gemini.SinIA as e:
            torneo["gladiadores"].append({"nombre": nombre, "carta": carta, "fuera": f"sin IA ({str(e)[:60]})"})
            continue
        limpia = _limpia(s, youtube, original)
        entrada = {"nombre": nombre, "carta": carta, "salida": limpia, "por_que": (s or {}).get("por_que") if isinstance(s, dict) else None,
                   "cerebro": ia.quien().get("motor")}
        torneo["gladiadores"].append(entrada if limpia else dict(entrada, fuera="su salida no cumplía las reglas"))
        if limpia:
            luchadores.append({"nombre": nombre, "carta": carta, "salida": limpia})
    if len(luchadores) < 2:
        paso("coliseo", "no hubo gladiadores suficientes (la IA no contestaba): sale con su salida de siempre")
        return g                                    # un torneo sin luchar no gasta sitio del día
    # 2 y 3. Combates por parejas y el juez ciego
    ronda = 1
    while len(luchadores) > 1:
        siguientes = []
        nombre_ronda = {8: "cuartos", 4: "semifinal", 2: "final"}.get(len(luchadores), ronda)   # como la app
        for i in range(0, len(luchadores) - 1, 2):
            x, y = luchadores[i], luchadores[i + 1]
            combate = {"ronda": nombre_ronda, "a": x["nombre"], "b": y["nombre"]}
            try:
                c = ia.preguntar(COMBATE.format(ronda=nombre_ronda, a=_texto_salida(x["salida"]),
                                                b=_texto_salida(y["salida"]), reglas=reglas, **comun),
                                 papel="ideas", temperatura=0.7, ligero_primero=True)
                if isinstance(c, dict):
                    combate.update(critica_a_b=c.get("critica_a_b"), critica_b_a=c.get("critica_b_a"))
                    x["salida"] = _limpia(c.get("a"), youtube, original) or x["salida"]
                    y["salida"] = _limpia(c.get("b"), youtube, original) or y["salida"]
            except gemini.SinIA:
                combate["sin_combate"] = "la IA no contestaba: el juez decide con lo que había"
            orden = [x, y]
            random.shuffle(orden)                       # que el juez no favorezca siempre a la primera
            try:
                j = ia.preguntar(JUEZ.format(uno=_texto_salida(orden[0]["salida"]), dos=_texto_salida(orden[1]["salida"]),
                                             **comun), papel="juez", temperatura=0.2, ligero_primero=True)
                gana = orden[1] if isinstance(j, dict) and str(j.get("ganador")).strip() == "2" else orden[0]
                combate.update(razon=(j or {}).get("razon") if isinstance(j, dict) else None,
                               notas={orden[0]["nombre"]: (j or {}).get("nota_1"), orden[1]["nombre"]: (j or {}).get("nota_2")}
                               if isinstance(j, dict) else None)
            except gemini.SinIA:
                gana = x
                combate["razon"] = "el juez no contestaba: pasa el primero del cuadro"
            combate.update(ganador=gana["nombre"], salida_a=x["salida"], salida_b=y["salida"])
            torneo["combates"].append(combate)
            siguientes.append(gana)
        if len(luchadores) % 2:                         # si son impares, el último pasa sin luchar
            siguientes.append(luchadores[-1])
        luchadores, ronda = siguientes, ronda + 1
    campeon = luchadores[0]
    torneo["campeon"] = {"nombre": campeon["nombre"], "carta": campeon["carta"], "salida": campeon["salida"]}
    _guardar(torneo, campeon)
    s = campeon["salida"]
    nuevo = dict(g, titulo=s["titulo"], hashtags=s["hashtags"])
    texto = _sin_creditos(s["texto"]) + (f"\n{credito}" if credito else "")
    if youtube:
        nuevo["descripcion"] = texto
    else:
        nuevo["texto_tiktok"] = nuevo["texto_instagram"] = texto
    nuevo["coliseo"] = {"torneo": torneo["id"], "campeon": campeon["nombre"], "carta": campeon["carta"],
                        "titulo_antes": original["titulo"]}
    paso("coliseo", f"campeón: {campeon['nombre']} (carta «{campeon['carta']}») tras {len(torneo['combates'])} combates")
    return nuevo


def _guardar(torneo, campeon):
    """Deja el torneo para la app y lleva la cuenta de qué cartas ganan (en general y en cada cuenta)."""
    privado.guardar_estado(os.path.join("coliseo", "torneos", f"{torneo['id']}.json"), torneo)
    r = privado.leer(os.path.join("estado", "coliseo", "resumen.json"), {}) or {}
    hoy = r.get("hoy") if (r.get("hoy") or {}).get("dia") == _hoy() else {"dia": _hoy(), "torneos": 0}
    hoy["torneos"] = int(hoy.get("torneos", 0)) + 1
    cartas = r.get("cartas") or {}
    por_cuenta = r.get("por_cuenta") or {}
    for gl in torneo["gladiadores"]:
        if gl.get("salida"):
            cartas.setdefault(gl["carta"], {"torneos": 0, "ganadas": 0})["torneos"] += 1
    if campeon:
        cartas.setdefault(campeon["carta"], {"torneos": 1, "ganadas": 0})["ganadas"] += 1
        cuenta = por_cuenta.setdefault(torneo["canal"], {})
        cuenta[campeon["carta"]] = cuenta.get(campeon["carta"], 0) + 1
    ultimos = ([{"id": torneo["id"], "canal": torneo["canal"], "fecha": torneo["fecha"], "video": torneo["video"],
                 "campeon": (torneo.get("campeon") or {}).get("nombre"), "carta": (torneo.get("campeon") or {}).get("carta"),
                 "titulo": ((torneo.get("campeon") or {}).get("salida") or {}).get("titulo"), "prueba": torneo["prueba"]}]
               + (r.get("ultimos") or []))[:30]
    privado.guardar_estado(os.path.join("coliseo", "resumen.json"),
                           {"hoy": hoy, "cartas": cartas, "por_cuenta": por_cuenta, "ultimos": ultimos})
    for robot, que in (("organizador_juegos", {"torneo": torneo["id"], "canal": torneo["canal"]}),
                       ("gladiadores", {"torneo": torneo["id"], "campeon": (campeon or {}).get("nombre"),
                                        "carta": (campeon or {}).get("carta")}),
                       ("juez_ciego", {"torneo": torneo["id"], "combates": len(torneo["combates"])})):
        c = privado.cuaderno(robot)
        c.apuntar("torneo", que)
        c.guardar()
