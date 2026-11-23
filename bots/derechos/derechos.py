"""Derechos Sociales: la quinta ciudad, la que cuida de los robots (la pidió el dueño el 23 nov). Una vez al día:

- Doctora: mira la salud de cada robot en su cuaderno y en el Archivo de casos: cuánto ha trabajado esta semana, cuántas
  veces ha fallado, si trabaja demasiado o lleva días sin hacer nada. Salud buena, regular o mala.
- Equipo de mejora (Rosa Repaso, Tomás Tornillo y Luz Lección): junta los fallos que se repiten, propone el arreglo
  (para Claude, el «fabrica 2.0», o para el dueño) y convierte lo aprendido en una lección para ese robot.
- Defensora: escucha lo que necesita cada robot (una llave, un permiso, una lista…) y lo pide por él.
- Guía de los nuevos: a cada robot nuevo le pasa las mejores lecciones de sus compañeros de ciudad, una sola vez.
- Psicóloga: a los robots que van de caída les deja una nota con lo que sí hicieron bien y un paso concreto, y avisa al
  Jefe si la mala racha sigue (estilo de la skill «psicologo-robots»).
- Jefe de Derechos Sociales: lee la línea directa (estado/derechos/sos.json, si la ronda de Claude la ha traído de la app),
  lo de todos y decide lo de hoy: qué va a Claude, qué al dueño y qué ya está hecho.

No usa IA (no gasta cupo) ni toca el código: escribe estado/derechos/*.json (lo copia a la app la ronda de Claude) y
los cuadernos. Uso:  python bots/derechos/derechos.py
"""
import collections
import datetime as dt
import glob
import json
import os
import statistics
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import privado  # noqa: E402

CARPETA = "derechos"                      # dentro de estado/
ROBOTS_CIUDAD = ("doctora_robots", "equipo_mejora", "defensora_robots", "guia_nuevos", "psicologa_robots", "jefe_derechos")
# Robots que no tienen por qué trabajar a diario (no es mala salud que lleven días sin hacer nada)
TRANQUILOS = {"constructor_canales", "presentador_directos", "animador_hipnotico", "cartografo", "archivero_mapas",
              "dibujante_mapas", "vigilante_permisos", "buscador_clips"}
ARREGLOS = {
    "SinIA": ("La IA gratis se acaba y el robot se queda parado.",
              "Con la llave de Claude escribirá igualmente; mientras, que espere al turno siguiente sin insistir.", "dueno"),
    "TimeoutError": ("Una conexión tarda demasiado y corta el trabajo.",
                     "Repetir una vez más con más tiempo de espera antes de darlo por fallido.", "claude"),
    "URLError": ("Se queda sin conexión con un servicio.", "Repetir más tarde y avisar si pasa tres veces seguidas.", "claude"),
    "maquinas": ("Un turno automático no pasa a su hora o falla.", "Revisar el horario y el último registro del turno.",
                 "claude"),
    "gemini": ("La IA gratis se ha gastado.", "Repartir mejor el cupo entre robots y usar el cerebro de pago para escribir.",
               "dueno"),
}


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _fecha(texto):
    try:
        return dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None


def robots():
    """Los robots del manifiesto (id, nombre, ciudad) y los que tienen cuaderno aunque no estén en él."""
    m = privado.leer("manifiesto.json", {}) or {}
    lista = {b["id"]: {"id": b["id"], "nombre": b.get("nombre", b["id"]), "ciudad": b.get("ciudad"), "hace": b.get("hace")}
             for b in m.get("bots", []) if b.get("tipo", "bot") == "bot"}
    for ruta in glob.glob(os.path.join(privado.carpeta(), "memoria", "*.json")):
        rid = os.path.basename(ruta)[:-5]
        lista.setdefault(rid, {"id": rid, "nombre": rid.replace("_", " ").capitalize(), "ciudad": None, "hace": None})
    return lista


def cuaderno_de(rid):
    return privado.leer(os.path.join("memoria", f"{rid}.json"), None)


def _tipo_caso(clave):
    partes = str(clave).split(":")
    if partes[0] == "turno" and len(partes) >= 3:
        return partes[2]
    return partes[0]


