"""El estudio de animación: vídeos animados con el estilo de las cuentas del dueño, en versión mejorada.

Formato «famoso» (el plató, plato.html): la historia de un famoso contada en 6-8 escenas cortas. Cada escena ENSEÑA lo
que dice la voz: el estadio lleno cuando triunfa, las gradas vacías cuando entrena solo, su barrio, un escenario con focos
y maniquíes grises (la gente que habla o duda), y objetos que significan algo (trofeo, calendario, número grande, lista de
tareas, bocadillo con una pregunta...). Arriba va la frase con las palabras clave resaltadas.

La IA (Claude o Gemini) escribe el guion por escenas eligiendo de una lista cerrada de fondos, acciones y objetos; la voz se graba escena a
escena (edge-tts) para que la imagen vaya clavada con lo que se dice; plato.html dibuja cada fotograma (render.js, con el
navegador) y ffmpeg junta voz, música compuesta por nosotros (herramientas/musica.py) y efectos hechos por nosotros.

Uso:  python bots/estudio/estudio.py --canal barrio-2 [--guion guion.json] [--salida carpeta]
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import wave

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import musica  # noqa: E402
import voz as locutor  # noqa: E402
from bots.comun import ia, privado  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
FORMATOS = ("famoso",)
FONDOS = {"escenario": "escenario", "estadio": "cesped", "gradas": "cesped", "barrio": "calle"}
SUELOS = ("escenario", "cesped", "calle")
POSICIONES = ("centro", "izq", "der", "izq2", "der2")
ACCIONES = {
    "famoso": ("quieto", "magia", "trofeo", "celebra", "senala_der", "senala_izq", "brazos_cruzados", "pensando", "cansado",
               "regate", "corre"),
    "maniqui": ("quieto", "senala_der", "senala_izq", "brazos_cruzados", "pensando", "cansado", "tumbado", "corre"),
}
OBJETOS = ("balon", "chispas", "conos", "camino", "confeti", "numero", "calendario", "checklist", "bocadillo", "trofeo",
           "porteria")
PELOS = ("corto", "rizado", "rapado", "engominado", "largo", "calvo")

VOCABULARIO = """FONDOS (dónde pasa la escena):
- "escenario": plató oscuro con un foco (para frases, dudas, lecciones y la pregunta final)
- "estadio": estadio lleno de noche, con público y focos (triunfos, partidos, fama)
- "gradas": estadio vacío de noche (entrenar solo, sacrificio, cuando nadie miraba)
- "barrio": calle de su barrio con edificios y farola (orígenes, infancia, de dónde viene)
SUELO: "escenario", "cesped" (campo) o "calle". Si no lo pones, va el que pega con el fondo.
ACTORES (2 como mucho por escena, 3 si son maniquíes alrededor del famoso):
- "famoso": el protagonista, dibujado con su ropa. "nino": true si la escena es de cuando era niño.
- "maniqui": persona gris sin cara = la gente, los que dudan, los rivales o TÚ (el que mira el vídeo).
  Lleva "etiqueta" (1-2 palabras en MAYÚSCULAS: SUERTE, EGO, EXCUSAS, CRÍTICOS, TÚ...) con "color_etiqueta" "rojo"
  (lo malo) u "oro" (lo bueno o TÚ).
  "pos": centro, izq, der, izq2 (borde izquierdo) o der2 (borde derecho).
