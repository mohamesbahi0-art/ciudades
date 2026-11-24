"""El Taller de los Mecánicos: robots que arreglan solos lo que falla, sin Claude y sin el dueño.

Cada media hora (mecanicos.yml, en GitHub) miran cómo va todo y aplican su receta. Cada receta es un arreglo seguro y
que se puede deshacer (reintentar, relanzar, dejar descansar, limpiar o avisar); nunca tocan el código ni borran nada
del dueño. Lo que no saben arreglar lo dejan como «parte» bien explicado para Claude y, si hace falta el dueño, le
avisan al móvil (una vez al día por tema).

Los mecánicos y sus recetas (el manual largo está en MANUAL.md, que también lee el Jefe de taller cuando diagnostica):
- Mecánico de rondas: si la fábrica lleva más de 2 h y media sin empezar una ronda, la arranca; si un turno falló al
  preparar las herramientas (un fallo de GitHub, no nuestro), lo repite una vez.
- Mecánica de canales: si un canal falla 3 veces seguidas con el mismo fallo, lo manda 12 horas a descansar (para que
  no gaste IA ni ensucie la ronda); si el servicio gratis de dibujos está caído, los canales que dibujan esperan 3 horas.
- Mecánico de limpieza: quita de «Ahora en la fábrica» los vídeos que se quedaron colgados hace más de 3 horas.
- Jefe de taller: mira los fallos que nadie conoce, los diagnostica con la IA pequeña (céntimos) y decide: lo arregla
  un mecánico, es cosa del dueño (llaves, permisos, saldo) o es un fallo de código para Claude. Lleva los partes.

Uso:  python bots/mecanicos/taller.py [--prueba]
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import gemini, ia, privado  # noqa: E402

ESTADO = os.path.join("mecanicos", "taller.json")          # dentro de estado/
SIN_RONDA_MINUTOS = 150
DESCANSO_HORAS, DIBUJOS_HORAS, COLGADO_HORAS = 12, 3, 3
PREPARAR = ("herramientas", "sacar el repositorio", "checkout", "setup-python", "set up job")
REPETIBLES = ("Fábrica", "Revisar canales", "Ojeador de redes", "Estudio de los Influencers", "Radar de nichos",
              "Recolector de clips", "Derechos Sociales", "Cartero", "Juzga mi vídeo", "Directos de la semana")
MENU = ("esperar", "descansar_canal", "avisar_dueno", "para_claude")

DIAGNOSTICO = """Eres el Jefe de taller de una fábrica de vídeos que trabaja sola en GitHub. Este es su manual:
{manual}

