"""La Élite: los tres mandamases de las ciudades (lo pidió el dueño). Cada 2 horas lo miran TODO desde arriba, leyendo los
partes de la Policía, los Mecánicos, Derechos Sociales, el Juzgado y el Cine, y solo se meten cuando algo falla una y otra
vez, la culpa es de un robot o hace falta un sistema nuevo. Los arreglos pequeños son de los Mecánicos.

- El Espía (`elite_espia`): vigila los fallos de todos los robots y saca los que se repiten.
- La Estratega (`elite_estratega`): vigila la calidad y los resultados de cada cuenta (notas del Juzgado, lo que se va el
  público del Cine y lo que el dueño descarta) y saca los formatos que no llegan.
- El Arquitecto (`elite_arquitecto`): decide y ejecuta lo gordo. Lo que puede hacer él solo, y siempre se puede deshacer:
  enseñar una lección nueva al robot culpable (su cuaderno) y mandar a reforma a una cuenta que gasta IA sin acercarse
  a la nota. Lo que pide código nuevo (cambiar un robot por otro, un sistema nuevo) lo deja como «obra» para Claude, con
  el porqué y las pruebas: los robots de GitHub no reescriben programas solos.
Nunca tocan las lecciones del dueño, las claves ni los permisos. Solo piensan con la IA (la pequeña, una pregunta) cuando
hay algo nuevo que decidir. Cada uno tiene su cuaderno. Todo queda en estado/elite/elite.json (privado).

Uso:  python bots/elite/elite.py [--prueba]
"""
import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import ia, privado  # noqa: E402

ESTADO = os.path.join("estado", "elite", "elite.json")
HORAS = 24                 # lo que miran hacia atrás
MIN_JUICIOS = 5            # juicios de una cuenta antes de opinar de su formato
LEJOS = 78                 # si la mejor nota no pasa de aquí, el formato no llega
REFORMA_HORAS = 12         # lo que descansa una cuenta mandada a reforma (se deshace borrándola de «reformas»)
FALLOS_REPETIDOS = 4       # veces que un robot falla igual en un día para que sea cosa de la Élite

DECIDIR = """Eres el Arquitecto de la Élite de una fábrica de vídeos cortos (YouTube Shorts, TikTok e Instagram). Estos son
los problemas que se repiten, con sus pruebas. Para cada uno decide UNA salida:
- "leccion": escribe una lección concreta y práctica (1-2 frases, en español) para el robot que la necesita, que corrija
  la causa. Robots: guionista (cuentas de TikTok/Instagram), escritor (canales de YouTube), juez_guardia.
- "reforma": la cuenta gasta IA sin acercarse a la nota y una lección no basta: descansa unas horas.
- "obra": hace falta código nuevo (cambiar un robot por otro, un formato nuevo, un sistema nuevo). Explica qué habría que
  construir, en 2-3 frases, para que lo haga un programador.
- "nada": no hay pruebas bastantes.
Problemas:
{problemas}
Devuelve SOLO un JSON: {{"decisiones": [{{"id": "el id del problema", "salida": "leccion|reforma|obra|nada",
"robot": "a quién va la lección", "texto": "la lección o la obra", "porque": "una frase con la prueba"}}]}}"""


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _fecha(t):
    try:
        return dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def leer():
    e = privado.leer(ESTADO, {}) or {}
    for k, v in (("reformas", {}), ("obras", []), ("decisiones", []), ("vistos", {})):
        e.setdefault(k, v)
    return e


def en_reforma(clave, estado=None, ahora=None):
    """El motivo si la Élite tiene la cuenta en reforma (lo respeta la fábrica al planear); None si puede trabajar."""
    r = ((estado or leer()).get("reformas") or {}).get(clave)
    if r and (_fecha(r.get("hasta")) or _ahora()) > (ahora or _ahora()):
        return r.get("motivo") or "en reforma por orden de la Élite"
    return None