ACCIONES del famoso: quieto, magia (brilla, talento), trofeo (levanta un trofeo), celebra (brazos arriba), senala_der,
senala_izq, brazos_cruzados, pensando, cansado, regate (cruza la pantalla con el balón: pon "desde" y "hasta"), corre.
ACCIONES del maniquí: quieto, senala_der, senala_izq (señalar = criticar, acusar), brazos_cruzados, pensando, cansado,
tumbado (rendido, descansando), corre.
OBJETOS (0 a 3 por escena, solo si significan algo de la frase):
- {"tipo": "balon", "anim": "orbita|botar|regate"} · {"tipo": "chispas"} (talento, magia) · {"tipo": "confeti"} (triunfo)
- {"tipo": "conos"} y {"tipo": "camino"} (entrenamiento, regate) · {"tipo": "porteria", "pos": "der"}
- {"tipo": "numero", "texto": "304", "sub": "TEXTO PEQUEÑO", "pos": "der"} (una cifra clave: edad, goles, dinero, años)
- {"tipo": "calendario", "texto": "2014", "sub": "AÑO", "pos": "der"} (un año o un día concreto)
- {"tipo": "checklist", "items": 4, "marcados": 2, "pos": "der"} (hábitos, tareas, constancia)
- {"tipo": "bocadillo", "texto": "?"} (pregunta, duda; va encima del actor)
- {"tipo": "trofeo", "pos": "der"} (un trofeo en el suelo)"""

EJEMPLO = {"famoso": {"nombre": "LAMINE", "piel": "#7A4A2E", "pelo": "rapado", "color_pelo": "#141012", "camiseta": "#C8102E",
                      "detalle": "#F2C230", "dorsal": "19", "color_dorsal": "#F5C842", "pantalon": "#16224F",
                      "medias": "#C8102E", "botas": "#111318"},
           "escenas": [
               {"voz": "Con quince años ya jugaba en el Barça.", "texto": "Con 15 años ya jugaba en el Barça.",
                "resaltar": ["15 años"], "fondo": "estadio",
                "actores": [{"id": "lamine", "tipo": "famoso", "pos": "centro", "accion": "magia", "etiqueta": "15 AÑOS"}],
                "objetos": [{"tipo": "chispas"}, {"tipo": "balon", "anim": "orbita"}]},
               {"voz": "Muchos dicen que es pura suerte.", "texto": "Muchos dicen que es pura suerte.", "resaltar": ["suerte"],
                "color": "rojo", "fondo": "escenario",
                "actores": [{"id": "m1", "tipo": "maniqui", "pos": "izq2", "etiqueta": "SUERTE", "accion": "senala_der"},
                            {"id": "lamine", "tipo": "famoso", "pos": "centro", "accion": "brazos_cruzados"},
                            {"id": "m2", "tipo": "maniqui", "pos": "der2", "etiqueta": "SUERTE", "accion": "senala_izq"}]},
               {"voz": "Casi nueve años entrenando sin que nadie mirara.", "texto": "Casi 9 años entrenando sin que nadie mirara.",
                "resaltar": ["nadie mirara"], "fondo": "gradas",
                "actores": [{"id": "lamine", "tipo": "famoso", "accion": "regate", "desde": "izq2", "hasta": "der2"}],
                "objetos": [{"tipo": "conos"}, {"tipo": "camino"}, {"tipo": "balon", "anim": "regate"}]},
               {"voz": "¿Y tú? ¿Qué estás entrenando hoy que nadie ve?", "texto": "¿Y tú? ¿Qué estás entrenando hoy que nadie ve?",
                "resaltar": ["nadie ve"], "fondo": "escenario",
                "actores": [{"id": "tu", "tipo": "maniqui", "pos": "izq", "etiqueta": "TÚ", "color_etiqueta": "oro"}],
                "objetos": [{"tipo": "checklist", "pos": "der", "items": 4, "marcados": 2}, {"tipo": "bocadillo", "texto": "?"}]}]}

PLANTILLA = """Eres el guionista de una cuenta de TikTok e Instagram llamada «{nombre}» ({tema}). Haces vídeos animados de
20 a 30 segundos sobre famosos: la parte de su historia que casi nadie conoce, contada para que enganche desde el primer
segundo y deje una lección. Así son los vídeos que mejor le funcionan al dueño (sacado de sus propios vídeos):
{formula}

Ejemplos reales suyos (escena a escena):
{ejemplos}

Lo que ha aprendido la cuenta (lo del dueño manda):
{lecciones}

Ya hechos (no repitas famoso en la misma semana ni el mismo tema):
{hechos}
{extra}
REGLAS
- Famosos de los que más interesan ahora a la gente joven en España (futbolistas sobre todo, también otros deportistas,
  cantantes o empresarios muy conocidos). Cuenta solo cosas ciertas y conocidas de su vida; nada inventado.
- {sin_miedo}
- De 6 a 8 escenas. Cada escena es UNA frase corta (de 4 a 14 palabras). La primera es el gancho: un dato que sorprende
  o una frase que abre una pregunta. La última es una pregunta directa a quien lo ve, con un maniquí «TÚ».
- Lo más importante: CADA ESCENA ENSEÑA LITERALMENTE LO QUE DICE SU FRASE. Si habla de su barrio, fondo «barrio»; si
  triunfa, «estadio»; si entrena solo, «gradas»; si dice una cifra, un objeto «numero» con esa cifra; si alguien duda o
  critica, maniquíes con esa etiqueta señalándole. Nada de objetos que no pinten nada.
- "voz" es lo que se dice (números escritos como se dicen: «quince», «tres, cero, cuatro»); "texto" es lo que se lee
  arriba (igual, pero con cifras); "resaltar" son 1 o 2 palabras de "texto" (color "rojo" si son algo malo).
