"""Formato «pictos» del estudio (cuenta de motivación): historias de motivación y dinero con pictogramas, en versión mejorada del
estilo del dueño. Fondo oscuro con brillo, monigotes lisos, iconos de línea, barras, contadores, gráficas, listas y texto
que sale palabra a palabra con la voz (pictos.html lo dibuja).

La IA (Claude o Gemini, ver bots/comun/ia.py) escribe el guion con una lista cerrada de iconos y piezas; limpiar() lo deja dentro de lo que sabe dibujar el
estudio; eventos() pone los sonidos justo cuando aparece cada cosa.
"""
import json
import os
import re
import unicodedata

from bots.comun import ia, privado

MUSICA = "energia"
PALETAS = ("menta", "azul", "naranja")
COLORES = ("main", "blanco", "gris", "rojo", "oro", "azul")
POSICIONES = ("centro", "izq", "der", "izq2", "der2")
ALTURAS = ("suelo", "mano", "aire", "arriba")
ACCIONES = ("quieto", "senala_der", "senala_izq", "celebra", "piensa", "saluda", "sujeta", "brazos_abiertos", "triste",
            "nervioso")
ICONOS = ("moneda monedas monedas_crecen billete hucha cartera cartera_vacia tarjeta banco casa coche movil portatil tele "
          "mando libro reloj reloj_arena calendario grafica_sube grafica_baja flecha_arriba flecha_abajo trofeo corona "
          "medalla estrella cohete bombilla cerebro diana montana escalera puerta llave candado lupa botella carrito cafe "
          "pesa fuego rayo corazon check cruz pregunta exclamacion pizarra colegio oficina maletin porcentaje balanza "
          "regalo ajedrez cama camino").split()
FORMAS = ("exponencial", "recta", "plana", "baja", "sube")

VOCABULARIO = f"""Cada escena es un plano con pocas cosas, que ENSEÑAN lo que dice su frase:
- "personas": monigotes lisos (cabeza y cuerpo). {{"id": "nombre corto", "color": "main" (el protagonista) | "blanco"
  (otra persona) | "gris" (apagado, el que no lo hace) | "rojo" (lo malo), "pos": centro|izq|der|izq2|der2,
  "accion": {"|".join(ACCIONES)}, "etiqueta": "1-2 PALABRAS encima (VAGO, 1.500 €, MARTA)", "color_etiqueta": color,
  "etiqueta_cuando": "palabra de la frase en la que aparece", "tachar_cuando": "palabra en la que se tacha la etiqueta",
  "corona_cuando": "palabra en la que le sale una corona", "brilla": true/false, "pupitre": true/false, "escala": 0.7-1}}
- "fila": {{"n": 5, "destaca": 2, "pupitre": true}} = una fila de gente (la clase, los demás) con uno destacado.
- "objetos": iconos de línea con color. {{"tipo": uno de [{", ".join(ICONOS)}], "pos": ..., "altura": suelo|mano|aire|arriba,
  "escala": 0.6-1.6, "color": color, "texto": "para calendario o pizarra", "etiqueta": "texto encima", "cuando": "palabra
  en la que aparece", "tachar": "palabra en la que se tacha"}}
- "etiquetas": [{{"texto": "INTERÉS COMPUESTO", "color": "oro", "y": 760, "cuando": "palabra"}}] (píldoras sueltas).
- "barras": [{{"texto": "LO QUE PUSO", "valor": 0.3, "etiqueta": "36.000 €", "color": "blanco"}}] (hasta 3; valor de 0 a 1).
- "contador": {{"desde": 0, "hasta": 121997, "prefijo": "", "sufijo": " €", "texto": "EN 30 AÑOS", "color": "oro"}}.
- "grafica": {{"eje": "años", "lineas": [{{"nombre": "MARTA", "color": "main", "forma": "exponencial"}}, {{"nombre": "ÁLEX",
  "color": "rojo", "forma": "plana"}}]}} (formas: {", ".join(FORMAS)}).
- "lista": [{{"texto": "EL PROFE MIRA EL MÓVIL", "icono": "movil", "cuando": "palabra"}}] (2-4 puntos numerados).
- "flechas": [{{"de": "izq", "a": "der"}}] (una cosa lleva a otra).
- "cta": {{"texto": "SÍGUEME", "opciones": ["SOY ÁLEX", "SOY MARTA"]}} (solo en la última escena).
No llenes la pantalla: 1 a 3 cosas por escena. Lo que aparece «cuando» se dice la palabra queda clavado con la voz."""

