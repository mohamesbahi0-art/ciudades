"""La Élite: los tres mandamases de las ciudades (lo pidió el dueño). Cada hora lo miran TODO desde arriba, leyendo los
partes de la Policía, los Mecánicos, Derechos Sociales, el Juzgado, el Cine y la fábrica, y se meten cuando algo falla una
y otra vez, la culpa es de un robot o hace falta un sistema nuevo. Los arreglos pequeños son de los Mecánicos.

- El Espía (`elite_espia`): junta el parte general (todo lo que pasa, cuenta a cuenta) y saca los fallos que se repiten.
- La Estratega (`elite_estratega`): vigila la calidad y los resultados (notas del Juzgado, quién escribió cada guion,
  dónde se va el público del Cine, lo que el dueño descarta) y saca lo que no llega y por qué.
- El Arquitecto (`elite_arquitecto`): decide y ejecuta, con el cerebro más listo y sus skills (bots/elite/skills/):
    · lección: enseña al robot culpable lo que tiene que cambiar (su cuaderno);
    · palanca: cambia un ajuste de una cuenta o de la fábrica entera, dentro de una lista cerrada y con sus límites
      (quién escribe, ritmo, intentos, filtros encendidos, prioridades…);
    · reforma: una cuenta que gasta IA sin acercarse a la nota descansa mientras se rehace su formato;
    · obra: cuando hay que cambiar un robot por otro o construir un sistema nuevo, deja el encargo para Claude con el
      porqué y las pruebas (los robots de GitHub no reescriben programas solos).
  Cada cambio lleva su medida de antes; a los 3 vídeos juzgados lo vuelve a medir: si ha mejorado se queda, si ha
  empeorado se deshace solo, y las dos cosas las apunta en su cuaderno. Así aprende cada hora.
Nunca tocan las lecciones del dueño, su nota mínima, las claves, los permisos ni el dinero. Los cambios no tocan config/:
van en estado/elite/ajustes.json y quitarlos de ahí los deshace. Todo queda en estado/elite/elite.json (privado).

Uso:  python bots/elite/elite.py [--prueba]
"""
import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import ia, privado  # noqa: E402

ESTADO = os.path.join("estado", "elite", "elite.json")
SKILLS = os.path.join(RAIZ, "bots", "elite", "skills")
HORAS = 24                 # lo que miran hacia atrás
MIN_JUICIOS = 5            # juicios de una cuenta antes de opinar de su formato
LEJOS = 78                 # si la mejor nota no pasa de aquí, el formato no llega
REFORMA_HORAS = 12         # lo que descansa una cuenta mandada a reforma (se deshace borrándola de «reformas»)
FALLOS_REPETIDOS = 4       # veces que un robot falla igual en un día para que sea cosa de la Élite
SEGUIR_CON = 3             # vídeos juzgados después de un cambio para volver a medirlo
MEJORA, EMPEORA = 2, -3    # puntos de nota media para dar un cambio por bueno o deshacerlo
CADUCA_CAMBIO = 72         # horas: un cambio que ni mejora ni empeora se da por neutro y deja sitio a otro
SIN_VIDEOS = 24            # horas: un cambio de una cuenta que la deja sin hacer vídeos se deshace
MARGEN_TURNO = 45          # minutos: los vídeos juzgados justo después de un cambio se empezaron antes y no cuentan
LLAMADAS_DIA = 4           # veces al día, como mucho, que el Arquitecto piensa con el cerebro caro
REPOSO_HORAS = 6           # un mismo problema de una misma cuenta no se vuelve a decidir antes de esto…
REPOSO_JUICIOS = 4         # …ni sin estos vídeos juzgados nuevos (así no se decide dos veces con las mismas pruebas)


def _entero(a, b):
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and a <= v <= b


def _numero(a, b):
    return lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and a <= v <= b


def _velocidad(v):
    m = re.fullmatch(r"([+-])(\d{1,2})%", str(v))
    return bool(m) and -10 <= int(m.group(1) + m.group(2)) <= 20


def _segundos(v):
    return (isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in v)
            and 8 <= v[0] < v[1] <= 180)


# Lo ÚNICO que la Élite puede cambiar sola, con sus límites. Fuera de aquí, nada (y nunca la nota mínima del dueño).
PALANCAS_CANAL = {
    "guionista": (lambda v: v in ("claude", "cualquiera"),
                  "quién escribe sus guiones: \"claude\" (solo el cerebro de pago: menos vídeos, mejores) o \"cualquiera\""),
    "intentos_estudio": (_entero(1, 3), "intentos seguidos por turno en las cuentas animadas (1 a 3)"),
    "nota_para_arreglar": (_entero(65, 85), "desde qué nota un suspenso se rehace con sus fallos en vez de tirarse (65 a 85)"),
    "velocidad_estudio": (_velocidad, "velocidad de la voz en las cuentas animadas, de \"-10%\" a \"+20%\""),
    "velocidad": (_velocidad, "velocidad de la voz en los canales con dibujos o fotos, de \"-10%\" a \"+20%\""),
    "hueco_estudio": (_numero(0.15, 0.5), "silencio entre escenas en segundos (0.15 a 0.5): menos = más ritmo"),
    "segundos": (_segundos, "duración [mínimo, máximo] del vídeo en segundos (entre 8 y 180)"),
}
PALANCAS_FABRICA = {
    "videos_por_ronda": (_entero(1, 6), "vídeos como mucho por ronda y línea (1 a 6)"),
    "horas_si_va_lejos": (_numero(1, 12), "cada cuántas horas lo intenta una cuenta que va lejos del 90 (1 a 12)"),
    "versiones_por_video": (_entero(1, 4), "versiones de un mismo vídeo (el original y sus arreglos), de 1 a 4"),
    "intentos_fallidos_dia": (_entero(2, 20), "turnos suspendidos al día por cuenta antes de parar hasta mañana (2 a 20)"),
    "nota_para_arreglar": (_entero(65, 85), "desde qué nota se rehace un suspenso en todas las cuentas (65 a 85)"),
    "sala_ideas": (lambda v: isinstance(v, bool), "la Sala de Ideas encendida (true) o apagada (false)"),
    "juzgado.jurado.encendido": (lambda v: isinstance(v, bool), "el Jurado popular encendido o apagado"),
    "coliseo.encendido": (lambda v: isinstance(v, bool), "el Coliseo encendido o apagado"),
    "juzgado.publico.personas": (_entero(20, 200), "espectadores del Cine (20 a 200)"),
    "prioridad": (None, "el orden de las cuentas (lista con las mismas claves, la primera va antes)"),
}

