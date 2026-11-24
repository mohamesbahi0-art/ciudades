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

PROBLEMAS NUEVOS, con sus pruebas:
{problemas}

Para CADA problema elige UNA salida:
- "leccion": una lección concreta (1-2 frases, en español) para quien la necesita. "robot": "escritor" (quien escribe los
  guiones de esa cuenta) o "juez" (el Juzgado). Va en "texto".
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
"salida": "leccion|palanca|reforma|obra|nada", "robot": "escritor|juez", "ambito": "canal|fabrica", "canal": "…",
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
    for k, v in (("reformas", {}), ("obras", []), ("decisiones", []), ("vistos", {}), ("cambios", [])):
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
    juicios = _juicios(desde)
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
                    "formato": c.get("formato_estudio") or c.get("tipo"), "juicios": len(js),
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
                       "canal": privado.alias(p.get("canal") or ""), "clave": p.get("canal"), "veces": 1,
                       "pruebas": [str(p.get("causa"))[:200]]})
    ayer = _iso(_ahora() - dt.timedelta(hours=24))
    for c in parte.get("casos_abiertos") or []:
        if str(c.get("desde") or "9") < ayer and "gemini" not in str(c.get("id")):
            salida.append({"id": f"caso-{c.get('id')}", "tipo": "caso", "robot": c.get("robot"), "canal": "", "veces": c.get("veces"),
                           "pruebas": [c.get("problema")]})
    return salida


# ------------------------------------------------------------------------------------ la Estratega: calidad y resultados
def estratega(parte):
    """Lo que no llega y por qué: [{id, tipo, canal, clave, pruebas…}]."""
    hoy = _ahora().strftime("%Y%m%d")
    activos = {c.get("clave") for c in leer()["cambios"] if c.get("estado") == "activo"}
    salida = []
    for alias, c in (parte.get("cuentas") or {}).items():
        clave = c["clave"]
        if c["juicios"] >= MIN_JUICIOS and (c["mejor"] or 0) < LEJOS and not c.get("reforma"):
            salida.append({"id": f"formato-{alias}-{hoy}", "tipo": "formato", "canal": alias, "clave": clave,
                           "juicios": c["juicios"], "mejor": c["mejor"], "media": c["media"],
                           "pruebas": _consejos(clave) + ([f"cine: {json.dumps(c['cine'], ensure_ascii=False)}"] if c.get("cine") else [])})
        pago, gratis = (c["por_guionista"].get("claude") or {}), (c["por_guionista"].get("gemini") or {})
        if pago.get("n", 0) >= 2 and gratis.get("n", 0) >= 2 and pago["media"] - gratis["media"] >= 8 \
                and (c.get("cambios_elite") or {}).get("guionista") != "claude" and clave not in activos:
            salida.append({"id": f"cerebro-{alias}-{hoy}", "tipo": "cerebro", "canal": alias, "clave": clave,
                           "pruebas": [f"guiones del cerebro de pago: {pago['n']} con media {pago['media']}; del gratis: "
                                       f"{gratis['n']} con media {gratis['media']}"]})
        cine = c.get("cine") or {}
        if cine.get("sesiones", 0) >= 3 and (cine.get("pasan_3s") or 100) < 45:
            salida.append({"id": f"gancho-{alias}-{hoy}", "tipo": "gancho", "canal": alias, "clave": clave,
                           "pruebas": [f"en {cine['sesiones']} sesiones del Cine solo el {cine['pasan_3s']} % pasa del segundo 3"]})
        v1, v2 = (c["por_version"].get("1") or {}), (c["por_version"].get("2+") or {})
        if v2.get("n", 0) >= 3 and v1.get("n") and v2["media"] <= v1["media"]:
            salida.append({"id": f"arreglos-{alias}-{hoy}", "tipo": "arreglos", "canal": alias, "clave": clave,
                           "pruebas": [f"las versiones corregidas ({v2['n']}, media {v2['media']}) no superan a las "
                                       f"originales (media {v1['media']})"]})
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


def _medida(clave=None):
    """La nota media y la mejor de una cuenta (o de todas) en las últimas 48 horas, y cuántos juicios hay en total."""
    por = _juicios()
    js = por.get(clave, []) if clave else [j for lista in por.values() for j in lista]
    hace = _iso(_ahora() - dt.timedelta(hours=48))
    recientes = [j["nota"] for j in js if (j.get("fecha") or "") >= hace] or [j["nota"] for j in js[-6:]]
    return {"media": _media(recientes), "mejor": max(recientes) if recientes else None, "total": len(js)}


def _deshacer(cambio):
    d = privado.cambios_elite()
    if cambio["ambito"] == "canal":
        d["canales"].get(cambio["clave"], {}).pop(cambio["campo"], None)
        if not d["canales"].get(cambio["clave"]):
            d["canales"].pop(cambio["clave"], None)
    else:
        d["fabrica"].pop(cambio["campo"], None)
    _guardar_cambios(d)