EJEMPLO = {"paleta": "menta", "escenas": [
    {"voz": "Dos amigos cobran lo mismo: mil quinientos euros al mes.", "texto": "Dos amigos cobran lo mismo: 1.500 € al mes.",
     "resaltar": ["1.500 €"], "personas": [{"id": "alex", "color": "blanco", "pos": "izq", "etiqueta": "ÁLEX"},
                                           {"id": "marta", "color": "main", "pos": "der", "etiqueta": "MARTA"}],
     "etiquetas": [{"texto": "1.500 € / MES", "color": "oro", "y": 820, "cuando": "1.500"}]},
    {"voz": "Pero lo invertido crece solo, y cada año un poco más.", "texto": "Pero lo invertido crece solo, y cada año un poco más.",
     "resaltar": ["crece solo"], "color": "verde",
     "grafica": {"eje": "años", "lineas": [{"nombre": "MARTA", "color": "main", "forma": "exponencial"},
                                           {"nombre": "ÁLEX", "color": "rojo", "forma": "plana"}]}},
    {"voz": "Con un siete por ciento al año, en treinta años tendría más de cien mil euros.",
     "texto": "Con un 7 % al año, en 30 años tendría más de 100.000 €.", "resaltar": ["100.000 €"],
     "contador": {"desde": 0, "hasta": 121997, "sufijo": " €", "texto": "30 años · 7 % al año", "color": "oro"},
     "personas": [{"id": "marta", "color": "main", "pos": "centro", "accion": "celebra", "cuando": "cien"}]},
    {"voz": "¿Tú eres Álex o Marta? Te leo en comentarios.", "texto": "¿Tú eres Álex o Marta? Te leo en comentarios.",
     "resaltar": ["Álex", "Marta"], "cta": {"texto": "SÍGUEME", "opciones": ["SOY ÁLEX", "SOY MARTA"]}}]}

PLANTILLA = """Eres el guionista de «{nombre}», una cuenta de TikTok e Instagram de motivación y dinero (finanzas personales,
hábitos, mentalidad, disciplina) para gente joven de España. Haces vídeos de 20 a 35 segundos con pictogramas: una
historia corta o una comparación que engancha desde el primer segundo y deja una idea que la gente quiere guardar.

Lo que más está funcionando ahora en este nicho (Radar de nichos e Influencers):
{receta}

Así es el estilo del dueño (sacado de su vídeo de ejemplo):
{formula}

Lo que ha aprendido la cuenta (lo del dueño manda):
{lecciones}

Ya hechos (no repitas tema):
{hechos}

REGLAS
- {sin_miedo}
- Datos de dinero ciertos y sin prometer nada: si hay rentabilidades, dilo como supuesto («con un 7 % al año») y que las
  cuentas cuadren de verdad. Si das una cifra calculada, redondéala hacia abajo y di «más de» o «casi».
- De 8 a 12 escenas cortas, una frase por escena (de 4 a 12 palabras; si es más larga, pártela en dos escenas). Algo
  nuevo en pantalla cada 2-3 segundos: la gente se va si el vídeo se queda quieto.
- Primera escena = el gancho, lo más importante del vídeo: una afirmación que choca, un «A contra B» o un número que
  sorprende, Y algo grande en pantalla desde el segundo 0 (dos personas enfrentadas, un contador, una etiqueta enorme).
  Su frase, como mucho 7 palabras: así el primer cambio de plano llega antes de los 2 segundos (los jueces lo miden).
- NINGUNA escena vacía: cada una tiene al menos una persona, un objeto o una pieza (barras, contador, gráfica, lista).
- Última escena = pregunta a quien lo ve + "cta".
- "voz" es lo que se dice (números escritos como se dicen); "texto" es lo que sale escrito palabra a palabra (igual,
  pero con cifras); "resaltar" son 1-2 palabras de "texto"; "color" de lo resaltado: "oro" (dinero, bueno), "rojo"
  (malo) o "verde" (lo que hay que hacer).
- CADA ESCENA ENSEÑA LO QUE DICE: si dice una cantidad, contador o barras; si compara, dos personas o una gráfica; si
  enumera, una lista. Usa "cuando" para que las cosas salgan justo al decir su palabra.

Lo que puedes poner:
{vocabulario}

Ejemplo de la FORMA (no copies el tema):
{ejemplo}

Devuelve SOLO un JSON: {{"formato": "pictos", "titulo": "...", "paleta": "menta|azul|naranja", "escenas": [...],
"descripcion": "1-2 frases", "hashtags": ["3-5"], "texto_tiktok": "texto para pegar al subirlo, con gancho y hashtags",
"texto_instagram": "lo mismo para Instagram"}}"""