def doctora(lista, casos, hace7, hace3):
    salud = {}
    for rid, r in lista.items():
        c = cuaderno_de(rid)
        diario = (c or {}).get("diario") or []
        semana = [e for e in diario if (_fecha(e.get("fecha")) or hace7) > hace7]
        errores = [e for e in semana if e.get("accion") == "error"]
        mios = [x for x in casos if x.get("robot") == rid and ((_fecha(x.get("fecha")) or hace7) > hace7
                                                             or x.get("estado") != "arreglado")]
        abiertos = [x for x in mios if x.get("estado") != "arreglado"]
        ultima = max((e.get("fecha") for e in diario if e.get("fecha")), default=None)
        reciente = ultima and (_fecha(ultima) or hace7) > hace3
        fallos = len(errores) + len(mios)
        if c is None or not diario:
            estado = "sin_datos"
        elif fallos >= 3 or len(abiertos) >= 2:
            estado = "mala"
        elif fallos or (not reciente and rid not in TRANQUILOS):
            estado = "regular"
        else:
            estado = "buena"
        tipos = collections.Counter(_tipo_caso(x.get("clave")) for x in mios)
        tipos.update(str((e.get("detalle") or {}).get("error") or "error").split(":")[0][:30] for e in errores)
        salud[rid] = {"nombre": r["nombre"], "ciudad": r["ciudad"], "salud": estado, "trabajo_7d": len(semana) - len(errores),
                      "fallos_7d": fallos, "casos_abiertos": len(abiertos), "ultima": ultima,
                      "fallos_por_tipo": dict(tipos.most_common(4))}
    activos = [s["trabajo_7d"] for s in salud.values() if s["trabajo_7d"] > 0]
    mucho = (statistics.median(activos) * 3) if len(activos) >= 5 else None
    for rid, s in salud.items():
        if mucho and s["trabajo_7d"] > mucho:
            s["carga"] = "mucha"
        elif s["trabajo_7d"] == 0 and s["salud"] != "sin_datos" and rid not in TRANQUILOS:
            s["carga"] = "ninguna"
        else:
            s["carga"] = "normal"
        s["nota"] = (f"Esta semana ha trabajado {s['trabajo_7d']} veces y ha fallado {s['fallos_7d']}"
                     + (f" (sobre todo: {', '.join(s['fallos_por_tipo'])})" if s["fallos_por_tipo"] else "") + ".")
    return salud


def equipo_mejora(salud):
    """Fallos que se repiten → propuesta de arreglo y una lección para ese robot (una sola vez)."""
    propuestas = []
    for rid, s in salud.items():
        for tipo, veces in s["fallos_por_tipo"].items():
            if veces < 2:
                continue
            problema, arreglo, para = ARREGLOS.get(tipo, (f"Falla una y otra vez ({tipo}).",
                                                          "Mirar el registro del fallo y corregir la causa.", "claude"))
            propuestas.append({"robot": rid, "nombre": s["nombre"], "tipo": tipo, "veces": veces, "problema": problema,
                               "arreglo": arreglo, "para": para})
            c = privado.cuaderno(rid)
            c.aprender(f"Fallo que se repite ({tipo}): {problema} Qué hacer: {arreglo}", pruebas=["equipo de mejora"],
                       confianza=0.4)
            c.guardar()
    return propuestas