def seguimiento(e, prueba=False):
    """Vuelve a medir cada cambio en prueba: el que mejora se queda, el que empeora se deshace, y de los dos se aprende."""
    cerrados = []
    cuaderno = None
    for c in e["cambios"]:
        if c.get("estado") != "activo":
            continue
        clave = c.get("clave") if c["ambito"] == "canal" else None
        por = _juicios()
        js = por.get(clave, []) if clave else [j for lista in por.values() for j in lista]
        despues = [j["nota"] for j in js if (j.get("fecha") or "") > c["fecha"]]
        horas = (_ahora() - (_fecha(c["fecha"]) or _ahora())).total_seconds() / 3600
        antes = (c.get("base") or {}).get("media")
        if len(despues) < SEGUIR_CON or antes is None:
            if horas > CADUCA_CAMBIO:
                c.update(estado="neutro", cerrado=_iso(), resultado="no ha habido vídeos bastantes para medirlo")
                cerrados.append(c)
            continue
        ahora_media = _media(despues)
        donde = f"la cuenta {privado.alias(clave)}" if clave else "la fábrica"
        que = f"poner {c['campo']} = {json.dumps(c['despues'], ensure_ascii=False)} en {donde}"
        if ahora_media - antes >= MEJORA:
            c.update(estado="funciono", cerrado=_iso(), resultado=f"la nota media pasó de {antes} a {ahora_media}")
            leccion = f"FUNCIONÓ {que}: la nota media pasó de {antes} a {ahora_media} ({c.get('causa') or 'sin causa apuntada'})."
        elif ahora_media - antes <= EMPEORA:
            c.update(estado="deshecho", cerrado=_iso(), resultado=f"la nota media bajó de {antes} a {ahora_media}: deshecho")
            leccion = f"NO FUNCIONÓ {que}: la nota media bajó de {antes} a {ahora_media}; se ha deshecho. No repetirlo ahí."
            if not prueba:
                _deshacer(c)
        elif horas > CADUCA_CAMBIO:
            c.update(estado="neutro", cerrado=_iso(), resultado=f"ni mejora ni empeora ({antes} → {ahora_media}): se queda")
            leccion = f"NI FU NI FA {que}: la nota media siguió igual ({antes} → {ahora_media})."
        else:
            continue
        cerrados.append(c)
        if not prueba:
            cuaderno = cuaderno or privado.cuaderno("elite_arquitecto")
            cuaderno.aprender(leccion, confianza=0.8)
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