def _normal(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    return re.sub(r"[^a-z0-9ñ%€$]", "", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def _num(x, defecto=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return defecto


def _color(c, defecto="main"):
    return c if c in COLORES else defecto


def _corta(x, n):
    return str(x or "").strip()[:n]


def limpiar(g):
    """Deja el guion dentro de lo que sabe dibujar pictos.html (corrige o quita lo raro en vez de fallar)."""
    escenas = []
    for e in (g.get("escenas") or [])[:13]:
        if not isinstance(e, dict) or not (e.get("voz") or e.get("texto")):
            continue
        texto = _corta(e.get("texto") or e.get("voz"), 160)
        x = {"voz": _corta(e.get("voz") or texto, 200), "texto": texto,
             "resaltar": [r for r in (e.get("resaltar") or []) if isinstance(r, str) and _normal(r) and _normal(r) in _normal(texto)][:2],
             "color": e.get("color") if e.get("color") in ("oro", "rojo", "verde") else "oro"}
        if e.get("antes"):
            x["antes"] = _corta(e["antes"], 40)
        personas, usadas = [], set()
        for n, p in enumerate((e.get("personas") or [])[:3]):
            if not isinstance(p, dict):
                continue
            q = {"id": _corta(p.get("id") or f"p{n}", 16), "color": _color(p.get("color"), "blanco"),
                 "accion": p.get("accion") if p.get("accion") in ACCIONES else "quieto"}
            pos = p.get("pos") if p.get("pos") in POSICIONES else None
            if pos is None or pos in usadas:
                pos = next((x2 for x2 in ("centro", "izq", "der", "izq2", "der2") if x2 not in usadas), "centro")
            usadas.add(pos)
            q["pos"] = pos
            for campo in ("etiqueta_cuando", "tachar_cuando", "corona_cuando", "cuando"):
                if p.get(campo):
                    q[campo] = _corta(p[campo], 30)
            if p.get("etiqueta"):
                q["etiqueta"] = _corta(p["etiqueta"], 16).upper()
                q["color_etiqueta"] = _color(p.get("color_etiqueta"), "rojo" if q["color"] in ("rojo", "gris") else "oro")
            if p.get("brilla"):
                q["brilla"] = True
            if p.get("pupitre"):
                q["pupitre"] = True
            q["escala"] = max(0.6, min(1.1, _num(p.get("escala"), 1.0)))
            personas.append(q)
        if personas:
            x["personas"] = personas
        if isinstance(e.get("fila"), dict):
            f = e["fila"]
            x["fila"] = {"n": int(max(3, min(9, _num(f.get("n"), 5)))), "destaca": int(_num(f.get("destaca"), -1)),
                         "pupitre": bool(f.get("pupitre")), "color": _color(f.get("color"), "blanco")}
        objetos = []
        for o in (e.get("objetos") or [])[:3]:
            if not isinstance(o, dict) or o.get("tipo") not in ICONOS:
                continue
            q = {"tipo": o["tipo"], "pos": o.get("pos") if o.get("pos") in POSICIONES else "centro",
                 "altura": o.get("altura") if o.get("altura") in ALTURAS else "aire",
                 "escala": max(0.5, min(1.6, _num(o.get("escala"), 0.9))), "color": _color(o.get("color"))}
            for campo, n in (("texto", 10), ("etiqueta", 16), ("cuando", 30), ("tachar", 30)):
                if o.get(campo):
                    q[campo] = _corta(o[campo], n)
            objetos.append(q)
        if objetos:
            x["objetos"] = objetos
        etiquetas = [{"texto": _corta(t.get("texto"), 22).upper(), "color": _color(t.get("color"), "oro"),
                      "y": int(max(620, min(1100, _num(t.get("y"), 780)))), **({"cuando": _corta(t["cuando"], 30)} if t.get("cuando") else {}),
                      **({"tam": int(max(26, min(64, _num(t["tam"], 34))))} if t.get("tam") else {})}
                     for t in (e.get("etiquetas") or [])[:2] if isinstance(t, dict) and t.get("texto")]
        if etiquetas:
            x["etiquetas"] = etiquetas
        barras = [{"texto": _corta(b.get("texto"), 20), "valor": max(0.0, min(1.0, _num(b.get("valor"), 0.5))),
                   "etiqueta": _corta(b.get("etiqueta"), 14), "color": _color(b.get("color"))}
                  for b in (e.get("barras") or [])[:3] if isinstance(b, dict)]
        if barras:
            x["barras"] = barras
        c = e.get("contador")
        if isinstance(c, dict) and c.get("hasta") is not None:
            x["contador"] = {"desde": _num(c.get("desde"), 0), "hasta": _num(c.get("hasta"), 0), "prefijo": _corta(c.get("prefijo"), 4),
                             "sufijo": _corta(c.get("sufijo"), 8), "texto": _corta(c.get("texto"), 32),
                             "color": _color(c.get("color"), "oro"), "decimales": int(max(0, min(2, _num(c.get("decimales"), 0))))}
        gr = e.get("grafica")
        if isinstance(gr, dict) and gr.get("lineas"):
            x["grafica"] = {"eje": _corta(gr.get("eje"), 14), "lineas": [
                {"nombre": _corta(l.get("nombre"), 14).upper(), "color": _color(l.get("color"), "main" if i == 0 else "rojo"),
                 "forma": l.get("forma") if l.get("forma") in FORMAS else "recta"}
                for i, l in enumerate(gr["lineas"][:3]) if isinstance(l, dict)]}
        lista = [{"texto": _corta(it.get("texto"), 26), **({"icono": it["icono"]} if it.get("icono") in ICONOS else {}),
                  **({"cuando": _corta(it["cuando"], 30)} if it.get("cuando") else {})}
                 for it in (e.get("lista") or [])[:4] if isinstance(it, dict) and it.get("texto")]
        if lista:
            x["lista"] = lista
        flechas = [{"de": f.get("de"), "a": f.get("a")} for f in (e.get("flechas") or [])[:2]
                   if isinstance(f, dict) and f.get("de") in POSICIONES and f.get("a") in POSICIONES and f["de"] != f["a"]]
        if flechas:
            x["flechas"] = flechas
        visible = any(k in x for k in ("personas", "fila", "objetos", "etiquetas", "barras", "contador", "grafica", "lista"))
        if not visible:
            previa = escenas[-1] if escenas else None
            if previa and previa.get("personas"):
                x["personas"] = [dict(p, accion=p.get("accion", "quieto")) for p in previa["personas"]]
            else:
                grande = (x["resaltar"][0] if x["resaltar"] else " ".join(texto.split()[:2])).upper()[:22]
                x["etiquetas"] = [{"texto": grande, "color": "oro" if x["color"] != "rojo" else "rojo", "y": 900, "tam": 58}]
        escenas.append(x)
    if len(escenas) < 4:
        raise ValueError("el guion tiene muy pocas escenas")
    ultima = (g.get("escenas") or [{}])[-1] if g.get("escenas") else {}
    cta = ultima.get("cta") if isinstance(ultima, dict) else None
    escenas[-1]["cta"] = {"texto": _corta((cta or {}).get("texto") or "SÍGUEME", 18).upper(),
                          "opciones": [_corta(o, 14).upper() for o in ((cta or {}).get("opciones") or [])[:2]]}
    g["escenas"] = escenas
    g["formato"], g["html"] = "pictos", "pictos.html"
    g["paleta"] = g.get("paleta") if g.get("paleta") in PALETAS else "menta"
    g["titulo"] = _corta(g.get("titulo") or escenas[0]["texto"], 90)
    for campo in ("descripcion", "texto_tiktok", "texto_instagram"):
        g[campo] = _corta(g.get(campo) or g["titulo"], 600)
    g["hashtags"] = [h if str(h).startswith("#") else f"#{h}" for h in (g.get("hashtags") or [])[:5]] or ["#dinero", "#motivacion"]
    return g


def guionizar(canal, lecciones):
    from bots.estudio import estudio
    clave = canal["clave"]
    ref = privado.leer(os.path.join("estado", "referencias", f"{privado.alias(clave)}-nuevo.json"), {}) or {}
    receta = (privado.leer(os.path.join("estado", "influencers", "recetas.json"), {}) or {}).get("canales", {}).get(clave) or {}
    radar = (privado.leer(os.path.join("estado", "influencers", "radar", f"{privado.alias(clave)}.json"), {}) or {}).get("resumen") or {}
    hechos = (privado.leer(os.path.join("estado", "estudio", f"{privado.alias(clave)}.json"), {}) or {}).get("videos", [])
    texto = PLANTILLA.format(
        nombre=canal["nombre"], receta=json.dumps({"radar": radar, "receta": {k: v for k, v in receta.items() if k != "fecha"}},
                                                    ensure_ascii=False)[:3500] or "(nada todavía)",
        formula=json.dumps(ref, ensure_ascii=False)[:2500] or "(sin análisis)", lecciones=lecciones or "(nada todavía)",
        hechos="\n".join(f"- {h.get('titulo')}" for h in hechos[-30:]) or "- (nada)", sin_miedo=estudio.SIN_MIEDO,
        vocabulario=VOCABULARIO, ejemplo=json.dumps(EJEMPLO, ensure_ascii=False))
    ultimo = None
    for _ in range(3):
        g = ia.preguntar(texto, papel="guionista", temperatura=0.95)
        if isinstance(g, list) and g:
            g = g[0]
        try:
            if isinstance(g, dict):
                return limpiar(g)
        except (ValueError, TypeError, KeyError) as e:
            ultimo = e
        texto += "\n\nEl intento anterior no tenía la forma pedida. Devuelve SOLO el JSON, con 8 a 12 escenas."
    raise ValueError(f"La IA no dio un guion válido de pictos ({ultimo})")


def _cuando(e, palabra, defecto):
    """Segundo (absoluto) en que la voz dice esa palabra; si no, el defecto."""
    if palabra:
        n = _normal(palabra)
        for p in e.get("palabras") or []:
            w = _normal(p["p"])
            if w and (w.startswith(n) or (n.startswith(w) and len(w) > 2)):
                return p["a"]
    return e["inicio"] + defecto


def eventos(g):
    """Sonidos clavados a lo que aparece: whoosh al cambiar de escena, pop al salir gente, iconos y etiquetas, tic en
    cada punto de una lista, golpe cuando el contador llega y brillo con coronas, trofeos y estrellas."""
    ev, antes = [], set()
    for i, e in enumerate(g["escenas"]):
        a = e["inicio"]
        if i:
            ev.append(("whoosh", max(0.0, a - 0.1), 0.5))
        for k, p in enumerate(e.get("personas") or []):
            if p["id"] not in antes:
                ev.append(("pop", _cuando(e, p.get("cuando"), 0.05 + 0.08 * k), 0.3))
            if p.get("etiqueta"):
                ev.append(("pop", _cuando(e, p.get("etiqueta_cuando"), 0.35), 0.35))
            if p.get("corona_cuando"):
                ev.append(("brillo", _cuando(e, p["corona_cuando"], 0.8), 0.45))
        for k, o in enumerate(e.get("objetos") or []):
            ev.append(("brillo" if o["tipo"] in ("corona", "trofeo", "estrella", "medalla") else "pop",
                       _cuando(e, o.get("cuando"), 0.25 + 0.15 * k), 0.35))
        for t in e.get("etiquetas") or []:
            ev.append(("pop", _cuando(e, t.get("cuando"), 0.4), 0.35))
        for k, it in enumerate(e.get("lista") or []):
            ev.append(("tic", _cuando(e, it.get("cuando"), 0.3 + 0.6 * k), 0.5))
        if e.get("contador"):
            ev.append(("golpe", a + 0.3 + max(1.2, min(3.0, (e["fin"] - a) * 0.55)), 0.7))
        if e.get("barras"):
            ev.append(("tic", a + 0.4, 0.4))
        if e.get("cta"):
            ev.append(("pop", a + 0.4, 0.4))
        antes = {p["id"] for p in e.get("personas") or []}
    return ev