def espia(desde):
    """Los fallos que se repiten: [{id, tipo: "robot", robot, canal, veces, pruebas}]."""
    cuenta = {}
    for ruta in glob.glob(os.path.join(privado.carpeta(), "estado", "central", "*.json")):
        d = privado.leer(os.path.relpath(ruta, privado.carpeta()), {}) or {}
        for t in d.get("turnos") or []:
            f = _fecha(t.get("terminado"))
            err = str(t.get("error") or "")
            if t.get("resultado") != "error" or not f or f < desde or err.startswith("SinIA") or "dibujos" in err:
                continue
            k = (t.get("robot") or "fabrica", t.get("canal"), err.split(":")[0][:40])
            cuenta.setdefault(k, []).append(err[:160])
    partes = [p for p in (privado.leer(os.path.join("estado", "mecanicos", "taller.json"), {}) or {}).get("partes") or []
              if p.get("estado") == "para_claude"]
    salida = [{"id": f"robot-{r}-{privado.alias(c or '')}-{e}".replace(" ", "_"), "tipo": "robot", "robot": r,
               "canal": privado.alias(c or ""), "veces": len(v), "pruebas": v[-2:]}
              for (r, c, e), v in cuenta.items() if len(v) >= FALLOS_REPETIDOS]
    salida += [{"id": f"parte-{p.get('id') or p.get('fecha')}", "tipo": "parte", "robot": "mecanicos",
                "canal": privado.alias(p.get("canal") or ""), "veces": 1, "pruebas": [str(p.get("causa"))[:200]]}
               for p in partes[-3:]]
    return salida


def estratega(desde):
    """Los formatos que no llegan y lo que el dueño descarta: [{id, tipo, canal, pruebas…}]."""
    por = {}
    patron = os.path.join(privado.carpeta(), "estado", "juzgado", "juicios", "*.json")
    for ruta in sorted(glob.glob(patron))[-400:]:
        if ruta.endswith(("-idea.json", "-jurado.json")):
            continue
        j = privado.leer(os.path.relpath(ruta, privado.carpeta()), {}) or {}
        f = _fecha(j.get("fecha"))
        if j.get("tipo") == "video" and f and f >= desde and isinstance(j.get("nota"), (int, float)) and not j.get("prueba"):
            por.setdefault(j.get("canal"), []).append(j)
    salida = []
    for clave, js in por.items():
        notas = [j["nota"] for j in js]
        if len(js) >= MIN_JUICIOS and max(notas) < LEJOS:
            peores = sorted(js, key=lambda j: j["nota"])[:2]
            salida.append({"id": f"formato-{privado.alias(clave)}-{_ahora().strftime('%Y%m%d')}", "tipo": "formato",
                           "canal": privado.alias(clave), "clave": clave, "juicios": len(js), "mejor": max(notas),
                           "media": round(sum(notas) / len(notas)),
                           "pruebas": [str(j.get("consejo") or "")[:220] for j in peores] +
                                      [str((j.get("publico_resumen") or ""))[:200] for j in js[-1:] if j.get("publico_resumen")]})
    for clave in list((privado.config().get("barrios") or {})):
        tirados = privado.descartes(clave, 4) if hasattr(privado, "descartes") else ""
        if tirados.count("\n") >= 1:                       # dos o más descartes del dueño: su gusto manda
            salida.append({"id": f"descartes-{privado.alias(clave)}-{hashlib.md5(tirados.encode()).hexdigest()[:6]}",
                           "tipo": "descartes", "canal": privado.alias(clave), "clave": clave, "pruebas": [tirados[:500]]})
    return salida