def arquitecto(problemas, parte, e, prueba=False):
    """Decide con el cerebro bueno y ejecuta. Devuelve las decisiones tomadas ahora."""
    nuevos = [p for p in problemas if p["id"] not in e["vistos"]]
    if not nuevos:
        return []
    cfg = privado.config()
    por_alias = {privado.alias(k): k for s in ("canales", "barrios") for k in (cfg.get(s) or {})}
    activos = [c for c in e["cambios"] if c.get("estado") == "activo"]
    parte_corto = dict(parte, cuentas={a: {k: v for k, v in c.items() if k != "clave" and v not in (None, {}, 0, "")}
                                       for a, c in parte["cuentas"].items()})
    texto = DECIDIR.format(
        skills=_skills(), lecciones=privado.cuaderno("elite_arquitecto").para_el_prompt(12), horas=HORAS,
        parte=json.dumps(parte_corto, ensure_ascii=False)[:9000],
        cambios=json.dumps([{k: c.get(k) for k in ("ambito", "campo", "despues", "fecha")} | {"canal": privado.alias(c.get("clave") or "")}
                            for c in activos], ensure_ascii=False) or "[]",
        problemas=json.dumps([{k: v for k, v in p.items() if k != "clave"} for p in nuevos], ensure_ascii=False)[:7000],
        palancas_canal=_palancas(PALANCAS_CANAL), palancas_fabrica=_palancas(PALANCAS_FABRICA), reforma=REFORMA_HORAS)
    try:
        r = ia.preguntar(texto, papel="elite", temperatura=0.3)
        decisiones = r.get("decisiones") if isinstance(r, dict) else None
        listo = ia.quien().get("motor") == "claude"        # ¿ha pensado el cerebro bueno?
    except Exception:
        decisiones, listo = None, False
    if not isinstance(decisiones, list):
        return []                                           # sin IA: los problemas se quedan para la hora siguiente
    ahora, hechas = _iso(), []
    for p in nuevos:
        d = next((x for x in decisiones if isinstance(x, dict) and x.get("id") == p["id"]), None) or {}
        salida = d.get("salida") if d.get("salida") in ("leccion", "palanca", "reforma", "obra", "nada") else "nada"
        texto_d = str(d.get("texto") or "")[:600]
        clave = p.get("clave") or por_alias.get(str(d.get("canal") or ""))
        apunte = {"id": p["id"], "fecha": ahora, "tipo": p.get("tipo"), "canal": p.get("canal"), "salida": salida,
                  "causa": str(d.get("causa") or "")[:240], "texto": texto_d, "porque": str(d.get("porque") or "")[:300],
                  "como_se_sabra": str(d.get("como_se_sabra") or "")[:240], "cerebro": "claude" if listo else "gratis"}
        if salida in ("palanca", "reforma") and not listo:
            # un cambio de verdad solo lo decide el cerebro bueno: se deja para cuando tenga su hucha (no se marca visto)
            continue
        if salida == "leccion" and texto_d:
            robot = _cuaderno_de(clave, d.get("robot"))
            nombre = ((cfg.get("barrios") or {}).get(clave) or (cfg.get("canales") or {}).get(clave) or {}).get("nombre") or "todas"
            if not prueba:
                c = privado.cuaderno(robot)
                c.aprender(f"(Élite, para «{nombre}») {texto_d}", confianza=0.75 if listo else 0.55)   # nunca «del dueño»
                c.guardar()
            apunte.update(robot=robot, deshacer=f"quitar esa lección del cuaderno de {robot}")
        elif salida == "palanca":
            ambito = "fabrica" if d.get("ambito") == "fabrica" else "canal"
            campo, valor = str(d.get("campo") or ""), d.get("valor")
            if ambito == "canal" and not clave:
                apunte.update(salida="nada", rechazada="no se sabe de qué cuenta habla")
            elif not _vale(ambito, campo, valor):
                apunte.update(salida="nada", rechazada=f"«{campo}» = {json.dumps(valor, ensure_ascii=False)[:60]} no está "
                                                       "en la lista de palancas o se sale de sus límites")
            elif any(c["ambito"] == ambito and c.get("clave") == (clave if ambito == "canal" else None) for c in activos):
                apunte.update(salida="nada", rechazada="ya hay un cambio en prueba ahí: primero se mide ese")
            else:
                cambios = privado.cambios_elite()
                if ambito == "canal":
                    antes = privado.canal(clave).get(campo)
                    cambios["canales"].setdefault(clave, {})[campo] = valor
                else:
                    antes = privado.ajustes()
                    for parte_ruta in campo.split("."):
                        antes = antes.get(parte_ruta) if isinstance(antes, dict) else None
                    cambios["fabrica"][campo] = valor
                cambio = {"id": p["id"], "fecha": ahora, "ambito": ambito, "clave": clave if ambito == "canal" else None,
                          "campo": campo, "antes": antes, "despues": valor, "causa": apunte["causa"],
                          "base": _medida(clave if ambito == "canal" else None), "estado": "activo"}
                if not prueba:
                    _guardar_cambios(cambios)
                e["cambios"].append(cambio)
                activos.append(cambio)
                apunte.update(ambito=ambito, campo=campo, antes=antes, despues=valor,
                              deshacer="se deshace solo si empeora; a mano, quitándolo de estado/elite/ajustes.json")
        elif salida == "reforma" and clave:
            hasta = _iso(_ahora() + dt.timedelta(hours=REFORMA_HORAS))
            e["reformas"][clave] = {"hasta": hasta, "desde": ahora,
                                    "motivo": "en reforma por la Élite: " + (apunte["causa"] or "su formato no llega a la nota")
                                              + "; descansa mientras se rehace"}
            e["obras"].append({"id": p["id"], "fecha": ahora, "estado": "para_claude", "canal": p.get("canal"),
                               "que": texto_d or "rehacer el formato de esta cuenta", "porque": apunte["porque"],
                               "pruebas": p.get("pruebas")})
            apunte.update(hasta=hasta, deshacer="quitar la cuenta de «reformas» en estado/elite/elite.json")
        elif salida == "obra":
            e["obras"].append({"id": p["id"], "fecha": ahora, "estado": "para_claude", "canal": p.get("canal"),
                               "que": texto_d, "porque": apunte["porque"], "pruebas": p.get("pruebas")})
        e["vistos"][p["id"]] = ahora
        hechas.append(apunte)
    return hechas


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prueba", action="store_true", help="mira y decide, pero no cambia nada")
    a = p.parse_args(argv)
    desde = _ahora() - dt.timedelta(hours=HORAS)
    e = leer()
    medidos = seguimiento(e, a.prueba)                 # 1. lo que cambió antes: ¿funcionó?
    parte = parte_general(desde)                       # 2. el Espía junta el parte general
    fallos, calidad = espia(parte, desde), estratega(parte)   # 3. qué falla y qué no llega
    hechas = arquitecto(fallos + calidad, parte, e, a.prueba)  # 4. el Arquitecto decide y ejecuta
    e["decisiones"] = (e["decisiones"] + hechas)[-60:]
    e["obras"] = e["obras"][-40:]
    e["cambios"] = e["cambios"][-60:]
    limite = _iso(_ahora() - dt.timedelta(days=7))
    e["vistos"] = {k: v for k, v in e["vistos"].items() if v >= limite}
    e["reformas"] = {k: v for k, v in e["reformas"].items() if str(v.get("hasta") or "") >= _iso()}
    e.update(ultimo=_iso(), mirado={"fallos": len(fallos), "calidad": len(calidad), "cuentas": len(parte["cuentas"])},
             parte=dict(parte, cuentas={alias: {k: v for k, v in c.items() if k != "clave"}
                                        for alias, c in parte["cuentas"].items()}),
             problemas=[{k: p.get(k) for k in ("id", "tipo", "canal")} for p in fallos + calidad])
    if not a.prueba:
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
