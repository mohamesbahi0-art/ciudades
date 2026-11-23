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
    antes = _titulos_coliseo()
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
        titulo = antes.get((sub["canal"], sub["titulo"]), sub["titulo"])     # el del guion, si el Coliseo lo cambió
        for nombre, c in escritores.items():
            for e in reversed(c.datos["diario"]):
                if e.get("accion") == "guion" and e["detalle"].get("titulo") == titulo:
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
        votos = {}
        carpeta = os.path.join(privado.carpeta(), "estado", "juzgado", "juicios")
        for n in sorted(os.listdir(carpeta)) if os.path.isdir(carpeta) else []:
            j = privado.leer(os.path.join("estado", "juzgado", "juicios", n), {}) or {}
            if j.get("tipo") == "video" and j.get("canal") == sub["canal"] and j.get("titulo") == titulo:
                votos = {x["juez"]: x["nota"] for x in j.get("votos", [])}
                if (j.get("jurado") or {}).get("nota_media") is not None:      # el Jurado popular también juega la Liga
                    votos["Jurado popular"] = j["jurado"]["nota_media"]
        mediciones[vid] = {"canal": sub["canal"], "titulo": sub["titulo"], "titulo_guion": titulo, "horas": round(horas, 1),
                           "visitas": video["visitas"], "megusta": video.get("megusta"), "nota_juez": nota_juez,
                           "votos": votos, "escritor": quien, "medido": privado.ahora()}
        nuevas.append(vid)
    for c in escritores.values():
        c.guardar()
    privado.escribir(MEDICIONES, mediciones)
    if nuevas:
        cerebro = privado.cuaderno("cerebro")
        cerebro.apuntar("notas_reales", {"videos": len(nuevas)})
        cerebro.guardar()
    return [mediciones[v] for v in nuevas]


def _titulos_coliseo():
    """{(canal, título campeón del Coliseo): título que tenía el guion}: los vídeos se suben con el título del Coliseo,
    pero el guion, el juicio y el cuaderno del escritor guardan el de antes."""
    mapa = {}
    carpeta = os.path.join(privado.carpeta(), "estado", "coliseo", "torneos")
    for n in sorted(os.listdir(carpeta)) if os.path.isdir(carpeta) else []:
        t = privado.leer(os.path.join("estado", "coliseo", "torneos", n), {}) or {}
        nuevo = ((t.get("campeon") or {}).get("salida") or {}).get("titulo")
        if nuevo and t.get("clave") and t.get("video"):
            mapa[(t["clave"], nuevo)] = t["video"]
    return mapa


def _aciertos(pares):
    """De cada par de vídeos del mismo canal, ¿dio más nota al que tuvo más visitas?"""
    bien = total = 0
    for i, (ca, na, va) in enumerate(pares):
        for cb, nb, vb in pares[i + 1:]:
            if ca != cb or na == nb or va == vb:
                continue
            total += 1
            bien += (na > nb) == (va > vb)
    return (round(bien / total, 2) if total else None), total


def liga():
    """La Liga de los Jueces: cuánto acierta cada uno con las visitas reales. El que más acierte (con 10 comparaciones
    o más) preside el Juzgado como Juez Mayor."""
    mediciones = list((privado.leer(MEDICIONES, {}) or {}).values())
    tabla = {}
    pares = [(m["canal"], m["nota_juez"], m["visitas"]) for m in mediciones if m.get("nota_juez") is not None]
    aciertos, total = _aciertos(pares)
    tabla["juez_guardia"] = {"nombre": "Juez de guardia", "aciertos": aciertos, "comparaciones": total}
    for clave, nombre in (("gancho", "Jueza Carmen Gancho"), ("reloj", "Juez Ramón Reloj"), ("calle", "Jueza Lola Calle"),
                          ("jurado", "Jurado popular")):
        pares = [(m["canal"], m["votos"][nombre], m["visitas"]) for m in mediciones if nombre in (m.get("votos") or {})]
        aciertos, total = _aciertos(pares)
        tabla[clave] = {"nombre": nombre, "aciertos": aciertos, "comparaciones": total}
    privado.guardar_estado("juzgado/liga.json", {"jueces": tabla})
    c = privado.cuaderno("liga")
    c.apuntar("clasificacion", {k: v["aciertos"] for k, v in tabla.items()})
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
