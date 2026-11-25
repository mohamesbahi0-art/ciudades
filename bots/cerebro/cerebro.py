"""El Cerebro: el que manda sobre todas las ciudades. No es un robot más: mira cada vídeo que juzga el Juzgado, saca
qué falló y qué funcionó, y deja a cada cuenta su PLAN para el siguiente vídeo, para que llegue al 90 con facilidad y
apunte al 100 (el 90 es el mínimo para publicar, no la meta). Trabaja en GitHub cada media hora, sin Claude ni el
ordenador del dueño, y se arregla solo: si un paso suyo falla, lo apunta, sigue con los demás y lo reintenta en la
siguiente pasada.

Qué hace en cada pasada (cerebro.yml):
1. REPARA lo que frena a una cuenta y se puede arreglar sin tocar código (por ejemplo: si el servicio gratis de dibujos
   no entrega, pasa esa cuenta al formato animado, que no necesita dibujos, y lo deshace cuando vuelven).
2. APRENDE de cada vídeo juzgado nuevo: guarda en su memoria qué le vieron los jueces y el público del Cine.
3. MIDE sus planes anteriores: si con un plan la cuenta sube, sus reglas ganan peso; si baja, lo pierden y no se repiten.
4. PIENSA un plan nuevo para cada cuenta con vídeos nuevos (con el cerebro bueno si tiene su parte; si no, con la IA
   gratis en cadena) y lo deja en estado/cerebro/recetas.json. El Escritor lo lee antes de escribir. Piensa con su
   MANUAL (bots/cerebro/saber/*.md: gancho, retención, final, títulos, su formato, experimentos y diagnóstico), que es
   lo mejor de las skills de Claude destilado para que valga también con la IA gratis (ver `saber`).
5. Lo cuenta EN DIRECTO en estado/cerebro/directo.json (lo enseña la app).

Sus límites (no se los salta): no gasta dinero, no baja la nota mínima del dueño, no contradice lo que dijo el dueño,
no toca claves ni permisos y no se salta normas ni bloqueos de ninguna plataforma. Lo que cambia va en
estado/cerebro/ajustes.json (se aplica al leer; quitarlo de ahí lo deshace), nunca en config/.
"""
import argparse
import datetime as dt
import json
import os
import re
import statistics
import sys
import traceback

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from bots.comun import ia, privado  # noqa: E402

CARPETA = os.path.join("estado", "cerebro")
MEMORIA = os.path.join(CARPETA, "memoria.json")
RECETAS = os.path.join(CARPETA, "recetas.json")
AJUSTES = os.path.join(CARPETA, "ajustes.json")
DIRECTO = os.path.join(CARPETA, "directo.json")
JUICIOS = os.path.join("estado", "juzgado", "juicios")
META = 100                    # a por lo máximo: el 90 es el mínimo para publicar, no donde hay que quedarse
RECUERDA = 400                # vídeos juzgados que guarda de cada cuenta
MIRA = 12                     # los últimos que le enseña al pensar
PLANES_POR_PASADA = 4         # cuentas a las que les piensa un plan nuevo en cada pasada (las que más lo necesitan)
MIDE_CON = 2                  # vídeos juzgados después de un plan para poder decir si funcionó
SUBE, BAJA = 2, -2            # puntos de media que cuentan como «mejor» o «peor»
DIBUJOS_FALLOS = 3            # turnos seguidos sin dibujos para pasar la cuenta al formato animado
DIBUJOS_HORAS = 24            # cuánto dura ese cambio antes de volver a probar los dibujos
DIRECTO_GUARDA = 250
SABER = os.path.join(RAIZ, "bots", "cerebro", "saber")    # su manual: ficheros .md cortos, lo más importante arriba
SABER_TOPE = 6000             # caracteres del manual que entran en cada pregunta (la IA gratis tiene el sitio justo)
SABER_FORMATOS = "5-"         # el fichero que va por apartados («## Nombre [formato, formato]»)
FOCOS = {"1-": ("gancho", "arranque", "primer segundo", "primeros segundos", "inicio", "empieza"),   # de qué se quejan
         "2-": ("ritmo", "lento", "lenta", "retenci", "relleno", "aburr", "largo", "se van", "parte muerta"),  # → qué leer
         "3-": ("final", "cierre", "acaba", "termina", "remate", "desenlace"),
         "4-": ("título", "titulo", "texto", "subtítulo", "subtitulo", "legib", "no se lee")}

