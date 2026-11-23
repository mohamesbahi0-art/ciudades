"""El Cerebro, el Detector de virales y la Liga de los Jueces: aprenden de las visitas de verdad.

- Cerebro: a las 48-96 horas de publicarse cada vídeo nuestro, mira sus visitas (de la revisión de los Jefes de canal) y
  le pone la nota real al guion en el cuaderno de quien lo escribió. Así cada robot sabe qué le salió bien y qué no.
- Liga: compara lo que dijo el Juez de guardia con las visitas reales y calcula cuánto acierta (de 0 a 1).
- Detector de virales: avisa cuando un vídeo de las últimas 72 horas va mucho más rápido de lo normal en su canal.

No gasta cuota de YouTube: usa estado/canales/*.json, registro/subidas.json y los cuadernos.
"""
import datetime as dt
import os
import statistics

from bots.central import huecos
from bots.comun import privado

ESCRITORES = ("escritor", "guionista", "archivero_mapas")
MEDICIONES = os.path.join("estado", "juzgado", "mediciones.json")


def _horas(desde, ahora):
    return (ahora - huecos.fecha(desde)).total_seconds() / 3600


def medir(ahora=None):
    """Cerebro: nota real (visitas a las 48-96 h) para cada vídeo nuestro publicado. Devuelve las mediciones nuevas."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    registro = privado.leer(os.path.join("registro", "subidas.json"), []) or []
    mediciones = privado.leer(MEDICIONES, {}) or {}
    escritores = {r: privado.cuaderno(r) for r in ESCRITORES}
    juez = privado.cuaderno("juez_guardia")
    nuevas = []
    for sub in registro:
        vid = sub.get("id")
        if not vid or vid in mediciones:
            continue
        revision = privado.leer(os.path.join("estado", "canales", f"{sub['canal']}.json"), {}) or {}
        video = next((v for v in revision.get("recientes", []) if v["id"] == vid), None)
        if not video:
            continue
        horas = _horas(video["publicado"], ahora)
        if not 48 <= horas <= 96:
            continue
        id_guion, nota_juez, quien = None, None, None
        for nombre, c in escritores.items():
            for e in reversed(c.datos["diario"]):
                if e.get("accion") == "guion" and e["detalle"].get("titulo") == sub["titulo"]:
                    id_guion, quien = e["id"], nombre
                    break
            if id_guion:
                break
        if id_guion:
            for e in reversed(juez.datos["diario"]):
                if e.get("accion") == "juicio" and e["detalle"].get("guion") == id_guion:
                    nota_juez = e["detalle"].get("total")
                    break
            por_hora = round(video["visitas"] / horas, 2)
            escritores[quien].nota(id_guion, por_hora, "visitas por hora a las 48-96 h",
                                   f"{video['visitas']} visitas y {video.get('megusta', 0)} me gusta en {round(horas)} h")
        mediciones[vid] = {"canal": sub["canal"], "titulo": sub["titulo"], "horas": round(horas, 1),
                           "visitas": video["visitas"], "megusta": video.get("megusta"), "nota_juez": nota_juez,
                           "escritor": quien, "medido": privado.ahora()}
        nuevas.append(vid)
    for c in escritores.values():
        c.guardar()
    privado.escribir(MEDICIONES, mediciones)
    if nuevas:
        cerebro = privado.cuaderno("cerebro")
        cerebro.apuntar("notas_reales", {"videos": len(nuevas)})
        cerebro.guardar()
    return [mediciones[v] for v in nuevas]


def liga():
    """Cuánto acierta cada juez: de cada par de vídeos del mismo canal, ¿puso más nota al que tuvo más visitas?"""
    mediciones = [m for m in (privado.leer(MEDICIONES, {}) or {}).values() if m.get("nota_juez") is not None]
    bien = total = 0
    for i, a in enumerate(mediciones):
        for b in mediciones[i + 1:]:
            if a["canal"] != b["canal"] or a["nota_juez"] == b["nota_juez"] or a["visitas"] == b["visitas"]:
                continue
            total += 1
            bien += (a["nota_juez"] > b["nota_juez"]) == (a["visitas"] > b["visitas"])
    tabla = {"juez_guardia": {"nombre": "Juez de guardia", "aciertos": round(bien / total, 2) if total else None,
                              "comparaciones": total}}
    privado.guardar_estado("juzgado/liga.json", {"jueces": tabla})
    if total:
        c = privado.cuaderno("liga")
        c.apuntar("clasificacion", tabla)
        c.guardar()
    return tabla


def virales(ahora=None, veces=3.0):
    """Detector de virales: vídeos de menos de 72 h que van al triple (o más) de lo normal en su canal."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    cfg = privado.config()
    alertas = []
    for clave in cfg.get("canales", {}):
        revision = privado.leer(os.path.join("estado", "canales", f"{clave}.json"), {}) or {}
        recientes = [v for v in revision.get("recientes", []) if _horas(v["publicado"], ahora) >= 1]
        ritmos = [v["visitas"] / _horas(v["publicado"], ahora) for v in recientes]
        if len(ritmos) < 5:
            continue
        normal = statistics.median(ritmos) or 0.1
        for v, ritmo in zip(recientes, ritmos):
            if _horas(v["publicado"], ahora) <= 72 and ritmo >= veces * normal and v["visitas"] >= 100:
                alertas.append({"canal": clave, "titulo": v["titulo"], "url": v["url"], "visitas": v["visitas"],
                                "por_hora": round(ritmo, 1), "veces_lo_normal": round(ritmo / normal, 1)})
    privado.guardar_estado("analisis/virales.json", {"alertas": alertas})
    detector = privado.cuaderno("detector_virales")
    detector.apuntar("repaso", {"alertas": len(alertas)})
    detector.guardar()
    return alertas
