"""La ronda de la fábrica: lo que hace GitHub cada dos horas, sin Claude y sin ningún ordenador encendido.

1. El Subidor intenta subir lo que esperaba en la cola.
2. El Organizador decide qué canales y barrios necesitan vídeo: primero los que tienen menos días de vídeos por delante
   (los vacíos antes que nadie), solo después de su último vídeo programado y nunca a más de un mes.
3. Hace un turno por cada uno (turno.py) y guarda lo hecho en el repositorio privado después de cada vídeo.

Se para sola si hoy no queda cupo de subidas y la cola ya está llena, para no hacer vídeos que no se pueden subir.

Uso:  python bots/central/fabrica.py [--prueba] [--solo gta,curios] [--maximo 2]
"""
import argparse
import datetime as dt
import os
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.central import huecos, parasubir, subidor, turno  # noqa: E402
from bots.comun import privado  # noqa: E402

SIN_HACER = {"clips": "falta la lista de creadores con permiso"}


def revisiones(cfg):
    return {k: privado.leer(os.path.join("estado", "canales", f"{k}.json"), {}) or {} for k in cfg.get("canales", {})}


def planear(ajustes, cfg, revs, solo=None, ahora=None):
    """Devuelve [(clave, hora o None, motivo)] por orden de urgencia, y lo que se queda sin hacer y por qué."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    registro = privado.leer(subidor.REGISTRO, []) or []
    cola = subidor.en_cola()
    cupo = subidor.hay_cupo(ajustes)
    cola_llena = len(cola) >= ajustes["cola_maxima"]
    orden = {k: i for i, k in enumerate(ajustes.get("prioridad", []))}
    candidatos, esperan = [], {}
    for clave, c in cfg.get("canales", {}).items():
        if solo and clave not in solo:
            continue
        if c.get("pausado"):
            esperan[clave] = "en pausa"
            continue
        if c.get("tipo") in SIN_HACER or clave in SIN_HACER:
            esperan[clave] = SIN_HACER.get(c.get("tipo"), SIN_HACER.get(clave))
            continue
        if not os.environ.get(f"YT_REFRESH_{clave.upper()}"):
            esperan[clave] = "sin permiso de YouTube"
            continue
        if not cupo and cola_llena:
            esperan[clave] = "hoy no queda cupo de subidas y la cola está llena"
            continue
        ocupadas = huecos.ocupados(revs.get(clave), registro, cola, clave)
        hora = huecos.siguiente(c["horas"], ocupadas, ahora=ahora, dias_maximos=ajustes["dias_maximos"])
        if not hora:
            esperan[clave] = f"ya tiene vídeos para {ajustes['dias_maximos']} días"
            continue
        candidatos.append((huecos.colchon(ocupadas, ahora), orden.get(clave, 99), clave, hora))
    for clave, b in cfg.get("barrios", {}).items():
        if solo and clave not in solo:
            continue
        if b.get("estado") != "activo":
            esperan[clave] = b.get("motivo") or "en pausa"
            continue
        pend = [d for d in parasubir.documentos() if d.get("barrio") == clave and d.get("estado") == "pendiente"]
        if len({d.get("titulo") for d in pend}) >= ajustes["pendientes_por_barrio"]:
            esperan[clave] = f"ya tiene {ajustes['pendientes_por_barrio']} vídeos esperando a que los subas"
            continue
        fechas = [huecos.fecha(d["cuando"]) for d in pend if d.get("cuando")]
        dias = max(0.0, (max(fechas) - ahora).total_seconds() / 86400) if fechas else 0.0
        if dias > 1.5:
            esperan[clave] = "tiene vídeos para los próximos días"
            continue
        candidatos.append((dias, orden.get(clave, 99), clave, None))
    candidatos.sort()
    return [(clave, hora) for _, _, clave, hora in candidatos], esperan


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prueba", action="store_true", help="planea y hace los vídeos, pero no sube ni guarda nada")
    p.add_argument("--solo", help="claves separadas por comas")
    p.add_argument("--maximo", type=int)
    p.add_argument("--sin-guardar", action="store_true")
    a = p.parse_args()
    inicio = time.time()
    ajustes, cfg = privado.ajustes(), privado.config()
    solo = {privado.resolver(x) for x in a.solo.split(",")} if a.solo else None
    maximo = a.maximo or ajustes["videos_por_ronda"]
    revs = revisiones(cfg)
    rondas = (privado.leer(os.path.join("estado", "fabrica.json"), {}) or {}).get("rondas", [])
    ronda = {"empezada": privado.ahora(), "prueba": a.prueba, "turnos": []}
    trabajo = tempfile.mkdtemp(prefix="fabrica-")

    def guardar(mensaje):
        if not a.prueba and not a.sin_guardar:
            privado.git_guardar(mensaje)

    if not a.prueba:
        subidos = subidor.vaciar_cola(ajustes, revs, trabajo)
        ronda["cola_subidos"] = subidos
        if subidos:
            print(f"cola: {subidos} vídeo(s) subidos", flush=True)
            guardar(f"fábrica: {subidos} vídeo(s) de la cola subidos")

    plan, esperan = planear(ajustes, cfg, revs, solo)
    ronda["plan"] = [k for k, _ in plan][:maximo]
    ronda["esperan"] = esperan
    barrios_hoy = [k for k in ronda["plan"] if k in cfg.get("barrios", {})]
    if barrios_hoy:                          # el Robot del vídeo diario prepara el vídeo de cada barrio
        diario = privado.cuaderno("robot_video_diario")
        for k in barrios_hoy:
            diario.apuntar("video_del_dia", {"barrio": k})
        diario.guardar()
    organizador = privado.cuaderno("organizador")
    organizador.apuntar("ronda", {"plan": ronda["plan"], "esperan": esperan, "prueba": a.prueba})
    organizador.guardar()
    print(privado.limpiar(f"plan: {', '.join(map(privado.alias, ronda['plan'])) or 'nada que hacer'}"), flush=True)
    for clave, motivo in esperan.items():
        print(privado.limpiar(f"  {privado.alias(clave)}: {motivo}"), flush=True)

    for clave, hora in plan[:maximo]:
        if (time.time() - inicio) / 60 > ajustes["minutos_por_ronda"]:
            print("se acaba el tiempo de la ronda: lo que falta, en la siguiente", flush=True)
            break
        args = ["--canal", clave, "--salida", trabajo] + (["--hora", huecos.iso(hora)] if hora else [])
        if a.prueba:
            args.append("--prueba")
        codigo = turno.main(args)
        estado = privado.leer(os.path.join("estado", "central", f"{clave}.json"), {}) or {}
        ultimo = estado.get("ultimo_turno", {})
        ronda["turnos"].append({"canal": clave, "codigo": codigo, "resultado": ultimo.get("resultado"),
                                "destino": ultimo.get("destino_resultado"), "error": ultimo.get("error")})
        privado.guardar_estado("fabrica.json", dict(ronda, cuota=subidor.cuota(), cola=len(subidor.en_cola()),
                                                    rondas=rondas))
        guardar(f"fábrica: turno de {clave} ({ultimo.get('destino_resultado') or ultimo.get('resultado')})")

    from bots.comun import gemini
    gemini.apuntar_portero()
    ronda["terminada"] = privado.ahora()
    resumen_ronda = {k: ronda.get(k) for k in ("empezada", "terminada", "plan", "turnos", "cola_subidos")}
    privado.guardar_estado("fabrica.json", dict(ronda, cuota=subidor.cuota(), cola=len(subidor.en_cola()),
                                                rondas=(rondas + [resumen_ronda])[-30:]))
    guardar("fábrica: fin de la ronda")
    fallos = [t for t in ronda["turnos"] if t["codigo"] != 0]
    return 1 if ronda["turnos"] and len(fallos) == len(ronda["turnos"]) else 0


if __name__ == "__main__":
    sys.exit(main())