PENSAR = """Eres EL CEREBRO de una fábrica de vídeos cortos verticales. Tu único trabajo: que el PRÓXIMO vídeo de esta
cuenta saque más nota que los anteriores. La meta es {meta}/100; con menos de {minimo} no se publica. No te conformes.

CUENTA: {que} · formato «{formato}» · idioma {idioma} · se publica en {donde}.

SUS ÚLTIMOS VÍDEOS JUZGADOS (del más antiguo al más nuevo; nota sobre 100, lo que le vieron los jueces y, si lo hay,
lo que dijo el público simulado):
{videos}

CÓMO VA: media {media}, mejor {mejor}, último {ultimo}. El juez que más baja la nota: {juez_duro}.
{planes}
{saber}
{manual}
Piensa como el mejor director de contenido del mundo: busca la CAUSA que se repite, no la lista de síntomas. Lo que
funcionó (los vídeos de más nota) se repite; lo que se repite en los suspensos se corta de raíz. Apóyate en el manual
(sus cifras y plantillas), pero manda lo que enseñan los vídeos de ESTA cuenta. El guionista solo controla el texto,
el orden, el tema, la duración y el título: lo que sea de imagen o montaje, dilo en el diagnóstico, no como orden.

Devuelve SOLO un JSON:
{{"diagnostico": "en 1 o 2 frases sencillas, por qué no llega (o por qué llega)",
  "reglas": ["de 3 a 6 órdenes CONCRETAS y comprobables para el guionista del próximo vídeo (qué hacer en el segundo 0,
              cuántas palabras por escena, qué tipo de tema, cómo acabar…). Nada de «mejora el gancho»: di CÓMO"],
  "no_hagas": ["de 1 a 4 cosas que se han repetido en los suspensos y no deben volver a salir"],
  "repite": "lo que tenía el mejor vídeo y hay que mantener (o cadena vacía)",
  "prueba": "UNA cosa nueva y distinta que probar en el próximo vídeo para romper el techo de nota"}}
Escribe en español sencillo. No inventes datos de la cuenta. No pidas nada que rompa las normas de las redes."""


BUZON = os.path.join(CARPETA, "buzon.json")       # lo que el dueño le escribe desde la app (lo deja ahí la Comisaria)
CHAT = os.path.join(CARPETA, "chat.json")         # la conversación entera, con las respuestas (la copia a la app)
ORDENES_GUARDA = 30                               # órdenes del dueño que el Cerebro tiene presentes a la vez