- La ropa del famoso: los colores de su equipo o selección más conocido, su dorsal, su tono de piel y su pelo.

Lo que puedes poner en cada escena:
{vocabulario}

Ejemplo de la FORMA (no copies el tema):
{ejemplo}

Devuelve SOLO un JSON con esta forma (más "descripcion" (1-2 frases), "hashtags" (3-5), "texto_instagram" y
"texto_tiktok" (el texto para pegar al subirlo, con gancho y hashtags)):
{{"formato": "famoso", "titulo": "título corto con gancho",
 "famoso": {{"nombre": "COMO LE LLAMA LA GENTE, EN MAYÚSCULAS", "piel": "#hex", "pelo": "{pelos}", "color_pelo": "#hex",
            "camiseta": "#hex", "rayas": "#hex o null", "detalle": "#hex", "dorsal": "número o vacío", "color_dorsal": "#hex",
            "pantalon": "#hex", "medias": "#hex", "botas": "#hex"}},
 "escenas": [{{"voz": "...", "texto": "...", "resaltar": ["..."], "color": "oro|rojo", "fondo": "...", "suelo": "...",
              "actores": [{{"id": "...", "tipo": "famoso|maniqui", "pos": "...", "accion": "...", "etiqueta": "...",
                          "color_etiqueta": "rojo|oro", "nino": false}}],
              "objetos": [{{"tipo": "..."}}]}}]}}"""

SIN_MIEDO = ("Sin miedo (lo pide el dueño): temas duros, oscuros, incómodos o polémicos, sí, contados con crudeza y sin "
             "moralina. Solo tres límites: lo que se diga de gente real tiene que ser verdad, nada de odio contra grupos de "
             "personas y nada que rompa las normas de YouTube o TikTok.")


# Lo que añade la fábrica a un guion al grabarlo (tiempos de la voz, motor, juicio…): no es cosa del guionista.
DE_LA_FABRICA = ("palabras", "inicio", "fin", "duracion", "voces", "voz_motor", "musica", "cerebro", "jurado", "jurado_anterior",
                 "narracion", "texto_pantalla", "coliseo", "version", "arreglo_de", "mapa", "mundo", "html", "caja",
                 "pais_nombre")


def guion_escrito(g):
    """El guion tal como lo escribió el guionista: sin los tiempos de la voz ni lo que apunta la fábrica al grabarlo."""
    def limpio(x):
        if isinstance(x, dict):
            return {k: limpio(v) for k, v in x.items() if k not in DE_LA_FABRICA and not str(k).startswith("_")}
        if isinstance(x, list):
            return [limpio(v) for v in x]
        return x
    return limpio(g or {})


def bloque_arreglo(arreglar):
    """Lo que se le añade al guionista cuando el vídeo es la SEGUNDA VERSIÓN de uno que el Juzgado suspendió por poco:
    el guion que se grabó y, uno por uno, los fallos que le vieron, para que rehaga ESE vídeo corrigiéndolos (lo pidió el
    dueño: «que vuelva a crear otro enseguida, mejorado con los fallos que ha tenido»)."""
    if not arreglar or not arreglar.get("guion"):
        return ""
    v = arreglar.get("veredicto") or {}
    lineas = []
    for x in v.get("votos") or []:
        if isinstance(x, dict) and x.get("razon"):
            lineas.append(f"- {x.get('juez', 'Juez')} ({x.get('nota', '-')}/100): {str(x['razon'])[:400]}")
    if v.get("fiscalia"):
        lineas.append(f"- Fiscalía (los fallos, uno por uno): {str(v['fiscalia'])[:900]}")
    for f in v.get("fallos_graves") or []:
        lineas.append(f"- FALLO GRAVE (con esto no se publica): {str(f)[:300]}")
    if v.get("consejo"):
        lineas.append(f"- Consejo del Juzgado: {str(v['consejo'])[:500]}")
    for f in arreglar.get("no_repetir") or []:
        if f:
            lineas.append(f"- OJO: una versión corregida anterior salió PEOR que esta; de aquella dijeron: {str(f)[:300]}")
    for f in arreglar.get("inspector") or []:
        lineas.append(f"- El Inspector de imagen (medido en el vídeo, sin opinar): {str(f)[:300]}")
    medidas = v.get("medidas") or {}
    if medidas:
        lineas.append("- Medidas del vídeo que salió: " + json.dumps(
            {k: medidas[k] for k in ("duracion", "cambios_de_plano_por_minuto", "primer_cambio_de_plano",
                                     "cortes_por_minuto", "primer_corte") if medidas.get(k) is not None},
            ensure_ascii=False))
    bueno = f"\nLo que SÍ funcionaba (no lo pierdas): {str(v['defensa'])[:500]}" if v.get("defensa") else ""
    version = int(arreglar.get("version") or 2)
    return (f"\n\n=== VERSIÓN {version} DEL MISMO VÍDEO (esto manda sobre todo lo anterior) ===\n"
            f"Este guion ya se grabó y el Juzgado le puso {v.get('total', '-')}/100; para publicarse hacen falta "
            f"{arreglar.get('minimo', 90)}. NO escribas un vídeo nuevo: rehaz ESTE (el mismo tema y la misma idea, aunque "
            "esté en la lista de «ya hechos o intentados») arreglando uno por uno los fallos de abajo.\n"
            "Guion que se grabó:\n" + json.dumps(guion_escrito(arreglar["guion"]), ensure_ascii=False)[:9000] +
            "\n\nLo que le han visto los jueces:\n" + "\n".join(lineas) + bueno +
            "\n\nCómo arreglarlo:\n"
            "1. Recorre los fallos uno a uno y cambia en el guion justo lo que causa cada uno (un texto que no cabe se "
            "acorta; dos rótulos que se pisan pasan a uno o se acortan; una cifra en pantalla que no es la de la voz se "
            "iguala; una frase que se repite arriba y abajo se quita de un sitio; un arranque lento se cambia por lo más "
            "fuerte del vídeo en grande desde el primer fotograma y con su frase más corta).\n"
            "2. Si dicen que va lento o quieto, parte las escenas largas en dos y que cada una cambie lo que se ve.\n"
            "3. Si el título es flojo o no cuadra con el vídeo, cámbialo por uno que prometa justo lo que enseña.\n"
            "4. Lo que no han criticado se queda igual. No lo alargues y no metas fallos nuevos: repasa cada texto de "
            "pantalla (corto, entero, sin repetir) antes de entregar.\n"
            "Devuelve SOLO el JSON del guion corregido, con la misma forma de siempre.")


def referencias(clave):
    """La fórmula y 4 ejemplos de los vídeos de referencia del dueño, si están analizados."""
    d = privado.leer(os.path.join("estado", "referencias", f"{privado.alias(clave)}.json"), {}) or {}
    formula = json.dumps(d.get("formula") or {}, ensure_ascii=False)[:5000]
    ejemplos = []
    for v in list((d.get("videos") or {}).values()):
        if isinstance(v, dict) and v.get("escenas") and "famoso" in str(v.get("formato", "")):
            ejemplos.append(f"- {v.get('tema')}: " + " / ".join(str(e.get("texto_pantalla", "")) for e in v["escenas"][:8]))
    return formula or "(sin fórmula todavía)", "\n".join(ejemplos[:4]) or "(sin ejemplos)"


def _hex(c, defecto):
    return c if isinstance(c, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", c) else defecto


def _actor(a, n, usadas):
    tipo = a.get("tipo") if a.get("tipo") in ACCIONES else "maniqui"
    accion = a.get("accion") if a.get("accion") in ACCIONES[tipo] else "quieto"
    x = {"id": str(a.get("id") or f"{tipo}{n}")[:20], "tipo": tipo, "accion": accion}
    if accion in ("regate", "corre"):
        x["desde"] = a.get("desde") if a.get("desde") in POSICIONES else "izq2"
        x["hasta"] = a.get("hasta") if a.get("hasta") in POSICIONES and a.get("hasta") != x["desde"] else (
            "der2" if x["desde"] != "der2" else "izq2")
    else:
        pedida = a.get("pos") if a.get("pos") in POSICIONES else "centro"
        x["pos"] = next(p for p in (pedida, "centro", "izq2", "der2", "izq", "der", pedida) if p not in usadas or p == pedida)
        usadas.add(x["pos"])
    if a.get("etiqueta"):
        x["etiqueta"] = str(a["etiqueta"]).upper()[:14]
        x["color_etiqueta"] = a.get("color_etiqueta") if a.get("color_etiqueta") in ("rojo", "oro") else (
            "rojo" if tipo == "maniqui" else "oro")
    if tipo == "famoso" and a.get("nino"):
        x.update(nino=True, escala=0.72)
    if tipo == "maniqui" and x.get("pos") in ("izq2", "der2"):   # los del borde se abren para no tapar al famoso
        x.update(pos=125 if x["pos"] == "izq2" else 955, escala=0.94)
    return x


def _objeto(o, actores):
    if not isinstance(o, dict) or o.get("tipo") not in OBJETOS:
        return None
    o = {k: v for k, v in o.items() if k in ("tipo", "anim", "texto", "sub", "pos", "items", "marcados", "n")}
    if o["tipo"] in ("numero", "calendario"):
        if not str(o.get("texto") or "").strip():
            return None
        o["texto"] = str(o["texto"]).strip()[:6 if o["tipo"] == "numero" else 5]
        if o.get("sub"):
            o["sub"] = str(o["sub"]).upper()[:22]
    if o["tipo"] == "bocadillo":
        o["texto"] = str(o.get("texto") or "?")[:2]
    if o["tipo"] == "checklist":
        o["items"] = max(3, min(5, int(o.get("items") or 4)))
        o["marcados"] = max(0, min(o["items"], int(o.get("marcados") or 2)))
    if o["tipo"] == "balon" and o.get("anim") not in ("orbita", "botar", "regate"):
        o["anim"] = "regate" if any(x["accion"] == "regate" for x in actores) else "orbita"
    if "pos" in o and o["pos"] not in POSICIONES:
        o.pop("pos")
    return o


def limpiar(g):
    """Deja el guion de la IA dentro de lo que sabe dibujar el plató (corrige o quita lo raro en vez de fallar)."""
    f = g.get("famoso") or {}
    g["famoso"] = {"nombre": str(f.get("nombre") or "ÍDOLO").upper()[:14], "piel": _hex(f.get("piel"), "#C68B5E"),
                   "pelo": f.get("pelo") if f.get("pelo") in PELOS else "corto",
                   "color_pelo": _hex(f.get("color_pelo"), "#1A1310"), "camiseta": _hex(f.get("camiseta"), "#2F6FD6"),
                   "detalle": _hex(f.get("detalle"), "#FFFFFF"), "dorsal": str(f.get("dorsal") or "")[:3],
                   "color_dorsal": _hex(f.get("color_dorsal"), "#FFFFFF"), "pantalon": _hex(f.get("pantalon"), "#FFFFFF"),
                   "medias": _hex(f.get("medias"), "#FFFFFF"), "botas": _hex(f.get("botas"), "#15171C")}
    if _hex(f.get("rayas"), None):
        g["famoso"]["rayas"] = f["rayas"]
    escenas = []
    for e in (g.get("escenas") or [])[:9]:
        if not isinstance(e, dict) or not (e.get("voz") or e.get("texto")):
            continue
        texto = str(e.get("texto") or e.get("voz")).strip()
        voz = str(e.get("voz") or texto).strip()
        res = [r for r in (e.get("resaltar") or []) if isinstance(r, str) and r.strip() and r.lower() in texto.lower()][:2]
        fondo = e.get("fondo") if e.get("fondo") in FONDOS else "escenario"
        usadas = set()
        actores = [_actor(a, n, usadas) for n, a in enumerate((e.get("actores") or [])[:3]) if isinstance(a, dict)]
        objetos = [o for o in (_objeto(o, actores) for o in (e.get("objetos") or [])[:3]) if o]
        # si hay un objeto grande a un lado, el actor que estaba en el centro se va al otro lado
        lados = {o.get("pos", "der") for o in objetos if o["tipo"] in ("numero", "calendario", "checklist", "trofeo")}
        if lados and len(actores) == 1 and actores[0].get("pos") == "centro":
            actores[0]["pos"] = 275 if lados & {"der", "der2", "centro"} else 805
        escenas.append({"voz": voz, "texto": texto, "resaltar": res, "color": "rojo" if e.get("color") == "rojo" else "oro",
                        "fondo": fondo, "suelo": e.get("suelo") if e.get("suelo") in SUELOS else FONDOS[fondo],
                        "actores": actores, "objetos": objetos})
    if len(escenas) < 3:
        raise ValueError("el guion tiene muy pocas escenas")
    g["escenas"] = escenas
    g["formato"], g["html"] = "famoso", "plato.html"
    g["titulo"] = str(g.get("titulo") or escenas[0]["texto"])[:90]
    return g


def guionizar(canal, lecciones, arreglar=None):
    clave = canal["clave"]
    formula, ejemplos = referencias(clave)
    hechos = (privado.leer(os.path.join("estado", "estudio", f"{privado.alias(clave)}.json"), {}) or {}).get("videos", [])
    texto = PLANTILLA.format(nombre=canal["nombre"], tema=canal.get("tema", ""), formula=formula, ejemplos=ejemplos,
                             lecciones=lecciones or "(nada todavía)",
                             hechos="\n".join(f"- {h.get('famoso')}: {h.get('titulo')}" for h in hechos[-30:]) or "- (nada)",
                             extra="", sin_miedo=SIN_MIEDO, vocabulario=VOCABULARIO,
                             ejemplo=json.dumps(EJEMPLO, ensure_ascii=False), pelos="|".join(PELOS))
    texto += bloque_arreglo(arreglar)
    ultimo = None
    for _ in range(3):
        g = ia.preguntar(texto, papel="arreglo" if arreglar else "guionista", temperatura=0.95)
        if isinstance(g, list) and g:
            g = g[0]
        try:
            if isinstance(g, dict):
                return limpiar(g)
        except (ValueError, TypeError, KeyError) as e:
            ultimo = e
        texto += "\n\nEl intento anterior no tenía la forma pedida. Devuelve SOLO el JSON, con 6 a 8 escenas."
    raise ValueError(f"La IA no dio un guion válido para el estudio ({ultimo})")


def _duracion(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def voz_por_escenas(g, carpeta, canal, hueco=0.28, entrada=0.12, cola=1.4):
    """Graba cada escena por separado y coloca las escenas según lo que tarda cada frase (sin silencios muertos)."""
    voz, velocidad, tono = (canal.get("voz_estudio", "es-ES-AlvaroNeural"), canal.get("velocidad_estudio", "-6%"),
                            canal.get("tono_estudio", "-2Hz"))
    hueco, cola = float(canal.get("hueco_estudio", hueco)), float(canal.get("cola_estudio", cola))   # ritmo por perfil
    t, partes = entrada, []
    for i, e in enumerate(g["escenas"]):
        d = os.path.join(carpeta, f"voz{i}")
        os.makedirs(d, exist_ok=True)
        asyncio.run(locutor.generar(e["voz"], voz, velocidad, tono, d))
        locutor.apretar(d, hueco_max=0.3)
        palabras = json.load(open(os.path.join(d, "palabras.json"), encoding="utf-8"))
        largo = palabras[-1]["fin"] + 0.12 if palabras else _duracion(os.path.join(d, "voz.mp3"))
        e["palabras"] = [{"p": w["palabra"], "a": round(t + w["inicio"], 3), "b": round(t + w["fin"], 3)} for w in palabras]
        e["inicio"] = 0.0 if i == 0 else round(t - hueco / 2, 3)
        partes.append((os.path.join(d, "voz.mp3"), t))
        # Personajes que hablan en la escena con SU propia voz (las bolas-país): cada frase suena detrás del narrador
        for k, x in enumerate(e.get("voces") or []):
            dk = os.path.join(carpeta, f"voz{i}_{k}")
            try:
                os.makedirs(dk, exist_ok=True)
                asyncio.run(locutor.generar(x["texto"], x["voz"], x.get("velocidad", "+0%"), x.get("tono", "+0Hz"), dk))
                locutor.apretar(dk, hueco_max=0.3)
                pk = json.load(open(os.path.join(dk, "palabras.json"), encoding="utf-8"))
                dura = pk[-1]["fin"] + 0.1 if pk else _duracion(os.path.join(dk, "voz.mp3"))
            except Exception as err:               # si una voz no sale, la escena sigue solo con el narrador
                print(f"voz: el personaje de la escena {i + 1} no ha podido hablar ({type(err).__name__})", flush=True)
                continue
            x["a"], x["b"] = round(t + largo + 0.08, 3), round(t + largo + 0.08 + dura, 3)
            partes.append((os.path.join(dk, "voz.mp3"), t + largo + 0.08))
            largo += 0.08 + dura
        t += largo + hueco
    for i, e in enumerate(g["escenas"]):
        e["fin"] = g["escenas"][i + 1]["inicio"] if i + 1 < len(g["escenas"]) else round(t - hueco + cola, 3)
    g["duracion"] = g["escenas"][-1]["fin"]
    entradas, filtros = [], []
    for n, (ruta, cuando) in enumerate(partes):
        entradas += ["-i", ruta]
        ms = int(cuando * 1000)
        filtros.append(f"[{n}:a]adelay={ms}|{ms}[v{n}]")
    salida = os.path.join(carpeta, "voz.mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex",
                    ";".join(filtros) + ";" + "".join(f"[v{n}]" for n in range(len(partes))) +
                    f"amix=inputs={len(partes)}:normalize=0[s]", "-map", "[s]", "-ac", "1", "-t", str(g["duracion"]),
                    "-c:a", "libmp3lame", "-b:a", "160k", salida], check=True)
    return salida


def _sonidos(carpeta):
    """Efectos hechos nota a nota (sin derechos de nadie): whoosh, pop, brillo, golpe y tic."""
    import numpy as np
    sr, r = 44100, np.random.RandomState(4)

    def t(d):
        return np.arange(int(d * sr)) / sr
    s = {}
    x = t(0.5)
    X, F = np.fft.rfft(r.randn(len(x))), np.fft.rfftfreq(len(x), 1 / sr)
    s["whoosh"] = np.fft.irfft(X * np.exp(-((np.log(F + 1) - np.log(1800)) ** 2) / 0.9), len(x)) * np.sin(np.pi * x / 0.5) ** 2
    x = t(0.12)
    s["pop"] = np.sin(2 * np.pi * np.cumsum(1300 * np.exp(-x * 25) + 380) / sr) * np.exp(-x * 30)
    x = t(0.9)
    s["brillo"] = sum(np.sin(2 * np.pi * f * x) * np.exp(-(x - d).clip(0) * 6) * (x >= d)
                      for f, d in ((1318.5, 0), (1975.5, 0.09), (2637, 0.18)))
    x = t(0.8)
    s["golpe"] = (np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-x * 9)) / sr) * np.exp(-x * 4.5)
                  + 0.25 * r.randn(len(x)) * np.exp(-x * 40))
    x = t(0.05)
    s["tic"] = np.sin(2 * np.pi * 1900 * x) * np.exp(-x * 120) + 0.2 * r.randn(len(x)) * np.exp(-x * 200)
    rutas = {}
    for k, v in s.items():
        rutas[k] = os.path.join(carpeta, f"fx_{k}.wav")
        v = np.clip(v / (np.abs(v).max() + 1e-9) * 0.9, -1, 1)
        with wave.open(rutas[k], "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((v * 32767).astype("<i2").tobytes())
    return rutas


def eventos_famoso(g):
    """Los sonidos del plató «famoso»: whoosh en cada cambio de escena, pop cuando aparece alguien o algo, brillo, golpe
    y tics. Devuelve [(sonido, segundo, volumen)]."""
    eventos, antes = [], set()
    for i, e in enumerate(g["escenas"]):
        a = e["inicio"]
        if i:
            eventos.append(("whoosh", max(0.0, a - 0.12), 0.55))
        for k, x in enumerate([x for x in e["actores"] if x["id"] not in antes]):
            eventos.append(("pop", a + 0.22 + 0.12 * k, 0.35))
        for o in e["objetos"]:
            if o["tipo"] in ("chispas", "confeti"):
                eventos.append(("brillo", a + 0.2, 0.42))
            elif o["tipo"] == "numero":
                eventos.append(("golpe", a + 0.38, 0.8))
            elif o["tipo"] in ("calendario", "checklist", "trofeo"):
                eventos.append(("pop", a + 0.32, 0.35))
            elif o["tipo"] == "bocadillo":
                eventos.append(("pop", a + 0.92, 0.4))
            if o["tipo"] == "checklist":
                eventos += [("tic", a + 0.75 + 0.5 * k, 0.5) for k in range(o.get("marcados", 2))]
        antes = {x["id"] for x in e["actores"]}
    return eventos


def efectos(g, carpeta, eventos=None):
    """Pista de efectos a partir de [(sonido, segundo, volumen)]: whoosh, pop, brillo, golpe o tic."""
    eventos = eventos if eventos is not None else eventos_famoso(g)
    if not eventos:
        eventos = [("tic", 0.0, 0.0)]
    rutas = _sonidos(carpeta)
    entradas, filtros = [], []
    for n, (nombre, cuando, vol) in enumerate(eventos):
        entradas += ["-i", rutas[nombre]]
        ms = int(cuando * 1000)
        filtros.append(f"[{n}:a]adelay={ms}|{ms},volume={vol}[e{n}]")
    salida = os.path.join(carpeta, "efectos.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex",
                    ";".join(filtros) + ";" + "".join(f"[e{n}]" for n in range(len(eventos))) +
                    f"amix=inputs={len(eventos)}:normalize=0[s]", "-map", "[s]", "-t", str(g["duracion"]), salida],
                   check=True)
    return salida


def formato_de(canal, pedido=None):
    """(nombre, módulo) del formato: «famoso» (este fichero), «pictos» (pictogramas), «ciencia» (Wist je dat),
    «hipnotico» (bolas de neón con la historia narrada) o «bolas» (bolas-país en el mapa, el canal de mapas)."""
    nombre = pedido or canal.get("formato_estudio") or "famoso"
    if nombre == "pictos":
        from bots.estudio import pictos as modulo
    elif nombre == "ciencia":
        from bots.estudio import ciencia as modulo
    elif nombre == "hipnotico":
        from bots.estudio import hipnotico as modulo
    elif nombre == "bolas":
        from bots.estudio import bolas as modulo
    else:
        nombre, modulo = "famoso", sys.modules[__name__]
    return nombre, modulo


def hacer(canal, lecciones="", formato=None, carpeta=None, avisar=print, guion=None):
    """Hace un vídeo completo. Devuelve (ruta del mp4, guion)."""
    carpeta = carpeta or tempfile.mkdtemp(prefix="estudio-")
    os.makedirs(carpeta, exist_ok=True)
    nombre, m = formato_de(canal, formato or (guion or {}).get("formato"))
    avisar(f"estudio: guion «{nombre}»")
    g = m.limpiar(json.loads(json.dumps(guion))) if guion else m.guionizar(canal, lecciones)
    if guion:                                  # un guion que ya viene hecho (del turno, tras el Jurado) guarda lo suyo
        for campo in ("cerebro", "jurado"):
            if guion.get(campo) is not None:
                g[campo] = guion[campo]
    g.setdefault("cerebro", "a mano" if guion else ia.quien().get("motor", "gemini"))   # quién escribió el guion
    avisar("estudio: voz escena a escena")
    voz = voz_por_escenas(g, carpeta, canal)
    g["voz_motor"] = locutor.MOTOR.get("motor", "edge")
    if str(canal.get("voz_estudio") or "").startswith("eleven:"):      # por qué no ha sonado la voz del dueño (si pasa)
        aviso = locutor.MOTOR.get("aviso")
        if aviso:
            avisar(f"locutor: {aviso}")
        try:
            privado.guardar_estado("voz.json", {"aviso": aviso, "motor": g["voz_motor"]})
        except Exception:
            pass
    if g["voz_motor"] == "elevenlabs" and canal.get("eleven_gratis", True):
        # el plan gratis de ElevenLabs pide nombrarles al publicar
        for campo in ("texto_tiktok", "texto_instagram", "descripcion"):
            if g.get(campo):
                g[campo] = f"{g[campo].rstrip()}\n🎙️ Voz: elevenlabs.io"
    with open(os.path.join(carpeta, "guion_estudio.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)
    avisar(f"estudio: dibujando {g['duracion']} s fotograma a fotograma")
    mudo = os.path.join(carpeta, "imagen.mp4")
    subprocess.run(["node", os.path.join(AQUI, "render.js"), os.path.join(carpeta, "guion_estudio.json"), mudo, "30"],
                   check=True)
    avisar("estudio: música y efectos")
    pista = musica.crear(canal.get("musica_estudio") or getattr(m, "MUSICA", "inspira"), g["duracion"],
                         os.path.join(carpeta, "musica.m4a"))
    fx = efectos(g, carpeta, m.eventos(g) if hasattr(m, "eventos") else eventos_famoso(g))
    salida = os.path.join(carpeta, "video.mp4")
    if pista:
        entradas = ["-i", mudo, "-i", voz, "-i", pista, "-i", fx]
        mezcla = ("[1:a]volume=1.0[v];[2:a]volume=0.42[m];[3:a]volume=0.8[f];"
                  "[v][m][f]amix=inputs=3:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5[a]")
    else:       # sin música (el dueño la pone en TikTok): voz y efectos
        entradas = ["-i", mudo, "-i", voz, "-i", fx]
        mezcla = "[1:a]volume=1.0[v];[2:a]volume=0.7[f];[v][f]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5[a]"
    g["musica"] = bool(pista)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", mezcla, "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", str(g["duracion"]), "-movflags", "+faststart",
                    salida], check=True)
    return salida, g


def apuntar(clave, g):
    ruta = os.path.join("estado", "estudio", f"{privado.alias(clave)}.json")
    d = privado.leer(ruta, {}) or {}
    d["videos"] = (d.get("videos", []) + [{"titulo": g.get("titulo"), "formato": g.get("formato"),
                                           "famoso": (g.get("famoso") or {}).get("nombre"), "fecha": privado.ahora()}])[-200:]
    privado.escribir(ruta, d)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--canal", required=True)
    p.add_argument("--guion", help="un guion ya hecho (JSON) en vez de pedírselo a la IA")
    p.add_argument("--salida", default=None)
    a = p.parse_args()
    canal = privado.canal(privado.resolver(a.canal))
    guion = json.load(open(a.guion, encoding="utf-8")) if a.guion else None
    video, g = hacer(canal, carpeta=a.salida, guion=guion, avisar=lambda t: print(privado.limpiar(t), flush=True))
    print(privado.limpiar(f"estudio: vídeo listo ({g['duracion']} s, {len(g['escenas'])} escenas) en {video}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