Ha salido este fallo, que ninguna receta conoce:
- Dónde: {donde}
- Fallo: {error}
- Veces seguidas: {veces}
Elige UNA salida del menú: "esperar" (es pasajero: red, cupo, un servicio caído), "descansar_canal" (el canal falla
siempre igual: que descanse 12 horas), "avisar_dueno" (hace falta él: una llave, un permiso, saldo) o "para_claude" (es
un fallo del código o de un formato: lo arreglará Claude). Devuelve SOLO un JSON:
{{"salida": "...", "causa": "una frase", "para_el_dueno": "una frase en español sencillo, sin tecnicismos",
  "para_claude": "qué mirar y dónde, en una o dos frases"}}"""


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _fecha(texto):
    try:
        return dt.datetime.strptime(str(texto)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _gh(*args):
    """La herramienta gh con el permiso del propio turno (solo ve y relanza turnos de este repositorio)."""
    r = subprocess.run(["gh", *args, "-R", os.environ.get("GITHUB_REPOSITORY", "")], capture_output=True, text=True)
    return r.returncode, r.stdout


def turnos(cuantos=40):
    codigo, salida = _gh("run", "list", "-L", str(cuantos), "--json",
                         "databaseId,workflowName,status,conclusion,createdAt,event")
    try:
        return json.loads(salida) if codigo == 0 else []
    except ValueError:
        return []


def leer():
    e = privado.leer(os.path.join("estado", ESTADO), {}) or {}
    e.setdefault("arreglos", [])
    e.setdefault("cuarentena", {})
    e.setdefault("partes", [])
    e.setdefault("avisados", {})
    e.setdefault("repetidos", [])
    return e


def en_cuarentena(clave, estado=None, ahora=None):
    """El motivo si el canal descansa ahora (lo respeta la fábrica al planear); None si puede trabajar."""
    c = ((estado or leer()).get("cuarentena") or {}).get(clave)
    if c and (_fecha(c.get("hasta")) or _ahora()) > (ahora or _ahora()):
        return c.get("motivo") or "descansa por un fallo repetido"
    return None


def dibujos_caidos(estado=None, ahora=None):
    hasta = _fecha(((estado or leer()).get("dibujos_caidos") or {}).get("hasta"))
    return bool(hasta and hasta > (ahora or _ahora()))


def _apunta(e, robot, que, detalle, prueba):
    e["arreglos"] = (e["arreglos"] + [{"fecha": privado.ahora(), "robot": robot, "que": que, "detalle": detalle}])[-60:]
    print(privado.limpiar(f"[{robot}] {que}: {detalle}"), flush=True)
    if not prueba:
        c = privado.cuaderno(robot)
        c.apuntar(que, {"detalle": privado.limpiar(detalle)[:200]})
        c.guardar()


def _avisa_una_vez(e, tema, titulo, mensaje, prueba):
    hoy = _ahora().strftime("%Y-%m-%d")
    if e["avisados"].get(tema) == hoy:
        return
    e["avisados"][tema] = hoy
    if not prueba:
        try:
            from bots.central import cartero
            cartero.avisar(titulo, mensaje, etiqueta="wrench")
        except Exception:
            pass


# ---------------- Mecánico de rondas ----------------
def rondas(e, lista, prueba):
    ahora = _ahora()
    fabrica = [t for t in lista if t.get("workflowName") == "Fábrica"]
    viva = any(t.get("status") in ("in_progress", "queued", "pending", "waiting", "requested") for t in fabrica)
    ultima = max((_fecha(t.get("createdAt")) for t in fabrica if _fecha(t.get("createdAt"))), default=None)
    if lista and not viva and (ultima is None or (ahora - ultima).total_seconds() / 60 > SIN_RONDA_MINUTOS):
        if prueba or _gh("workflow", "run", "fabrica.yml")[0] == 0:
            _apunta(e, "mecanico_rondas", "arranca la fábrica",
                    "llevaba más de 2 horas y media sin empezar una ronda: la he arrancado", prueba)
    for t in lista:                               # un turno que falló al preparar las herramientas se repite una vez
        if t.get("conclusion") != "failure" or t.get("workflowName") not in REPETIBLES or t["databaseId"] in e["repetidos"]:
            continue
        creado = _fecha(t.get("createdAt"))
        if not creado or (ahora - creado).total_seconds() > 3 * 3600:
            continue
        _, pasos = _gh("run", "view", str(t["databaseId"]), "--json", "jobs", "-q",
                       '.jobs[].steps[] | select(.conclusion=="failure") | .name')
        fallados = [p.strip().lower() for p in pasos.splitlines() if p.strip()]
        if fallados and all(any(x in p for x in PREPARAR) for p in fallados):
            e["repetidos"] = (e["repetidos"] + [t["databaseId"]])[-80:]
            if prueba or _gh("run", "rerun", str(t["databaseId"]), "--failed")[0] == 0:
                _apunta(e, "mecanico_rondas", "repite un turno",
                        f"«{t['workflowName']}» falló al preparar las herramientas (cosa de GitHub): lo repito", prueba)


# ---------------- Mecánica de canales ----------------
def _turnos_de_hoy():
    todas = []
    for nombre in ("fabrica.json", "fabrica-cuentas.json"):       # las dos líneas de la fábrica
        f = privado.leer(os.path.join("estado", nombre), {}) or {}
        todas += list(f.get("rondas") or []) + [f]
    todas.sort(key=lambda r: str(r.get("empezada") or ""))
    vistos, salida = set(), []
    for r in todas:
        if r.get("empezada") and r["empezada"] not in vistos and not r.get("prueba"):
            vistos.add(r["empezada"])
            salida += [dict(t, cuando=r["empezada"]) for t in r.get("turnos") or []]
    return salida[-60:]


def canales(e, prueba):
    from bots.central import fabrica
    ahora, lista = _ahora(), _turnos_de_hoy()
    recientes = [t for t in lista if (_fecha(t.get("cuando")) or ahora) > ahora - dt.timedelta(hours=3)]
    if sum(1 for t in recientes if "faltan" in str(t.get("error")) and "dibujos" in str(t.get("error"))) >= 2 \
            and not dibujos_caidos(e, ahora):
        e["dibujos_caidos"] = {"hasta": (ahora + dt.timedelta(hours=DIBUJOS_HORAS)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        _apunta(e, "mecanica_canales", "dibujos caídos", f"el servicio gratis de dibujos no contesta: los canales que "
                f"dibujan esperan {DIBUJOS_HORAS} horas (los demás siguen)", prueba)
    por_canal = {}
    for t in lista:
        por_canal.setdefault(t.get("canal"), []).append(t)
    desconocidos = []
    for clave, ts in por_canal.items():
        seguidos = []
        for t in reversed(ts):                    # los últimos fallos seguidos con el mismo error (que no sea de fuera)
            err = str(t.get("error") or "")
            if not err or fabrica.de_fuera(err) or (seguidos and err[:60] != seguidos[0][:60]):
                break
            seguidos.append(err)
        if len(seguidos) >= 3 and not en_cuarentena(clave, e, ahora):
            e["cuarentena"][clave] = {"hasta": (ahora + dt.timedelta(hours=DESCANSO_HORAS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                      "motivo": f"descansa {DESCANSO_HORAS} horas: falló 3 veces seguidas igual "
                                                "(los mecánicos han dejado el parte para arreglarlo)",
                                      "error": seguidos[0][:200]}
            _apunta(e, "mecanica_canales", "canal a descansar", f"{privado.alias(clave)} falló 3 veces seguidas con el "
                    f"mismo fallo: descansa {DESCANSO_HORAS} horas y dejo el parte", prueba)
            desconocidos.append((clave, seguidos[0], len(seguidos)))
    e["cuarentena"] = {k: v for k, v in e["cuarentena"].items() if (_fecha(v.get("hasta")) or ahora) > ahora}
    return desconocidos


# ---------------- Mecánico de limpieza ----------------
def limpieza(e, prueba):
    ruta = os.path.join("estado", "obras.json")
    d = privado.leer(ruta, {}) or {}
    ahora, tocadas = _ahora(), 0
    for o in (d.get("obras") or {}).values():
        visto = _fecha(o.get("actualizado"))
        if o.get("estado") == "en_marcha" and visto and (ahora - visto).total_seconds() > COLGADO_HORAS * 3600:
            o.update(estado="descartado", detalle="se quedó a medias (la ronda se cortó): lo ha retirado el Mecánico",
                     actualizado=privado.ahora())
            tocadas += 1
    if tocadas:
        if not prueba:
            privado.escribir(ruta, d)
        _apunta(e, "mecanico_limpieza", "limpia vídeos colgados", f"{tocadas} vídeo(s) llevaban más de {COLGADO_HORAS} "
                "horas a medias: fuera de «Ahora en la fábrica»", prueba)


# ---------------- Jefe de taller ----------------
def _manual():
    try:
        return open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "MANUAL.md"), encoding="utf-8").read()[:6000]
    except OSError:
        return "(sin manual)"


def jefe(e, desconocidos, prueba):
    claude = privado.leer(os.path.join("estado", "claude.json"), {}) or {}
    if claude.get("sin_saldo") or "llave" in str(claude.get("aviso") or ""):
        _avisa_una_vez(e, "claude", "🔧 La IA de pago necesita que la mires",
                       "La fábrica sigue con la IA gratis, pero la de pago no puede trabajar (saldo o llave). Cuando puedas, "
                       "míralo en la app, en Misiones.", prueba)
        _apunta(e, "jefe_taller", "avisa al dueño", "la IA de pago está sin saldo o con la llave mal", prueba)
    abiertos = {(p.get("canal"), p.get("error", "")[:60]) for p in e["partes"] if p.get("estado") != "arreglado"}
    for clave, error, veces in desconocidos:
        if (clave, error[:60]) in abiertos:
            continue
        parte = {"fecha": privado.ahora(), "canal": clave, "error": privado.limpiar(error)[:300], "veces": veces,
                 "estado": "para_claude", "salida": "para_claude", "causa": "", "para_claude": ""}
        try:
            d = ia.preguntar(DIAGNOSTICO.format(manual=_manual(), donde=f"el turno del canal {privado.alias(clave)}",
                                                error=privado.limpiar(error)[:500], veces=veces),
                             papel="jurado", temperatura=0.2, ligero_primero=True)
            if isinstance(d, dict) and d.get("salida") in MENU:
                parte.update(salida=d["salida"], causa=str(d.get("causa") or "")[:200],
                             para_claude=str(d.get("para_claude") or "")[:300],
                             para_el_dueno=str(d.get("para_el_dueno") or "")[:200],
                             estado={"esperar": "arreglado", "descansar_canal": "descansando",
                                     "avisar_dueno": "espera_al_dueno", "para_claude": "para_claude"}[d["salida"]])
        except gemini.SinIA:
            pass                                   # sin IA para diagnosticar: el parte va tal cual para Claude
        if parte["salida"] == "avisar_dueno":
            _avisa_una_vez(e, f"parte-{clave}", "🔧 Los mecánicos te necesitan",
                           parte.get("para_el_dueno") or "Hay un fallo que solo puedes arreglar tú. Míralo en la app.", prueba)
        e["partes"] = (e["partes"] + [parte])[-40:]
        _apunta(e, "jefe_taller", "parte nuevo", f"{privado.alias(clave)}: {parte['causa'] or 'fallo repetido'} → "
                f"{parte['salida']}", prueba)


def revisar(prueba=False, lista=None):
    e = leer()
    rondas(e, turnos() if lista is None else lista, prueba)
    desconocidos = canales(e, prueba)
    limpieza(e, prueba)
    jefe(e, desconocidos, prueba)
    e["ultimo"] = privado.ahora()
    if not prueba:
        privado.guardar_estado(ESTADO, e)
    return e


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prueba", action="store_true", help="mira y dice lo que haría, sin tocar nada")
    a = p.parse_args()
    e = revisar(a.prueba)
    print(f"taller: {len(e['arreglos'])} arreglos apuntados, {len(e['cuarentena'])} canal(es) descansando, "
          f"{sum(1 for x in e['partes'] if x.get('estado') == 'para_claude')} parte(s) para Claude", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