HABLAR = """Eres EL CEREBRO de la fábrica de vídeos del dueño: el que manda sobre todas las ciudades y su única meta es que
los vídeos lleguen a 100/100. El dueño te escribe desde su app. Contéstale como un compañero de confianza: en español de
España, sencillo, sin tecnicismos, corto (de 2 a 6 frases) y con la verdad (si algo va mal, dilo; si no lo sabes, dilo).

LO QUE TE ESCRIBE AHORA:
«{mensaje}»

LO QUE HABLASTEIS ANTES (lo más nuevo al final):
{historial}

CÓMO VA CADA CUENTA (media y mejor de sus últimos vídeos juzgados; nota mínima de hoy para publicar: {minimo}):
{cuentas}

TUS PLANES AHORA:
{planes}

LO ÚLTIMO QUE HAS HECHO:
{pasos}

LAS CUENTAS QUE EXISTEN (usa la clave exacta en «cuenta»): {claves}

Lo que puedes hacer TÚ ahora mismo con lo que te pide (va en «acciones»):
- "orden": algo que el dueño quiere que hagan los guionistas a partir de ahora (un tema, un estilo, algo que no quiere
  ver). Va como orden del dueño en todos los guiones de esa cuenta (o de todas, con "cuenta": "todas") hasta que él diga
  otra cosa. Escríbela como una orden clara y concreta.
- "repensar": hacer ya un plan nuevo para esa cuenta.
- "quitar_orden": dejar de aplicar una orden suya anterior (pon en "texto" cuál).
- "para_claude": lo que tú no puedes hacer y hace falta tocar el programa, o lo que está fuera de tus límites (cambiar
  la nota mínima, gastar dinero, llaves o permisos, borrar o crear canales). Se lo pasas a Claude; díselo al dueño así.
Si solo pregunta algo, contesta y no hagas nada ("acciones": []).

Devuelve SOLO un JSON: {{"respuesta": "lo que le contestas", "acciones": [{{"tipo": "orden"|"repensar"|"quitar_orden"|
"para_claude", "cuenta": "clave o todas", "texto": "..."}}]}}"""


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _iso(t=None):
    return (t or _ahora()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fecha(texto):
    try:
        return dt.datetime.strptime(str(texto), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def _recorta(texto, tope):
    """Las primeras líneas enteras que caben (los ficheros llevan lo más importante arriba)."""
    fuera = []
    for linea in texto.strip().splitlines():
        if sum(len(x) + 1 for x in fuera) + len(linea) > tope:
            break
        fuera.append(linea)
    while len(fuera) > 1 and (not fuera[-1].strip() or fuera[-1].startswith("#") or fuera[-1].rstrip().endswith(":")):
        fuera.pop()                       # no deja colgando un título de apartado sin nada debajo
    return "\n".join(fuera).rstrip()


def saber(formato, *otros, foco=(), tope=SABER_TOPE):
    """El manual del Cerebro para una cuenta de este formato: lo general recortado (lo de arriba de cada fichero) y el
    apartado de SU formato entero. `otros` son más nombres por los que buscar el apartado (el tipo del canal); `foco`,
    los ficheros de los que más se quejan los jueces («1-», «2-»…), que entran con el doble de sitio. Nunca pasa del
    tope, y si la carpeta no está devuelve cadena vacía (el Cerebro piensa igual, solo que sin manual)."""
    nombres = {str(n).strip().lower() for n in (formato,) + otros if n}
    generales, apartado = [], ""
    try:
        ficheros = sorted(f for f in os.listdir(SABER) if f.endswith(".md"))
    except OSError:
        return ""
    for nombre in ficheros:
        try:
            with open(os.path.join(SABER, nombre), encoding="utf-8") as f:
                texto = f.read().strip()
        except OSError:
            continue
        if not nombre.startswith(SABER_FORMATOS):
            generales.append((nombre, texto))
            continue
        for trozo in re.split(r"\n(?=## )", texto)[1:]:
            claves = re.search(r"\[([^\]]*)\]", trozo.splitlines()[0])
            if claves and nombres & {c.strip().lower() for c in claves.group(1).split(",")}:
                apartado = "# Su formato: " + re.sub(r"\s*\[[^\]]*\]", "", trozo[3:], count=1).strip()
                break
    apartado = _recorta(apartado, tope // 3)
    pesos = [2 if any(nombre.startswith(f) for f in foco) else 1 for nombre, _ in generales]
    sitio = tope - len(apartado) - 2 * (len(generales) + 1)
    trozos = [_recorta(texto, sitio * peso // max(1, sum(pesos))) for (_, texto), peso in zip(generales, pesos)]
    return "\n\n".join(t for t in trozos + [apartado] if t)[:tope]


def _foco(videos):
    """De qué se quejan más los jueces y el público en estos vídeos → qué ficheros del manual entran con más sitio."""
    texto = " ".join(" ".join(v.get("pegas") or []) + " " + str(v.get("fiscalia") or "") + " " + str(v.get("consejo") or "")
                     + " " + str(v.get("publico") or "") for v in videos).lower()
    veces = {f: sum(texto.count(p) for p in palabras) for f, palabras in FOCOS.items()}
    return tuple(f for f in sorted(veces, key=lambda f: -veces[f]) if veces[f])[:2]


class Cerebro:
    def __init__(self, prueba=False):
        self.prueba = prueba
        self.m = privado.leer(MEMORIA, {}) or {}
        self.m.setdefault("cuentas", {})
        self.m.setdefault("saber", [])            # reglas que han funcionado, valgan para la cuenta que valgan
        self.m.setdefault("averias", [])          # lo que le ha fallado a él mismo (y se ha saltado para seguir)
        self.recetas = privado.leer(RECETAS, {}) or {}
        self.recetas.setdefault("cuentas", {})
        self.ajustes = privado.leer(AJUSTES, {}) or {}
        self.ajustes.setdefault("canales", {})
        self.directo = (privado.leer(DIRECTO, {}) or {}).get("pasos", [])
        self.cfg = privado.config()

    # ---------------- en directo ----------------
    def digo(self, que, detalle, cuenta=None):
        """Lo que hace, contado en sencillo para la app. En los registros públicos, la cuenta sale con su alias."""
        self.directo.append({"fecha": _iso(), "que": que, "cuenta": cuenta, "detalle": str(detalle)[:400]})
        print(privado.limpiar(f"cerebro · {que}" + (f" · {privado.alias(cuenta)}" if cuenta else "")), flush=True)

    def cuentas(self):
        for grupo in ("canales", "barrios"):
            for clave, c in (self.cfg.get(grupo) or {}).items():
                if isinstance(c, dict) and not c.get("pausado"):
                    yield clave, dict(c, destino="youtube" if grupo == "canales" else "parasubir")

    def ficha(self, clave):
        return self.m["cuentas"].setdefault(clave, {"videos": [], "vistos": [], "planes": []})

    # ---------------- 1. reparar ----------------
    def reparar(self):
        ahora = _ahora()
        for clave, cambios in list(self.ajustes["canales"].items()):      # lo que ya caducó se deshace solo
            hasta = _fecha((cambios.get("_hasta") or {}).get("hipnotico_cada"))
            if hasta and hasta < ahora:
                cambios.pop("hipnotico_cada", None)
                cambios.get("_hasta", {}).pop("hipnotico_cada", None)
                self.digo("vuelve a probar los dibujos", "Ha pasado un día con el formato animado: esta cuenta vuelve a "
                          "intentar sus dibujos de siempre. Si siguen sin salir, la paso otra vez.", clave)
            if not {k for k in cambios if not k.startswith("_")}:
                self.ajustes["canales"].pop(clave, None)
        for clave, c in self.cuentas():
            if c.get("destino") != "youtube" or c.get("estudio") == "animacion" or c.get("solo_clips") or \
                    c.get("fotos") or c.get("videoteca"):
                continue                      # solo las cuentas que dependen del servicio gratis de dibujos
            if (self.ajustes["canales"].get(clave) or {}).get("hipnotico_cada") == 1:
                continue
            turnos = (privado.leer(os.path.join("estado", "central", f"{clave}.json"), {}) or {}).get("turnos") or []
            seguidos = 0
            for t in reversed(turnos):
                if "dibujos" in str(t.get("error") or "") and "faltan" in str(t.get("error") or ""):
                    seguidos += 1
                else:
                    break
            if seguidos >= DIBUJOS_FALLOS:
                cambio = self.ajustes["canales"].setdefault(clave, {})
                cambio["hipnotico_cada"] = 1
                cambio.setdefault("_hasta", {})["hipnotico_cada"] = _iso(ahora + dt.timedelta(hours=DIBUJOS_HORAS))
                self.digo("arreglo: cuenta sin dibujos", f"Lleva {seguidos} turnos sin poder dibujar (el servicio gratis "
                          "no entrega). La paso un día al formato animado, que no necesita dibujos, para que vuelva a "
                          "sacar vídeos.", clave)

    # ---------------- 2. aprender ----------------
    def aprender(self):
        carpeta = os.path.join(privado.carpeta(), JUICIOS)
        if not os.path.isdir(carpeta):
            return
        nuevos = {}
        for nombre in sorted(os.listdir(carpeta)):
            if not nombre.endswith(".json") or nombre.endswith("-jurado.json"):
                continue
            j = privado.leer(os.path.join(JUICIOS, nombre), {}) or {}
            clave = j.get("canal")
            if j.get("tipo") != "video" or j.get("prueba") or not isinstance(j.get("nota"), (int, float)) or \
                    clave not in dict(self.cuentas()):
                continue
            f = self.ficha(clave)
            if nombre in f["vistos"]:
                continue
            f["vistos"] = (f["vistos"] + [nombre])[-RECUERDA * 2:]
            votos = j.get("votos") or []
            f["videos"] = (f["videos"] + [{
                "fecha": j.get("fecha"), "titulo": str(j.get("titulo") or "")[:110], "nota": j["nota"],
                "sube": j.get("sentencia") == "sube", "version": j.get("version", 1),
                "guionista": j.get("guionista"), "juez": j.get("cerebro"),
                "votos": {str(v.get("juez")): v.get("nota") for v in votos if isinstance(v.get("nota"), (int, float))},
                "pegas": [str(v.get("razon"))[:240] for v in sorted(votos, key=lambda v: v.get("nota") or 0)[:2]
                          if (v.get("nota") or 0) < META],
                "fiscalia": str(j.get("fiscalia") or "")[:260], "consejo": str(j.get("consejo") or "")[:260],
                "graves": [str(x)[:80] for x in (j.get("fallos_graves") or [])][:4],
                "publico": str(j.get("publico_resumen") or "")[:260]}])[-RECUERDA:]
            nuevos[clave] = nuevos.get(clave, 0) + 1
        for clave, n in nuevos.items():
            v = self.ficha(clave)["videos"][-1]
            self.digo("aprendo", f"{n} vídeo(s) juzgado(s) nuevo(s). El último, «{v['titulo']}», sacó {v['nota']}/100.", clave)
        return nuevos

    # ---------------- 3. medir ----------------
    def medir(self):
        for clave, f in self.m["cuentas"].items():
            for plan in f.get("planes") or []:
                if plan.get("resultado"):
                    continue
                despues = [v["nota"] for v in f["videos"] if str(v.get("fecha") or "") > str(plan.get("fecha") or "")]
                if len(despues) < MIDE_CON:
                    continue
                cambio = round(statistics.mean(despues) - (plan.get("media_antes") or 0), 1)
                plan["resultado"] = {"media_despues": round(statistics.mean(despues), 1), "cambio": cambio,
                                     "videos": len(despues), "mejor": max(despues),
                                     "veredicto": "mejor" if cambio >= SUBE else "peor" if cambio <= BAJA else "igual"}
                self.digo("mido mi plan", f"Con mi último plan la media pasó de {plan.get('media_antes')} a "
                          f"{plan['resultado']['media_despues']} ({'+' if cambio >= 0 else ''}{cambio}): "
                          + {"mejor": "funciona, me lo quedo.", "peor": "ha ido a peor: no repito esas reglas.",
                             "igual": "ni sube ni baja: toca probar algo más distinto."}[plan["resultado"]["veredicto"]], clave)
                if plan["resultado"]["veredicto"] == "mejor":      # lo que funciona en una cuenta lo sabrán las demás
                    c = dict(self.cuentas()).get(clave) or {}
                    for regla in (plan.get("reglas") or [])[:3]:
                        self.m["saber"].append({"regla": regla, "formato": c.get("formato_estudio") or c.get("tipo"),
                                                "idioma": c.get("idioma", "es"), "cambio": cambio, "fecha": _iso()})
                    self.m["saber"] = sorted(self.m["saber"], key=lambda s: -float(s.get("cambio") or 0))[:60]

    # ---------------- 4. pensar ----------------
    def _necesita(self, clave):
        """¿Hay que pensarle un plan nuevo? Sí si tiene vídeos juzgados después del último plan (o nunca tuvo plan)."""
        f = self.ficha(clave)
        if f.get("repensar") and f["videos"]:
            return 1000                                    # lo ha pedido el dueño: el primero
        if not f["videos"]:
            return None
        ultimo_plan = (f.get("planes") or [{}])[-1].get("fecha") or ""
        frescos = [v for v in f["videos"] if str(v.get("fecha") or "") > ultimo_plan]
        if not frescos:
            return None
        ultimos = [v["nota"] for v in f["videos"][-MIRA:]]
        return META - statistics.mean(ultimos)            # cuanto más lejos del 100, antes le toca

    def pensar(self):
        cola = sorted(((n, k) for k, _ in self.cuentas() for n in [self._necesita(k)] if n is not None), reverse=True)
        cuentas = dict(self.cuentas())
        for _, clave in cola[:PLANES_POR_PASADA]:
            f, c = self.ficha(clave), cuentas[clave]
            ultimos = f["videos"][-MIRA:]
            notas = [v["nota"] for v in ultimos]
            por_juez = {}
            for v in ultimos:
                for juez, nota in (v.get("votos") or {}).items():
                    por_juez.setdefault(juez, []).append(nota)
            juez_duro = min(por_juez, key=lambda j: statistics.mean(por_juez[j])) if por_juez else "ninguno en concreto"
            videos = "\n".join(
                f"- {v['nota']}/100 {'(SUBE)' if v.get('sube') else ''} «{v['titulo']}»"
                + (f" · versión {v['version']}" if (v.get("version") or 1) > 1 else "")
                + (f" · pegas: {' | '.join(v['pegas'])}" if v.get("pegas") else "")
                + (f" · fiscalía: {v['fiscalia']}" if v.get("fiscalia") else "")
                + (f" · fallos graves: {', '.join(v['graves'])}" if v.get("graves") else "")
                + (f" · público: {v['publico']}" if v.get("publico") else "") for v in ultimos)
            medidos = [p for p in f.get("planes") or [] if p.get("resultado")][-4:]
            planes = ("TUS PLANES ANTERIORES PARA ESTA CUENTA Y CÓMO SALIERON (aprende de ellos: repite lo que subió la "
                      "nota, no repitas lo que la bajó):\n" + "\n".join(
                          f"- reglas: {' / '.join(p.get('reglas') or [])[:500]} → {p['resultado']['veredicto']} "
                          f"({'+' if p['resultado']['cambio'] >= 0 else ''}{p['resultado']['cambio']} de media)"
                          for p in medidos)) if medidos else ""
            formato = c.get("formato_estudio") or c.get("tipo") or "vídeo corto"
            sabido = [s for s in self.m["saber"] if s.get("formato") == formato      # «es» y «es-ES» son el mismo idioma
                      or str(s.get("idioma") or "es")[:2] == str(c.get("idioma") or "es")[:2]][:6]
            saber_txt = ("LO QUE YA TE HA FUNCIONADO EN OTRAS CUENTAS PARECIDAS:\n" + "\n".join(
                f"- {s['regla']} (+{s['cambio']})" for s in sabido)) if sabido else ""
            manual = saber(formato, c.get("tipo"), foco=_foco(ultimos))
            manual = ("TU MANUAL (lo que funciona en vídeos cortos; saca de aquí cifras y plantillas para tus órdenes):\n"
                      + manual + "\n") if manual else ""
            ordenes = [o["texto"] for o in self.m.get("ordenes_del_dueno") or [] if o.get("cuenta") in (clave, "todas")]
            if ordenes:                       # lo que ha pedido el dueño manda: el plan no puede ir contra ello
                saber_txt = (saber_txt + "\nLO QUE HA PEDIDO EL DUEÑO PARA ESTA CUENTA (manda sobre todo; tu plan lo "
                             "respeta y lo lleva a la práctica):\n" + "\n".join(f"- {o}" for o in ordenes[-8:]))
            texto = PENSAR.format(meta=META, minimo=int(c.get("nota_minima") or privado.nota_minima()),
                                  que=c.get("apodo") or c.get("tema") or formato, formato=formato,
                                  idioma={"es": "español", "nl": "neerlandés", "en": "inglés"}.get(str(c.get("idioma", "es"))[:2], "español"),
                                  donde="YouTube Shorts" if c["destino"] == "youtube" else "TikTok e Instagram",
                                  videos=videos, media=round(statistics.mean(notas)), mejor=max(notas), ultimo=notas[-1],
                                  juez_duro=juez_duro, planes=planes, saber=saber_txt, manual=manual)
            try:
                r = ia.preguntar(texto, papel="elite", temperatura=0.6)
                if isinstance(r, list) and r:
                    r = r[0]
                reglas = [str(x).strip()[:300] for x in (r.get("reglas") or []) if str(x).strip()][:6]
                if not reglas:
                    raise ValueError("el plan viene sin reglas")
            except Exception as e:                # sin IA o respuesta rara: esta cuenta se queda con su plan y sigue
                self.averia("pensar", clave, e)
                continue
            plan = {"fecha": _iso(), "media_antes": round(statistics.mean(notas), 1), "mejor_antes": max(notas),
                    "videos": len(f["videos"]), "diagnostico": str(r.get("diagnostico") or "")[:400], "reglas": reglas,
                    "no_hagas": [str(x).strip()[:240] for x in (r.get("no_hagas") or []) if str(x).strip()][:4],
                    "repite": str(r.get("repite") or "")[:300], "prueba": str(r.get("prueba") or "")[:300],
                    "cerebro": ia.quien().get("motor", "gemini")}
            f["planes"] = (f.get("planes") or [])[-30:] + [plan]
            f.pop("repensar", None)
            self.recetas["cuentas"][clave] = {k: plan[k] for k in ("fecha", "diagnostico", "reglas", "no_hagas", "repite",
                                                                   "prueba", "media_antes", "mejor_antes")}
            self.digo("plan nuevo", f"Media {plan['media_antes']}, mejor {plan['mejor_antes']}. {plan['diagnostico']} "
                      f"Para el próximo vídeo: {plan['reglas'][0]}", clave)

    # ---------------- hablar con el dueño ----------------
    def hablar(self):
        """Contesta lo que el dueño le ha escrito desde la app y hace lo que le pide (dentro de sus límites). Lo que no
        se puede contestar ahora (sin IA) se queda para la siguiente pasada: nunca se pierde un mensaje suyo."""
        buzon = privado.leer(BUZON, {}) or {}
        chat = privado.leer(CHAT, {}) or {}
        chat.setdefault("conversacion", [])
        contestados = {m.get("responde_a") for m in chat["conversacion"] if m.get("de") == "cerebro"}
        vistos = {m.get("id") for m in chat["conversacion"]}
        pendientes = [m for m in buzon.get("mensajes") or [] if isinstance(m, dict) and m.get("id") and
                      str(m.get("texto") or "").strip() and m["id"] not in contestados]
        if not pendientes:
            return
        cuentas = dict(self.cuentas())
        # a la IA solo le llegan los alias (barrio-N), nunca el nombre de una cuenta; se traducen al volver
        alias = {privado.alias(k): k for k in cuentas}
        for m in sorted(pendientes, key=lambda x: str(x.get("fecha") or ""))[:5]:
            if m["id"] not in vistos:
                chat["conversacion"].append({"id": m["id"], "de": "dueño", "fecha": m.get("fecha") or _iso(),
                                             "texto": str(m["texto"])[:2000]})
                vistos.add(m["id"])
            historial = "\n".join(f"- {x['de']}: {str(x.get('texto'))[:300]}" for x in chat["conversacion"][-11:-1]) or "- (nada)"
            resumen = []
            for k, c in cuentas.items():
                notas = [v["nota"] for v in (self.ficha(k).get("videos") or [])[-MIRA:]]
                resumen.append(f"- {privado.alias(k)} ({c.get('apodo') or c.get('tipo') or ''}): " + (
                    f"media {round(statistics.mean(notas))}, mejor {max(notas)}, {len(self.ficha(k)['videos'])} vídeos"
                    if notas else "todavía sin vídeos juzgados"))
            planes = "\n".join(f"- {privado.alias(k)}: {r.get('diagnostico', '')[:200]}" for k, r in (self.recetas.get("cuentas") or {}).items()) or "- (ninguno)"
            pasos = "\n".join(f"- {p['fecha'][5:16]} {p['que']} {privado.alias(p['cuenta']) if p.get('cuenta') else ''}: {p['detalle'][:150]}"
                               for p in self.directo[-12:]) or "- (nada)"
            try:
                r = ia.preguntar(HABLAR.format(mensaje=str(m["texto"])[:2000], historial=historial, minimo=privado.nota_minima(),
                                               cuentas="\n".join(resumen), planes=planes, pasos=pasos,
                                               claves=", ".join(alias)), papel="elite", temperatura=0.5)
                if isinstance(r, list) and r:
                    r = r[0]
                respuesta = str(r.get("respuesta") or "").strip()
                if not respuesta:
                    raise ValueError("respuesta vacía")
            except Exception as e:
                self.averia("hablar", None, e)
                break                          # el resto, en la siguiente pasada (en orden)
            hecho = []
            for a in (r.get("acciones") or [])[:6]:
                if isinstance(a, dict):
                    a = dict(a, cuenta=alias.get(a.get("cuenta"), a.get("cuenta")))
                    hecho.append(self._accion(a, cuentas, m))
            chat["conversacion"].append({"id": f"{m['id']}-r", "de": "cerebro", "fecha": _iso(), "responde_a": m["id"],
                                         "texto": respuesta[:2000], "acciones": [h for h in hecho if h]})
            self.digo("hablo con el dueño", "Me ha escrito desde la app y le he contestado"
                      + (f" ({'; '.join(h for h in hecho if h)})" if any(hecho) else "") + ".")
        chat["conversacion"] = chat["conversacion"][-200:]
        chat["actualizado"] = _iso()
        if not self.prueba:
            privado.escribir(CHAT, chat)

    def _accion(self, a, cuentas, mensaje):
        tipo, texto = a.get("tipo"), str(a.get("texto") or "").strip()[:400]
        cuenta = a.get("cuenta") if a.get("cuenta") in cuentas else ("todas" if a.get("cuenta") == "todas" else None)
        ordenes = self.m.setdefault("ordenes_del_dueno", [])
        if tipo == "orden" and texto and cuenta:
            ordenes.append({"fecha": _iso(), "cuenta": cuenta, "texto": texto, "mensaje": mensaje["id"]})
            self.m["ordenes_del_dueno"] = ordenes[-ORDENES_GUARDA:]
            try:                               # y queda en el cuaderno del guionista como lección del dueño (manda)
                c = privado.cuaderno("guionista")
                c.aprender(f"El dueño ({_iso()[:10]}, a través del Cerebro){' en ' + cuenta if cuenta != 'todas' else ''}: {texto}",
                           del_dueno=True)
                c.guardar()
            except Exception:
                pass
            return f"orden apuntada para {'todas las cuentas' if cuenta == 'todas' else cuenta}"
        if tipo == "quitar_orden" and texto:
            antes = len(ordenes)
            palabras = {w for w in texto.lower().split() if len(w) > 3}
            self.m["ordenes_del_dueno"] = [o for o in ordenes if not (palabras and len(palabras & set(o["texto"].lower().split())) >= max(1, len(palabras) // 2))]
            return "orden anterior quitada" if len(self.m["ordenes_del_dueno"]) < antes else ""
        if tipo == "repensar" and cuenta and cuenta != "todas":
            self.ficha(cuenta)["repensar"] = True          # le toca un plan nuevo en esta misma pasada
            return f"plan nuevo para {cuenta}"
        if tipo == "para_claude" and texto:
            self.m.setdefault("para_claude", []).append({"fecha": _iso(), "texto": texto, "mensaje": mensaje["id"],
                                                          "estado": "para_claude"})
            self.m["para_claude"] = self.m["para_claude"][-40:]
            return "se lo paso a Claude"
        return ""

    # ---------------- arreglarse solo ----------------
    def averia(self, paso, cuenta, error):
        """Algo suyo ha fallado: lo apunta, lo cuenta y SIGUE. En la siguiente pasada se vuelve a intentar solo."""
        de_fuera = isinstance(error, ia.SinIA)
        self.m["averias"] = (self.m["averias"] + [{"fecha": _iso(), "paso": paso, "cuenta": cuenta, "de_fuera": de_fuera,
                                                   "error": f"{type(error).__name__}: {str(error)[:200]}"}])[-60:]
        self.digo("espero a la IA" if de_fuera else "me arreglo",
                  ("Ahora ninguna IA contesta para pensar este plan: lo dejo para la siguiente pasada (en media hora)."
                   if de_fuera else f"Me ha fallado el paso «{paso}» ({type(error).__name__}). Lo salto, sigo con lo "
                   "demás y lo repito en la siguiente pasada."), cuenta)

    def paso(self, nombre, funcion):
        try:
            return funcion()
        except Exception as e:
            self.averia(nombre, None, e)
            print(privado.limpiar("\n".join(traceback.format_exc().strip().splitlines()[-6:])), flush=True)

    # ---------------- guardar ----------------
    def guardar(self):
        resumen = {}
        for clave, _ in self.cuentas():
            f = self.m["cuentas"].get(clave) or {}
            notas = [v["nota"] for v in (f.get("videos") or [])[-MIRA:]]
            if notas:
                resumen[clave] = {"media": round(statistics.mean(notas), 1), "mejor": max(notas), "ultimo": notas[-1],
                                  "videos": len(f.get("videos") or []), "planes": len(f.get("planes") or []),
                                  "falta_para_100": round(META - statistics.mean(notas), 1)}
        self.m["actualizado"] = self.recetas["actualizado"] = self.ajustes["actualizado"] = _iso()
        if self.prueba:
            return resumen
        privado.escribir(MEMORIA, self.m)
        privado.escribir(RECETAS, self.recetas)
        privado.escribir(AJUSTES, self.ajustes)
        privado.escribir(DIRECTO, {"actualizado": _iso(), "meta": META, "lee_charla": True, "minutos": [10, 40],
                                   "pasos": self.directo[-DIRECTO_GUARDA:],
                                   "cuentas": resumen, "saber": self.m["saber"][:12],
                                   "ordenes_del_dueno": self.m.get("ordenes_del_dueno", [])[-ORDENES_GUARDA:],
                                   "para_claude": [x for x in self.m.get("para_claude", []) if x.get("estado") == "para_claude"][-10:],
                                   "averias_hoy": sum(1 for a in self.m["averias"] if str(a.get("fecha"))[:10] == _iso()[:10]
                                                      and not a.get("de_fuera"))})
        try:
            c = privado.cuaderno("cerebro")
            c.apuntar("pasada", {"cuentas": len(resumen), "planes": sum(1 for p in self.directo[-40:] if p["que"] == "plan nuevo"
                                                                       and p["fecha"][:13] == _iso()[:13])})
            c.guardar()
        except Exception:
            pass
        return resumen

    def pasada(self):
        self.digo("empiezo", "Miro cómo va cada cuenta, arreglo lo que la frena y preparo su plan para el próximo vídeo.")
        self.paso("hablar", self.hablar)       # lo del dueño, lo primero
        self.paso("reparar", self.reparar)
        self.paso("aprender", self.aprender)
        self.paso("medir", self.medir)
        self.paso("pensar", self.pensar)
        return self.guardar()


ENSAYO = """Eres EL CEREBRO de una fábrica de vídeos cortos. Antes de grabar, haces el ENSAYO: lees el guion como lo
leerían los tres jueces más duros (gancho, ritmo y si se comparte) y el público, y dices qué nota sacaría y qué hay que
cambiar para que saque {meta}. Con menos de {minimo} no se publica.

CUENTA: {que} · formato «{formato}» · idioma {idioma}.
LO QUE LOS JUECES YA LE HAN CRITICADO A ESTA CUENTA (que no vuelva a pasar):
{pegas}
{manual}
EL GUION QUE SE VA A GRABAR:
{guion}

Sé exigente y concreto. Mira sobre todo: ¿el primer segundo enseña algo concreto y chocante, con nombre propio o cifra?
¿El título promete algo que el guion cumple de verdad? ¿Hay protagonistas con nombre y un detalle real, o son genéricos?
¿Es la historia de siempre? ¿El final da para discutir en comentarios?
Devuelve SOLO un JSON: {{"nota": número de 0 a 100 que le pondrían los jueces, "cambios": ["de 0 a 4 cambios CONCRETOS
al texto del guion (qué frase, qué título, qué dato) que más subirían la nota; lista vacía si ya está para {meta}"]}}"""
ENSAYO_BASTA = 92         # con esta nota prevista o más, el guion va tal cual


def ensayo(guion, canal, clave=None):
    """El ensayo antes de grabar: el Cerebro lee el guion como los jueces y devuelve (nota prevista, texto con los
    cambios para el guionista) o (nota, "") si ya vale. Si no hay IA o falla, (None, ""): el vídeo sigue sin ensayo."""
    try:
        clave = clave or canal.get("clave")
        videos = (((privado.leer(MEMORIA, {}) or {}).get("cuentas") or {}).get(clave) or {}).get("videos") or []
        pegas = [p for v in videos[-8:] for p in (v.get("pegas") or [])][-10:]
        formato = canal.get("formato_estudio") or canal.get("tipo") or "vídeo corto"
        escenas = guion.get("escenas") or []
        texto_guion = json.dumps({"titulo": guion.get("titulo"), "gancho": guion.get("texto_pantalla") or
                                  (escenas[0].get("texto") if escenas else ""),
                                  "escenas": [{k: e.get(k) for k in ("voz", "texto") if e.get(k)} for e in escenas]},
                                 ensure_ascii=False)[:7000]
        r = ia.preguntar(ENSAYO.format(
            meta=META, minimo=int(canal.get("nota_minima") or privado.nota_minima()), que=canal.get("apodo") or canal.get("tema") or formato,
            formato=formato, idioma={"es": "español", "nl": "neerlandés", "en": "inglés"}.get(str(canal.get("idioma", "es"))[:2], "español"),
            pegas="\n".join(f"- {p}" for p in pegas) or "- (todavía ninguna)",
            manual=saber(formato, canal.get("tipo"), tope=3000), guion=texto_guion), papel="elite", temperatura=0.3)
        if isinstance(r, list) and r:
            r = r[0]
        nota = max(0, min(100, int(r.get("nota") or 0)))
        cambios = [str(x).strip()[:300] for x in (r.get("cambios") or []) if str(x).strip()][:4]
        if nota >= ENSAYO_BASTA or not cambios:
            return nota, ""
        return nota, ("\n- (ENSAYO DEL CEREBRO antes de grabar: este guion sacaría " + str(nota) + "/100. Reescríbelo ENTERO "
                      "con el mismo tema, aplicando estos cambios uno por uno) " + " | ".join(cambios)
                      + "\n  El guion ensayado era: " + texto_guion[:2500])
    except Exception:
        return None, ""


def receta(clave):
    """Lo que el Cerebro le dice al guionista de esta cuenta antes de escribir (texto listo para sus lecciones)."""
    r = ((privado.leer(RECETAS, {}) or {}).get("cuentas") or {}).get(clave)
    ordenes = [o["texto"] for o in ((privado.leer(MEMORIA, {}) or {}).get("ordenes_del_dueno") or [])
               if o.get("cuenta") in (clave, "todas")]
    del_dueno = ("\n- (LO QUE HA PEDIDO EL DUEÑO, que manda sobre todo lo demás) " + " | ".join(ordenes[-8:])) if ordenes else ""
    if not r or not r.get("reglas"):
        return del_dueno
    return del_dueno + ("\n- (EL CEREBRO, tras estudiar los últimos vídeos juzgados de esta cuenta. La meta es 100/100, no el aprobado. "
            "Cumple estas órdenes una por una)\n  Por qué no llega: " + str(r.get("diagnostico") or "")
            + "\n  HAZ: " + " | ".join(r["reglas"])
            + ("\n  NO HAGAS: " + " | ".join(r["no_hagas"]) if r.get("no_hagas") else "")
            + ("\n  MANTÉN: " + r["repite"] if r.get("repite") else "")
            + ("\n  PRUEBA ESTA VEZ: " + r["prueba"] if r.get("prueba") else ""))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prueba", action="store_true", help="piensa pero no guarda nada")
    a = p.parse_args(argv)
    resumen = Cerebro(prueba=a.prueba).pasada()
    print(f"cerebro: {len(resumen)} cuentas con vídeos juzgados", flush=True)
    try:
        from bots.comun import gemini
        gemini.apuntar_portero()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