def defensora(salud, casos):
    """Lo que necesita cada robot y solo puede dar otro (sobre todo el dueño)."""
    peticiones = []
    claude = privado.leer(os.path.join("estado", "claude.json"), {}) or {}
    sin_ia = [rid for rid, s in salud.items() if s["fallos_por_tipo"].get("SinIA") or s["fallos_por_tipo"].get("gemini")]
    if sin_ia and not (claude.get("prueba") or {}).get("bien"):
        peticiones.append({"robots": sin_ia[:8], "pide": "La llave de Claude, para no quedarse parados cuando se acaba la "
                           "IA gratis.", "a_quien": "dueno", "aviso": "pc-claude-llave"})
    for c in casos:
        if c.get("estado") == "necesita_al_dueno":
            peticiones.append({"robots": [c.get("robot")], "pide": c.get("problema"), "a_quien": "dueno",
                               "caso": c.get("id")})
    fabrica = privado.leer(os.path.join("estado", "fabrica.json"), {}) or {}
    for clave, motivo in (fabrica.get("esperan") or {}).items():
        if "lista de creadores" in str(motivo):
            peticiones.append({"robots": ["buscador_clips"], "pide": "La lista de creadores que han dado permiso, para "
                               "encender el canal de clips.", "a_quien": "dueno", "aviso": "pc-lista-creadores"})
    fuentes = (privado.leer(os.path.join("estado", "influencers", "ojeador", "tendencias.json"), {}) or {}).get("fuentes") or {}
    cerradas = [k for k, f in fuentes.items() if f.get("estado") == "bloqueada"]
    if cerradas:
        peticiones.append({"robots": ["ojeador_redes"], "pide": "Paciencia: " + ", ".join(cerradas) + " no le deja mirar "
                           "ahora. Lo vuelve a intentar solo, sin saltarse nada.", "a_quien": "nadie"})
    return peticiones


def guia(lista, salud, hace7):
    """A cada robot nuevo (cuaderno de esta semana o casi vacío) le pasa las mejores lecciones de su ciudad, una vez."""
    hechos = privado.leer(os.path.join("estado", CARPETA, "guia.json"), {}) or {}
    primera = not hechos                     # la primera vez, los que ya llevan días trabajando no son nuevos
    bienvenidos = hechos.get("robots") or {}
    nuevos = []
    for rid, r in lista.items():
        if rid in bienvenidos or rid in ROBOTS_CIUDAD:
            continue
        c = cuaderno_de(rid)
        if c is None:
            continue
        entradas = len(c.get("diario") or [])
        if primera and entradas >= 5:
            bienvenidos[rid] = "ya estaba"
            continue
        creado = _fecha(c.get("creado"))
        if not ((creado and creado > hace7) or entradas < 3):
            continue
        compas = [x for x, y in lista.items() if y["ciudad"] == r["ciudad"] and x != rid and cuaderno_de(x)]
        lecciones = []
        for x in compas:
            for leccion in (cuaderno_de(x) or {}).get("lecciones", []):
                lecciones.append((leccion.get("del_dueno", False), leccion.get("confianza", 0), leccion["texto"], x))
        lecciones.sort(reverse=True)
        mio = privado.cuaderno(rid)
        pasadas = []
        for del_dueno, confianza, texto, de in lecciones[:3]:
            mio.aprender(texto, pruebas=[f"guía de los nuevos (de {de})"], confianza=min(0.5, confianza),
                         del_dueno=del_dueno)
            pasadas.append({"de": de, "texto": texto[:160]})
        mio.apuntar("bienvenida", {"lecciones": len(pasadas)})
        mio.guardar()
        bienvenidos[rid] = privado.ahora()
        nuevos.append({"robot": rid, "nombre": r["nombre"], "lecciones": pasadas})
    privado.guardar_estado(os.path.join(CARPETA, "guia.json"), {"robots": bienvenidos})
    return nuevos


def psicologa(salud, propuestas, anteriores):
    notas = []
    for rid, s in salud.items():
        if s["salud"] != "mala":
            continue
        paso = next((p["arreglo"] for p in propuestas if p["robot"] == rid), "Hacer una sola cosa bien en el próximo turno.")
        racha = int((anteriores.get(rid) or {}).get("racha", 0)) + 1
        notas.append({"robot": rid, "nombre": s["nombre"], "racha": racha,
                      "bien": (f"Esta semana sacó adelante {s['trabajo_7d']} trabajos: eso no lo borra un mal día."
                               if s["trabajo_7d"] else "Sigue en su puesto y lo intenta en cada turno."),
                      "paso": paso, "avisar_jefe": racha >= 3})
        c = privado.cuaderno(rid)
        c.apuntar("nota_psicologa", {"bien": notas[-1]["bien"], "paso": paso})
        c.guardar()
    return notas