DECIDIR = """Eres el Arquitecto de la Élite: el que manda sobre todos los robots de una fábrica de vídeos cortos (YouTube
Shorts, TikTok e Instagram). Tus dos compañeros te traen el parte: el Espía (fallos que se repiten) y la Estratega
(calidad y resultados). Tú decides y lo que decides se ejecuta solo, así que decide como el mejor ingeniero: causa,
prueba, el cambio más pequeño que la arregla y cómo se sabrá si ha funcionado.

TUS SKILLS (síguelas):
{skills}

LO QUE YA HAS APRENDIDO (tu cuaderno; no repitas lo que ya falló):
{lecciones}

PARTE GENERAL (últimas {horas} horas; lo sabes todo):
{parte}

CAMBIOS TUYOS QUE SIGUEN EN PRUEBA (no pongas otro en la misma cuenta hasta que se midan):
{cambios}

LO QUE YA DECIDISTE ANTES (no lo repitas con otras palabras; si no funcionó, sube un escalón: palanca, reforma u obra):
{antes}

PROBLEMAS NUEVOS, con sus pruebas:
{problemas}

Para CADA problema elige UNA salida:
- "leccion": una lección concreta y comprobable (1-2 frases, en español) para quien escribe los guiones de esa cuenta.
  Va en "texto". Al Juzgado NO le das lecciones tú: si crees que el problema es el juez, la salida es "obra" y lo
  explicas (nadie ablanda al juez sin que lo revise un programador). Mira antes en el parte si la cuenta está parada
  esperando otra cosa ("espera"): a quien no está haciendo vídeos no le sirve una lección.
- "palanca": cambiar UN ajuste. "ambito": "canal" o "fabrica"; "canal": la cuenta (como sale en el parte); "campo" y
  "valor" de esta lista y dentro de sus límites:
  De una cuenta:
{palancas_canal}
  De la fábrica entera:
{palancas_fabrica}
- "reforma": la cuenta gasta IA sin acercarse a la nota y ninguna lección ni palanca lo arregla: descansa {reforma} horas
  y se encarga rehacer su formato. En "texto", qué hay que rehacer.
- "obra": hace falta código nuevo (cambiar un robot por otro, un formato nuevo, un sistema nuevo). En "texto", qué hay
  que construir y por qué, en 2-4 frases, para el programador.
- "nada": no hay pruebas bastantes o no es cosa tuya (IA sin cupo, servicio caído: eso es de los Mecánicos).
Nunca: tocar la nota mínima del dueño, contradecir algo que haya dicho el dueño, claves, permisos ni dinero.

Devuelve SOLO un JSON: {{"decisiones": [{{"id": "id del problema", "causa": "la causa en una frase",
"salida": "leccion|palanca|reforma|obra|nada", "ambito": "canal|fabrica", "canal": "…",
"campo": "…", "valor": …, "texto": "…", "porque": "la prueba en una frase",
"como_se_sabra": "qué tiene que pasar para darlo por bueno"}}]}}"""


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _iso(momento=None):
    return (momento or _ahora()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fecha(t):
    try:
        return dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _media(notas):
    return round(sum(notas) / len(notas), 1) if notas else None


def leer():
    e = privado.leer(ESTADO, {}) or {}
    for k, v in (("reformas", {}), ("obras", []), ("decisiones", []), ("vistos", {}), ("cambios", []), ("ultimas", {}),
                 ("llamadas", {})):
        e.setdefault(k, v)
    return e


def en_reforma(clave, estado=None, ahora=None):
    """El motivo si la Élite tiene la cuenta en reforma (lo respeta la fábrica al planear); None si puede trabajar."""
    r = ((estado or leer()).get("reformas") or {}).get(clave)
    if r and (_fecha(r.get("hasta")) or _ahora()) > (ahora or _ahora()):
        return r.get("motivo") or "en reforma por orden de la Élite"
    return None


def _juicios(desde=None):
    """Los juicios de vídeo de verdad (no pruebas), por cuenta y en orden: {clave: [juicio…]}."""
    por = {}
    patron = os.path.join(privado.carpeta(), "estado", "juzgado", "juicios", "*.json")
    for ruta in sorted(glob.glob(patron))[-600:]:
        if ruta.endswith(("-idea.json", "-jurado.json")):
            continue
        j = privado.leer(os.path.relpath(ruta, privado.carpeta()), {}) or {}
        f = _fecha(j.get("fecha"))
        if j.get("tipo") != "video" or j.get("prueba") or not f or not isinstance(j.get("nota"), (int, float)):
            continue
        if desde is None or f >= desde:
            por.setdefault(j.get("canal"), []).append(j)
    for lista in por.values():
        lista.sort(key=lambda j: j.get("fecha") or "")
    return por


# --------------------------------------------------------------------------------------------- el Espía: el parte general
def parte_general(desde):
    """Todo lo que pasa, cuenta a cuenta y en la fábrica entera (lo que «sabe» la Élite). Sin IA."""
    cfg = privado.config()
    todos = _juicios()
    juicios = {k: [j for j in js if (_fecha(j.get("fecha")) or desde) >= desde] for k, js in todos.items()}
    esperan = {}
    for ruta in glob.glob(os.path.join(privado.carpeta(), "estado", "fabrica*.json")):
        esperan.update((privado.leer(os.path.relpath(ruta, privado.carpeta()), {}) or {}).get("esperan") or {})
    cifras = privado.leer(os.path.join("estado", "app", "cifras.json"), {}) or {}
    cambios = privado.cambios_elite()
    cuentas = {}
    for seccion in ("canales", "barrios"):
        for clave, c in (cfg.get(seccion) or {}).items():
            js = juicios.get(clave) or []
            activo = (c.get("estado") == "activo") if seccion == "barrios" else not c.get("pausado")
            if not js and not activo:
                continue
            notas = [j["nota"] for j in js]
            quien = {}
            for j in js:
                quien.setdefault(j.get("guionista") or "?", []).append(j["nota"])
            version = {"1": [j["nota"] for j in js if (j.get("version") or 1) == 1],
                       "2+": [j["nota"] for j in js if (j.get("version") or 1) > 1]}
            salas = [j["publico"] for j in js if isinstance(j.get("publico"), dict)]
            errores = [t for t in (privado.leer(os.path.join("estado", "central", f"{clave}.json"), {}) or {}).get("turnos") or []
                       if t.get("resultado") == "error" and (_fecha(t.get("terminado")) or desde) >= desde]
            fuera = [t for t in errores if str(t.get("error") or "").startswith("SinIA") or "dibujos" in str(t.get("error"))]
            dato = {"clave": clave, "que": "canal de YouTube" if seccion == "canales" else "cuenta de TikTok/Instagram",
                    "formato": c.get("formato_estudio") or c.get("tipo"), "de_que_va": str(c.get("tema") or "")[:160] or None,
                    "juicios": len(js), "juicios_total": len(todos.get(clave) or []),
                    "mejor": max(notas) if notas else None, "media": _media(notas), "ultima": notas[-1] if notas else None,
                    "por_guionista": {k: {"n": len(v), "media": _media(v)} for k, v in quien.items()},
                    "por_version": {k: {"n": len(v), "media": _media(v)} for k, v in version.items() if v},
                    "cine": ({"sesiones": len(salas), "pasan_3s": _media([s.get("pasan_3s") or 0 for s in salas]),
                              "final": _media([s.get("final") or 0 for s in salas]),
                              "se_van_en": _media([s["se_van_en"] for s in salas if s.get("se_van_en") is not None])}
                             if salas else None),
                    "descartes_del_dueno": (privado.descartes(clave, 6).count("\n") + 1) if privado.descartes(clave, 6) else 0,
                    "averias": len(errores) - len(fuera), "esperas_por_ia": len(fuera),
                    "espera": str(esperan.get(clave) or "")[:110] or None,
                    "reforma": en_reforma(clave), "cambios_elite": cambios["canales"].get(clave) or None}
            visitas = ((cifras.get("canales") or {}).get(clave) or {}).get("visitas") or {}
            if visitas:
                dato["visitas_hoy"] = visitas.get("hoy")
            cuentas[privado.alias(clave)] = dato
    claude = (privado.leer(os.path.join("estado", "claude.json"), {}) or {}).get("resumen") or {}
    taller = privado.leer(os.path.join("estado", "mecanicos", "taller.json"), {}) or {}
    pausa = (privado.leer(os.path.join("estado", "obras.json"), {}) or {}).get("pausa") or {}
    casos = [c for c in (privado.leer(os.path.join("estado", "casos.json"), {}) or {}).get("casos") or []
             if c.get("estado") != "arreglado"]
    salud = (privado.leer(os.path.join("estado", "derechos", "salud.json"), {}) or {}).get("robots") or {}
    return {"cuentas": cuentas,
            "ia": {"claude_hoy_usd": claude.get("hoy_usd"), "claude_tope_hoy_usd": claude.get("tope_hoy_usd"),
                   "gemini_sin_cupo": len((privado.leer(os.path.join("estado", "gemini.json"), {}) or {}).get("sin_cupo") or []),
                   "pausa": pausa.get("motivo") if pausa.get("activa") else None},
            "taller": {"descansan": sorted(privado.alias(k) for k in (taller.get("cuarentena") or {})),
                       "dibujos_caidos": bool((taller.get("dibujos_caidos") or {}).get("hasta", "") > _iso()),
                       "partes_para_claude": sum(1 for p in taller.get("partes") or [] if p.get("estado") == "para_claude")},
            "casos_abiertos": [{"id": c.get("id"), "robot": c.get("robot"), "problema": str(c.get("problema"))[:120],
                                "desde": c.get("fecha"), "veces": c.get("veces")} for c in casos[:8]],
            "robots_con_mala_salud": sorted(k for k, v in salud.items() if v.get("salud") == "mala")[:10],
            "orden_de_trabajo": [privado.alias(k) for k in (privado.ajustes().get("prioridad") or [])],
            "cambios_fabrica_elite": cambios["fabrica"] or None}


def espia(parte, desde):
    """Los fallos que se repiten: [{id, tipo, robot, canal, veces, pruebas}]."""
    cuenta = {}
    for ruta in glob.glob(os.path.join(privado.carpeta(), "estado", "central", "*.json")):
        d = privado.leer(os.path.relpath(ruta, privado.carpeta()), {}) or {}
        for t in d.get("turnos") or []:
            f = _fecha(t.get("terminado"))
            err = str(t.get("error") or "")
            if t.get("resultado") != "error" or not f or f < desde or err.startswith("SinIA") or "dibujos" in err:
                continue
            cuenta.setdefault((t.get("robot") or "fabrica", t.get("canal"), err.split(":")[0][:40]), []).append(err[:160])
    salida = [{"id": f"robot-{r}-{privado.alias(c or '')}-{e}".replace(" ", "_"), "tipo": "robot", "robot": r,
               "canal": privado.alias(c or ""), "clave": c, "veces": len(v), "pruebas": v[-2:]}
              for (r, c, e), v in cuenta.items() if len(v) >= FALLOS_REPETIDOS]
    for p in [p for p in (privado.leer(os.path.join("estado", "mecanicos", "taller.json"), {}) or {}).get("partes") or []
              if p.get("estado") == "para_claude"][-3:]:
        salida.append({"id": f"parte-{p.get('id') or p.get('fecha')}", "tipo": "parte", "robot": "mecanicos",
                       "canal": privado.alias(p.get("canal") or ""), "clave": p.get("canal"), "veces": p.get("veces") or 1,
                       "pruebas": [str(p.get("causa") or "")[:200], str(p.get("error") or "")[:200]]})
    ayer = _iso(_ahora() - dt.timedelta(hours=24))
    for c in parte.get("casos_abiertos") or []:
        if str(c.get("desde") or "9") < ayer and "gemini" not in str(c.get("id")):
            salida.append({"id": f"caso-{c.get('id')}", "tipo": "caso", "robot": c.get("robot"), "canal": "", "veces": c.get("veces"),
                           "pruebas": [c.get("problema")]})
    return salida


# ------------------------------------------------------------------------------------ la Estratega: calidad y resultados

def estratega(parte):
    """Lo que no llega y por qué: [{id, tipo, canal, clave, pruebas…}]."""
    activos = {c.get("clave") for c in leer()["cambios"] if c.get("estado") == "activo"}
    salida = []
    for alias, c in (parte.get("cuentas") or {}).items():
        clave = c["clave"]
        if c.get("reforma"):
            continue                                        # ya está en reforma: no se le da más vueltas
        if c["juicios"] >= MIN_JUICIOS and (c["mejor"] or 0) < LEJOS:
            salida.append({"id": f"formato-{alias}", "tipo": "formato", "canal": alias, "clave": clave,
                           "juicios": c["juicios"], "mejor": c["mejor"], "media": c["media"],
                           "pruebas": _consejos(clave) + ([f"cine: {json.dumps(c['cine'], ensure_ascii=False)}"] if c.get("cine") else [])})
        pago, gratis = (c["por_guionista"].get("claude") or {}), (c["por_guionista"].get("gemini") or {})
        if pago.get("n", 0) >= 2 and gratis.get("n", 0) >= 2 and pago["media"] - gratis["media"] >= 8 \
                and (c.get("cambios_elite") or {}).get("guionista") != "claude" and clave not in activos:
            salida.append({"id": f"cerebro-{alias}", "tipo": "cerebro", "canal": alias, "clave": clave,
                           "pruebas": [f"guiones del cerebro de pago: {pago['n']} con media {pago['media']}; del gratis: "
                                       f"{gratis['n']} con media {gratis['media']}"]})
        cine = c.get("cine") or {}
        if cine.get("sesiones", 0) >= 3 and (cine.get("pasan_3s") or 100) < 45:
            salida.append({"id": f"gancho-{alias}", "tipo": "gancho", "canal": alias, "clave": clave,
                           "pruebas": [f"en {cine['sesiones']} sesiones del Cine solo el {cine['pasan_3s']} % pasa del segundo 3"]})
        v1, v2 = (c["por_version"].get("1") or {}), (c["por_version"].get("2+") or {})
        if v2.get("n", 0) >= 3 and v1.get("n") and v2["media"] <= v1["media"]:
            salida.append({"id": f"arreglos-{alias}", "tipo": "arreglos", "canal": alias, "clave": clave,
                           "pruebas": [f"las versiones corregidas ({v2['n']}, media {v2['media']}) no superan a las "
                                       f"originales (media {v1['media']})"]})
        if c.get("cambios_elite") and not c["juicios"] and not c.get("espera"):
            salida.append({"id": f"parada-{alias}", "tipo": "parada", "canal": alias, "clave": clave,
                           "pruebas": [f"tiene cambios de la Élite ({json.dumps(c['cambios_elite'], ensure_ascii=False)}) "
                                       "y lleva 24 horas sin un solo vídeo juzgado"]})
        tirados = privado.descartes(clave, 4)
        if tirados.count("\n") >= 1:                       # dos o más descartes del dueño: su gusto manda
            salida.append({"id": f"descartes-{alias}-{hashlib.md5(tirados.encode()).hexdigest()[:6]}",
                           "tipo": "descartes", "canal": alias, "clave": clave, "pruebas": [tirados[:500]]})
    return salida


def _consejos(clave, cuantos=2):
    js = sorted((_juicios(_ahora() - dt.timedelta(hours=HORAS)).get(clave) or []), key=lambda j: j["nota"])
    return [f"({j['nota']}) {str(j.get('consejo') or '')[:200]}" for j in js[:cuantos]]


# ------------------------------------------------------------------------- el Arquitecto: seguir, decidir y ejecutar
def _guardar_cambios(d):
    privado.escribir(privado.CAMBIOS_ELITE, dict(d, actualizado=_iso()))



def _videos(js, desde=None):
    """Un vídeo cuenta una vez, con su mejor nota (sus versiones corregidas son el mismo vídeo). {vídeo: nota}."""
    por = {}
    for j in js:
        if desde and (j.get("fecha") or "") <= desde:
            continue
        k = (j.get("canal"), j.get("arreglo_de") or j.get("titulo"))
        por[k] = max(por.get(k, 0), j["nota"])
    return por


def _medida(clave=None):
    """La nota media y la mejor de una cuenta (o, cuenta a cuenta, de todas) en las últimas 48 horas."""
    por = _juicios()
    hace = _iso(_ahora() - dt.timedelta(hours=48))
    if clave:
        notas = list(_videos(por.get(clave, []), hace).values()) or [j["nota"] for j in por.get(clave, [])[-6:]]
        return {"media": _media(notas), "mejor": max(notas) if notas else None, "videos": len(notas)}
    cuentas = {k: _media(list(_videos(js, hace).values())) for k, js in por.items() if _videos(js, hace)}
    return {"por_cuenta": cuentas, "media": _media(list(cuentas.values())), "videos": sum(len(_videos(js, hace)) for js in por.values())}



def _deshacer(cambio):
    """Quita el cambio. Si antes había otro valor puesto por la propia Élite (un cambio anterior que funcionó), vuelve a
    ese; si no, se quita del todo y manda otra vez la configuración."""
    d = privado.cambios_elite()
    sitio = d["canales"].setdefault(cambio["clave"], {}) if cambio["ambito"] == "canal" else d["fabrica"]
    if cambio.get("habia_cambio"):
        sitio[cambio["campo"]] = cambio.get("antes")
    else:
        sitio.pop(cambio["campo"], None)
    if cambio["ambito"] == "canal" and not d["canales"].get(cambio["clave"]):
        d["canales"].pop(cambio["clave"], None)
    _guardar_cambios(d)



def seguimiento(e, prueba=False):
    """Vuelve a medir cada cambio en prueba: el que mejora se queda, el que empeora (o deja a la cuenta sin hacer vídeos)
    se deshace, y de todo se aprende. Solo cuentan los vídeos empezados después del cambio, cada vídeo una vez, y en los
    cambios de la fábrica entera se compara cada cuenta consigo misma."""
    cerrados, cuaderno = [], None
    por = _juicios()
    for c in e["cambios"]:
        if c.get("estado") != "activo":
            continue
        hecho = _fecha(c["fecha"]) or _ahora()
        desde = _iso(hecho + dt.timedelta(minutes=MARGEN_TURNO))
        horas = (_ahora() - hecho).total_seconds() / 3600
        base = c.get("base") or {}
        if c["ambito"] == "canal":
            despues = list(_videos(por.get(c.get("clave"), []), desde).values())
            antes, ahora_media, bastantes = base.get("media"), _media(despues), len(despues) >= SEGUIR_CON
            donde = f"la cuenta {privado.alias(c.get('clave') or '')}"
        else:                                   # cada cuenta contra su propia media de antes
            difs = [m - base["por_cuenta"][k] for k, m in
                    ((k, _media(list(_videos(js, desde).values()))) for k, js in por.items()
                     if len(_videos(js, desde)) >= 2 and k in (base.get("por_cuenta") or {})) if m is not None]
            antes, ahora_media = 0.0, (_media(difs) if difs else None)
            bastantes = len(difs) >= 2
            despues, donde = difs, "la fábrica"
        que = f"poner {c['campo']} = {json.dumps(c['despues'], ensure_ascii=False)} en {donde}"
        leccion = None
        if c["ambito"] == "canal" and not despues and horas > SIN_VIDEOS:
            c.update(estado="deshecho", cerrado=_iso(), resultado=f"en {SIN_VIDEOS} horas la cuenta no hizo ni un vídeo: deshecho")
            leccion = f"NO FUNCIONÓ {que}: dejó la cuenta {SIN_VIDEOS} horas sin hacer vídeos; se ha deshecho. No repetirlo ahí."
            if not prueba:
                _deshacer(c)
        elif not bastantes or antes is None or ahora_media is None:
            if horas <= CADUCA_CAMBIO:
                continue
            c.update(estado="neutro", cerrado=_iso(), resultado="no ha habido vídeos bastantes para medirlo: se queda")
        elif ahora_media - antes >= MEJORA:
            c.update(estado="funciono", cerrado=_iso(),
                     resultado=(f"la nota media pasó de {antes} a {ahora_media}" if c["ambito"] == "canal"
                                else f"las cuentas subieron {ahora_media} puntos de media"))
            leccion = f"FUNCIONÓ {que}: {c['resultado']} ({c.get('causa') or 'sin causa apuntada'})."
        elif ahora_media - antes <= EMPEORA:
            c.update(estado="deshecho", cerrado=_iso(),
                     resultado=(f"la nota media bajó de {antes} a {ahora_media}: deshecho" if c["ambito"] == "canal"
                                else f"las cuentas bajaron {abs(ahora_media)} puntos de media: deshecho"))
            leccion = f"NO FUNCIONÓ {que}: {c['resultado']}. No repetirlo ahí."
            if not prueba:
                _deshacer(c)
        elif horas > CADUCA_CAMBIO:
            c.update(estado="neutro", cerrado=_iso(), resultado="ni mejora ni empeora: se queda")
            leccion = f"NI FU NI FA {que}: la nota siguió igual."
        else:
            continue
        cerrados.append(c)
        if leccion and not prueba:
            cuaderno = cuaderno or privado.cuaderno("elite_arquitecto")
            cuaderno.aprender(leccion, confianza=0.7)
    if cuaderno:
        cuaderno.guardar()
    return cerrados


def _skills():
    trozos = []
    for ruta in sorted(glob.glob(os.path.join(SKILLS, "*.md"))):
        with open(ruta, encoding="utf-8") as f:
            trozos.append(f.read().strip())
    return "\n\n".join(trozos)[:7000]


def _palancas(tabla):
    return "\n".join(f"    · \"{campo}\": {ayuda}" for campo, (_, ayuda) in tabla.items())


def _vale(ambito, campo, valor):
    tabla = PALANCAS_CANAL if ambito == "canal" else PALANCAS_FABRICA
    if campo not in tabla:
        return False
    if campo == "prioridad":
        ahora = privado.ajustes().get("prioridad") or []
        return isinstance(valor, list) and sorted(map(str, valor)) == sorted(map(str, ahora))
    return bool(tabla[campo][0](valor))


def _cuaderno_de(clave, robot):
    """El cuaderno del robot que de verdad hace ese trabajo en esa cuenta."""
    if robot == "juez":
        return "juez_guardia"
    cfg = privado.config()
    if clave in (cfg.get("barrios") or {}):
        return "guionista"
    return "archivero_mapas" if clave == "mapas" else "escritor"


def _toca(p, e, parte):
    """¿Hay que decidir este problema ahora? Solo si es nuevo o si desde la última vez que se decidió han pasado horas
    Y hay vídeos juzgados nuevos (así no se paga dos veces por decidir lo mismo con las mismas pruebas)."""
    if p["id"] in e["vistos"]:
        ultima = e["ultimas"].get(p["id"]) or {"fecha": e["vistos"][p["id"]], "juicios": 0}
        if p["tipo"] in ("descartes", "robot", "parte", "caso"):
            return False                      # su id ya cambia cuando cambian las pruebas
        horas = (_ahora() - (_fecha(ultima.get("fecha")) or _ahora())).total_seconds() / 3600
        total = ((parte["cuentas"].get(p.get("canal")) or {}).get("juicios_total") or 0)
        return horas >= REPOSO_HORAS and total - (ultima.get("juicios") or 0) >= REPOSO_JUICIOS
    return True


def _llamadas_hoy(e):
    return (e.get("llamadas") or {}).get(_iso()[:10], 0)


def arquitecto(problemas, parte, e, prueba=False):
    """Decide con el cerebro bueno y ejecuta. Devuelve las decisiones tomadas ahora."""
    e.setdefault("ultimas", {})
    nuevos = [p for p in problemas if _toca(p, e, parte)]
    if not nuevos:
        return []
    if _llamadas_hoy(e) >= LLAMADAS_DIA:        # hoy ya ha pensado bastante: lo nuevo espera a mañana (o a otra hucha)
        print(f"élite: hoy ya ha decidido {LLAMADAS_DIA} veces; lo nuevo espera", flush=True)
        return []
    cfg = privado.config()
    todas = {k for s_ in ("canales", "barrios") for k in (cfg.get(s_) or {})}
    por_alias = {privado.alias(k): k for k in todas}
    activos = [c for c in e["cambios"] if c.get("estado") == "activo"]
    parte_corto = dict(parte, cuentas={a: {k: v for k, v in c.items() if k != "clave" and v not in (None, {}, 0, "")}
                                       for a, c in parte["cuentas"].items()})
    antes = [{"cuando": d.get("fecha"), "canal": d.get("canal"), "problema": d.get("tipo"), "salida": d.get("salida"),
              "que": str(d.get("texto") or d.get("campo") or "")[:160]} for d in e["decisiones"][-14:] if d.get("salida") != "nada"]
    texto = DECIDIR.format(
        skills=_skills(), lecciones=privado.cuaderno("elite_arquitecto").para_el_prompt(12), horas=HORAS,
        parte=json.dumps(parte_corto, ensure_ascii=False)[:9000],
        cambios=json.dumps([{k: c.get(k) for k in ("ambito", "campo", "despues", "fecha")} | {"canal": privado.alias(c.get("clave") or "")}
                            for c in activos], ensure_ascii=False) or "[]",
        antes=json.dumps(antes, ensure_ascii=False)[:3000] or "[]",
        problemas=json.dumps([{k: v for k, v in p.items() if k != "clave"} for p in nuevos[:8]], ensure_ascii=False)[:7000],
        palancas_canal=_palancas(PALANCAS_CANAL), palancas_fabrica=_palancas(PALANCAS_FABRICA), reforma=REFORMA_HORAS)
    try:
        r = ia.preguntar(texto, papel="elite", temperatura=0.3)
        decisiones = r.get("decisiones") if isinstance(r, dict) else None
        listo = ia.quien().get("motor") == "claude"        # ¿ha pensado el cerebro bueno?
    except Exception:
        decisiones, listo = None, False
    if not isinstance(decisiones, list):
        return []                                           # sin IA: los problemas se quedan para la hora siguiente
    if listo:
        e.setdefault("llamadas", {})[_iso()[:10]] = _llamadas_hoy(e) + 1
        e["llamadas"] = {k: v for k, v in e["llamadas"].items() if k >= _iso(_ahora() - dt.timedelta(days=7))[:10]}
    ahora, hechas = _iso(), []
    for p in nuevos[:8]:
        d = next((x for x in decisiones if isinstance(x, dict) and x.get("id") == p["id"]), None)
        if not d:
            continue                                        # el modelo no contestó a este: sigue pendiente, no «visto»
        try:
            apunte = _ejecutar(p, d, e, cfg, todas, por_alias, activos, listo, ahora, prueba)
        except Exception as err:                            # un problema raro no tira a los demás ni deja nombres fuera
            print(f"élite: una decisión no se ha podido ejecutar ({type(err).__name__})", flush=True)
            continue
        if apunte is None:
            continue
        e["vistos"][p["id"]] = ahora
        e["ultimas"][p["id"]] = {"fecha": ahora, "juicios": (parte["cuentas"].get(p.get("canal")) or {}).get("juicios_total") or 0}
        hechas.append(apunte)
        if not prueba:
            privado.escribir(ESTADO, e)                     # cada decisión queda apuntada al momento (con su ficha)
    return hechas


def _ejecutar(p, d, e, cfg, todas, por_alias, activos, listo, ahora, prueba):
    """Ejecuta una decisión dentro de lo permitido. Devuelve su apunte, o None si se deja para cuando piense el cerebro bueno."""
    salida = d.get("salida") if d.get("salida") in ("leccion", "palanca", "reforma", "obra", "nada") else "nada"
    texto_d = str(d.get("texto") or "")[:600]
    clave = p.get("clave") or por_alias.get(str(d.get("canal") or ""))
    if clave not in todas:
        clave = None                                        # esa cuenta ya no existe: no se toca nada suyo
    apunte = {"id": p["id"], "fecha": ahora, "tipo": p.get("tipo"), "canal": p.get("canal"), "salida": salida,
              "causa": str(d.get("causa") or "")[:240], "texto": texto_d, "porque": str(d.get("porque") or "")[:300],
              "como_se_sabra": str(d.get("como_se_sabra") or "")[:240], "cerebro": "claude" if listo else "gratis"}
    if salida in ("palanca", "reforma") and not listo:
        return None           # un cambio de verdad solo lo decide el cerebro bueno: se deja para cuando tenga su hucha
    if salida == "leccion" and (d.get("robot") == "juez" or not clave):
        salida = apunte["salida"] = "obra"                  # al Juzgado no se le dan lecciones sin que lo revise Claude
        texto_d = apunte["texto"] = "Revisar esto (la Élite no cambia sola al Juzgado ni a robots sin cuenta): " + texto_d
    if salida == "leccion" and texto_d:
        robot = _cuaderno_de(clave, "escritor")
        nombre = ((cfg.get("barrios") or {}).get(clave) or (cfg.get("canales") or {}).get(clave) or {}).get("nombre") or "todas"
        if not prueba:
            c = privado.cuaderno(robot)
            c.aprender(f"(Élite, para «{nombre}») {texto_d}", confianza=0.75 if listo else 0.55)   # nunca «del dueño»
            c.guardar()
        apunte.update(robot=robot, deshacer=f"quitar esa lección del cuaderno de {robot}")
    elif salida == "palanca":
        ambito = "fabrica" if d.get("ambito") == "fabrica" else "canal"
        campo, valor = str(d.get("campo") or ""), d.get("valor")
        if campo == "prioridad" and isinstance(valor, list):      # el modelo ve alias: se pasan a las claves de verdad
            valor = [por_alias.get(str(x), str(x)) for x in valor]
        if ambito == "canal" and not clave:
            apunte.update(salida="nada", rechazada="no se sabe de qué cuenta habla, o ya no existe")
        elif not _vale(ambito, campo, valor):
            apunte.update(salida="nada", rechazada=f"«{campo}» no está en la lista de palancas o se sale de sus límites")
        elif any(c["ambito"] == ambito and c.get("clave") == (clave if ambito == "canal" else None) for c in activos):
            apunte.update(salida="nada", rechazada="ya hay un cambio en prueba ahí: primero se mide ese")
        else:
            cambios = privado.cambios_elite()
            if ambito == "canal":
                habia = campo in (cambios["canales"].get(clave) or {})
                antes = privado.canal(clave).get(campo)
                cambios["canales"].setdefault(clave, {})[campo] = valor
            else:
                habia = campo in cambios["fabrica"]
                antes = privado.ajustes()
                for parte_ruta in campo.split("."):
                    antes = antes.get(parte_ruta) if isinstance(antes, dict) else None
                cambios["fabrica"][campo] = valor
            cambio = {"id": p["id"], "fecha": ahora, "ambito": ambito, "clave": clave if ambito == "canal" else None,
                      "campo": campo, "antes": antes, "habia_cambio": habia, "despues": valor, "causa": apunte["causa"],
                      "base": _medida(clave if ambito == "canal" else None), "estado": "activo"}
            e["cambios"].append(cambio)
            activos.append(cambio)
            if not prueba:
                _guardar_cambios(cambios)
            apunte.update(ambito=ambito, campo=campo, antes=antes, despues=valor,
                          deshacer="se deshace solo si empeora; a mano, quitándolo de estado/elite/ajustes.json")
    elif salida == "reforma" and clave:
        hasta = _iso(_ahora() + dt.timedelta(hours=REFORMA_HORAS))
        # el motivo es fijo (sale en los registros públicos de la fábrica); la causa, que escribe la IA, va aparte
        e["reformas"][clave] = {"hasta": hasta, "desde": ahora, "causa": apunte["causa"],
                                "motivo": "en reforma por orden de la Élite: descansa mientras se rehace su formato"}
        e["obras"].append({"id": p["id"], "fecha": ahora, "estado": "para_claude", "canal": p.get("canal"),
                           "que": texto_d or "rehacer el formato de esta cuenta", "porque": apunte["porque"],
                           "pruebas": p.get("pruebas")})
        apunte.update(hasta=hasta, deshacer="quitar la cuenta de «reformas» en estado/elite/elite.json")
    elif salida == "reforma":
        apunte.update(salida="nada", rechazada="no se sabe de qué cuenta habla, o ya no existe")
    elif salida == "obra":
        e["obras"].append({"id": p["id"], "fecha": ahora, "estado": "para_claude", "canal": p.get("canal"),
                           "que": texto_d, "porque": apunte["porque"], "pruebas": p.get("pruebas")})
    return apunte


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prueba", action="store_true", help="mira y decide, pero no cambia nada")
    a = p.parse_args(argv)
    try:
        return _repaso(a.prueba)
    except BaseException as err:               # nada de trazas con datos privados en el registro público
        if isinstance(err, KeyboardInterrupt):
            raise
        print(f"élite: el repaso se ha cortado ({type(err).__name__}); lo vuelve a intentar la hora que viene", flush=True)
        return 1


def _repaso(prueba):
    desde = _ahora() - dt.timedelta(hours=HORAS)
    e = leer()
    medidos = seguimiento(e, prueba)                   # 1. lo que cambió antes: ¿funcionó?
    parte = parte_general(desde)                       # 2. el Espía junta el parte general
    fallos, calidad = espia(parte, desde), estratega(parte)   # 3. qué falla y qué no llega
    hechas = arquitecto(fallos + calidad, parte, e, prueba)   # 4. el Arquitecto decide y ejecuta
    e["decisiones"] = (e["decisiones"] + hechas)[-60:]
    e["obras"] = e["obras"][-40:]
    e["cambios"] = e["cambios"][-60:]
    limite = _iso(_ahora() - dt.timedelta(days=30))
    e["vistos"] = {k: v for k, v in e["vistos"].items() if v >= limite}
    e["ultimas"] = {k: v for k, v in (e.get("ultimas") or {}).items() if k in e["vistos"]}
    e["reformas"] = {k: v for k, v in e["reformas"].items() if str(v.get("hasta") or "") >= _iso()}
    e.update(ultimo=_iso(), mirado={"fallos": len(fallos), "calidad": len(calidad), "cuentas": len(parte["cuentas"])},
             parte=dict(parte, cuentas={alias: {k: v for k, v in c.items() if k != "clave"}
                                        for alias, c in parte["cuentas"].items()}),
             problemas=[{k: p.get(k) for k in ("id", "tipo", "canal")} for p in fallos + calidad])
    if not prueba:
        privado.escribir(ESTADO, e)
        for robot, que, dato in (
                ("elite_espia", "vigilancia", {"cuentas": len(parte["cuentas"]), "fallos_repetidos": len(fallos)}),
                ("elite_estratega", "repaso", {"problemas_de_calidad": len(calidad), "tipos": sorted({x["tipo"] for x in calidad})}),
                ("elite_arquitecto", "decisiones", {"tomadas": len(hechas), "salidas": [h["salida"] for h in hechas],
                                                    "cambios_medidos": [f"{c['campo']}: {c['estado']}" for c in medidos]})):
            c = privado.cuaderno(robot)
            c.apuntar(que, dato)
            c.guardar()
    print(f"élite: {len(parte['cuentas'])} cuentas miradas, {len(fallos)} fallos repetidos, {len(calidad)} problemas de "
          f"calidad, {len(hechas)} decisiones ({', '.join(h['salida'] for h in hechas) or 'ninguna nueva'}), "
          f"{len(medidos)} cambios medidos", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