def arquitecto(problemas, e, prueba=False):
    """Decide y ejecuta. Devuelve las decisiones tomadas ahora."""
    nuevos = [p for p in problemas if p["id"] not in e["vistos"]]
    if not nuevos:
        return []
    try:
        r = ia.preguntar(DECIDIR.format(problemas=json.dumps(
            [{k: v for k, v in p.items() if k != "clave"} for p in nuevos], ensure_ascii=False)[:6000]),
            papel="jurado", ligero_primero=True, temperatura=0.4)
        decisiones = r.get("decisiones") if isinstance(r, dict) else []
    except Exception:
        decisiones = None
    ahora = privado.ahora()
    hechas = []
    for p in nuevos:
        d = next((x for x in decisiones or [] if isinstance(x, dict) and x.get("id") == p["id"]), None)
        if decisiones is None:                       # sin IA: lo deja para la próxima ronda (no lo marca como visto)
            continue
        salida = (d or {}).get("salida") or "nada"
        texto = str((d or {}).get("texto") or "")[:500]
        apunte = {"id": p["id"], "fecha": ahora, "problema": p, "salida": salida, "texto": texto,
                  "porque": str((d or {}).get("porque") or "")[:300]}
        clave = p.get("clave")
        if salida == "leccion" and texto and not prueba:
            robot = d.get("robot") if d.get("robot") in ("guionista", "escritor", "juez_guardia") else \
                ("guionista" if clave in (privado.config().get("barrios") or {}) else "escritor")
            c = privado.cuaderno(robot)
            c.aprender(f"(Élite, {p.get('canal') or 'todas'}) {texto}", confianza=0.7)     # nunca como lección del dueño
            c.guardar()
            apunte.update(robot=robot, deshacer=f"borrar esa lección del cuaderno de {robot}")
        elif salida == "reforma" and clave and p["tipo"] == "formato" and not prueba:
            hasta = (_ahora() + dt.timedelta(hours=REFORMA_HORAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
            e["reformas"][clave] = {"hasta": hasta, "desde": ahora,
                                    "motivo": f"en reforma por la Élite: {p['juicios']} vídeos juzgados y el mejor se queda "
                                              f"en {p['mejor']}; descansa mientras se arregla su formato"}
            e["obras"].append({"id": p["id"], "fecha": ahora, "estado": "para_claude", "canal": p.get("canal"),
                               "que": texto or "rehacer el formato de esta cuenta", "pruebas": p.get("pruebas")})
            apunte.update(deshacer="borrar la cuenta de «reformas» en estado/elite/elite.json")
        elif salida == "obra" and not prueba:
            e["obras"].append({"id": p["id"], "fecha": ahora, "estado": "para_claude", "canal": p.get("canal"),
                               "que": texto, "pruebas": p.get("pruebas")})
        e["vistos"][p["id"]] = ahora
        hechas.append(apunte)
    return hechas


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prueba", action="store_true")
    a = p.parse_args(argv)
    desde = _ahora() - dt.timedelta(hours=HORAS)
    e = leer()
    fallos, calidad = espia(desde), estratega(desde)
    hechas = arquitecto(fallos + calidad, e, a.prueba)
    e["decisiones"] = (e["decisiones"] + hechas)[-60:]
    e["obras"] = e["obras"][-40:]
    limite = (_ahora() - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    e["vistos"] = {k: v for k, v in e["vistos"].items() if v >= limite}
    e.update(ultimo=privado.ahora(), mirado={"fallos": len(fallos), "calidad": len(calidad)})
    if not a.prueba:
        privado.escribir(ESTADO, e)
        for robot, que, dato in (("elite_espia", "vigilancia", {"fallos_repetidos": len(fallos)}),
                                 ("elite_estratega", "repaso", {"cuentas_con_problema": len(calidad)}),
                                 ("elite_arquitecto", "decisiones", {"tomadas": len(hechas),
                                                                     "salidas": [h["salida"] for h in hechas]})):
            c = privado.cuaderno(robot)
            c.apuntar(que, dato)
            c.guardar()
    print(f"élite: {len(fallos)} fallos repetidos, {len(calidad)} cuentas con problema de calidad, {len(hechas)} decisiones "
          f"({', '.join(h['salida'] for h in hechas) or 'ninguna nueva'})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