def jefe(peticiones, propuestas, notas, sos):
    """Decide lo de hoy: la línea directa primero, luego lo que bloquea a más robots."""
    decisiones = []
    for m in (sos.get("mensajes") or [])[:5]:
        if not m.get("respondido"):
            decisiones.append({"que": f"Línea directa: {str(m.get('texto'))[:160]}", "para": "claude",
                               "por_que": "Lo primero es la línea directa."})
    for p in sorted(peticiones, key=lambda x: len(x.get("robots") or []), reverse=True):
        if p["a_quien"] == "dueno":
            decisiones.append({"que": p["pide"], "para": "dueno", "por_que": f"Lo necesitan {len(p.get('robots') or [])} "
                               "robots y solo lo puede dar el dueño.", "aviso": p.get("aviso")})
    for p in propuestas:
        if p["para"] == "claude":
            decisiones.append({"que": f"{p['nombre']}: {p['problema']} {p['arreglo']}", "para": "claude",
                               "por_que": f"Ha pasado {p['veces']} veces esta semana."})
    for n in notas:
        if n["avisar_jefe"]:
            decisiones.append({"que": f"{n['nombre']} lleva {n['racha']} días de mala racha: revisar su trabajo.",
                               "para": "claude", "por_que": "Aviso de la Psicóloga."})
    vistas, unicas = set(), []
    for d in decisiones:
        if d["que"] not in vistas:
            vistas.add(d["que"])
            unicas.append(d)
    return unicas[:8]


def main():
    ahora = _ahora()
    hace7, hace3 = ahora - dt.timedelta(days=7), ahora - dt.timedelta(days=3)
    lista = robots()
    casos = (privado.leer(os.path.join("estado", "casos.json"), {}) or {}).get("casos") or []
    anteriores = (privado.leer(os.path.join("estado", CARPETA, "psicologa.json"), {}) or {}).get("notas_por_robot") or {}
    salud = doctora(lista, casos, hace7, hace3)
    propuestas = equipo_mejora(salud)
    peticiones = defensora(salud, casos)
    nuevos = guia(lista, salud, hace7)
    notas = psicologa(salud, propuestas, anteriores)
    sos = privado.leer(os.path.join("estado", CARPETA, "sos.json"), {}) or {}
    decisiones = jefe(peticiones, propuestas, notas, sos)
    cuenta = collections.Counter(s["salud"] for s in salud.values())
    privado.guardar_estado(os.path.join(CARPETA, "salud.json"), {"robots": salud, "resumen": dict(cuenta)})
    privado.guardar_estado(os.path.join(CARPETA, "mejoras.json"), {"propuestas": propuestas})
    privado.guardar_estado(os.path.join(CARPETA, "peticiones.json"), {"peticiones": peticiones})
    privado.guardar_estado(os.path.join(CARPETA, "bienvenidas.json"), {"nuevos": nuevos})
    privado.guardar_estado(os.path.join(CARPETA, "psicologa.json"), {"notas": notas,
                                                                     "notas_por_robot": {n["robot"]: n for n in notas}})
    privado.guardar_estado(os.path.join(CARPETA, "jefe.json"), {"decisiones": decisiones})
    for rid, que in (("doctora_robots", {"robots": len(salud), "salud": dict(cuenta)}),
                     ("equipo_mejora", {"propuestas": len(propuestas)}), ("defensora_robots", {"peticiones": len(peticiones)}),
                     ("guia_nuevos", {"bienvenidas": len(nuevos)}), ("psicologa_robots", {"notas": len(notas)}),
                     ("jefe_derechos", {"decisiones": len(decisiones)})):
        c = privado.cuaderno(rid)
        c.apuntar("ronda", que)
        c.guardar()
    print(f"derechos sociales: {len(salud)} robots revisados ({dict(cuenta)}), {len(propuestas)} mejoras, "
          f"{len(peticiones)} peticiones, {len(nuevos)} bienvenidas, {len(notas)} notas, {len(decisiones)} decisiones")
    return 0


if __name__ == "__main__":
    sys.exit(main())
