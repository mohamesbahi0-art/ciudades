"""El estudio de los Influencers: miran qué se hace viral y escriben las recetas que siguen los Escritores.

Cada día (gasta unas 220 unidades de cuota de YouTube, de 10.000):
- Buscador de tendencias: lo más visto hoy en España (videojuegos y entretenimiento), 1 unidad por lista.
- Cazador de virales e Investigador: los Shorts que más visitas han hecho esta semana en el tema de 2 canales (van
  rotando), con la búsqueda oficial (100 unidades cada una).
- Experto SEO: lo que la gente escribe en el buscador de YouTube sobre cada tema (autocompletar, gratis).
- Analistas de vídeos: miran las portadas y los títulos de los virales y sacan qué tienen en común (Gemini).
- Recetario: escribe la receta de cada canal (título, gancho, duración, final, palabras clave). El Escritor la lee.
- Espía de la competencia: los canales que más aparecen en los virales, cada cuánto suben y cuánto hacen.
Cada lunes, además:
- Estratega de crecimiento: plan de la semana (cuánto publicar, series, qué probar).
- Exploradora de temas: qué temas nuevos podrían funcionar para un canal nuevo.

Todo va al repositorio privado (estado/influencers/) y a los cuadernos de cada robot.
Uso:  python bots/influencers/estudio.py [--semanal]
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.central import buscador_clips  # noqa: E402
from bots.comun import gemini, privado  # noqa: E402

AGENTE = {"User-Agent": "ciudades-influencers/1.0"}
CARPETA = os.path.join("estado", "influencers")


def _apuntar(robot, accion, detalle):
    c = privado.cuaderno(robot)
    c.apuntar(accion, detalle)
    c.guardar()


def _segundos(iso):
    return buscador_clips.segundos(iso)


def temas():
    """Qué buscar para cada canal y barrio activos (de config: "busqueda", si no, su tema)."""
    cfg = privado.config()
    salida = {}
    for clave, c in list(cfg.get("canales", {}).items()) + list(cfg.get("barrios", {}).items()):
        if c.get("pausado") or c.get("estado") in ("en_pausa", "por_confirmar"):
            continue
        salida[clave] = {"q": c.get("busqueda") or (c.get("tema") or c.get("nombre", clave))[:60],
                         "idioma": c.get("idioma", "es")[:2], "nombre": c.get("nombre", clave)}
    return salida


def tendencias(yt):
    lista = []
    for categoria in ("20", "24"):
        r = yt.videos().list(part="snippet,statistics,contentDetails", chart="mostPopular", regionCode="ES",
                             videoCategoryId=categoria, maxResults=25).execute()
        for v in r.get("items", []):
            lista.append({"id": v["id"], "titulo": v["snippet"]["title"], "canal": v["snippet"]["channelTitle"],
                          "visitas": int(v["statistics"].get("viewCount", 0)),
                          "segundos": _segundos(v["contentDetails"]["duration"]), "categoria": categoria})
    privado.guardar_estado("influencers/tendencias.json", {"lista": lista})
    _apuntar("buscador_tendencias", "tendencias", {"videos": len(lista)})
    return lista


def virales(yt, clave, tema):
    desde = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = yt.search().list(part="id", q=tema["q"], type="video", videoDuration="short", order="viewCount",
                         publishedAfter=desde, relevanceLanguage=tema["idioma"], maxResults=15).execute()
    ids = [x["id"]["videoId"] for x in r.get("items", [])]
    lista = []
    if ids:
        r = yt.videos().list(id=",".join(ids), part="snippet,statistics,contentDetails").execute()
        for v in r.get("items", []):
            lista.append({"id": v["id"], "titulo": v["snippet"]["title"], "canal": v["snippet"]["channelTitle"],
                          "canal_id": v["snippet"]["channelId"], "visitas": int(v["statistics"].get("viewCount", 0)),
                          "megusta": int(v["statistics"].get("likeCount", 0)),
                          "segundos": _segundos(v["contentDetails"]["duration"]),
                          "publicado": v["snippet"]["publishedAt"]})
    lista.sort(key=lambda v: v["visitas"], reverse=True)
    privado.guardar_estado(f"influencers/virales/{clave}.json", {"tema": tema["q"], "lista": lista})
    _apuntar("cazador_virales", "virales", {"canal": clave, "videos": len(lista)})
    _apuntar("investigador", "tema", {"canal": clave, "busqueda": tema["q"],
                                      "mejor": lista[0]["visitas"] if lista else 0})
    return lista


def palabras_clave(clave, tema):
    gl = {"es": "ES", "nl": "NL"}.get(tema["idioma"], "ES")
    url = (f"https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&hl={tema['idioma']}&gl={gl}"
           f"&q={urllib.parse.quote(tema['q'][:40])}")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=15) as r:
            datos = json.loads(r.read().decode("utf-8", "ignore"))
        sugerencias = [s for s in datos[1]][:10]
    except Exception:
        sugerencias = []
    _apuntar("experto_seo", "palabras", {"canal": clave, "cuantas": len(sugerencias)})
    return sugerencias


def _portada(vid, carpeta):
    ruta = os.path.join(carpeta, f"{vid}.jpg")
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                                                           headers=AGENTE), timeout=20) as r, open(ruta, "wb") as f:
            f.write(r.read())
        return ruta
    except Exception:
        return None


ANALISIS = """Eres el equipo de Analistas de vídeos. Estos son los Shorts que más visitas han hecho esta semana en el tema
«{tema}» (te paso sus portadas en el mismo orden):
{lista}

Lo que busca la gente en YouTube sobre este tema: {palabras}

Saca lo que tienen en común los que más funcionan, en concreto (no generalidades).
Devuelve SOLO un JSON: {{"patrones_titulo": ["..."], "ganchos": ["..."], "duracion": "rango en segundos",
"finales": ["..."], "portadas": ["qué se ve en las portadas que funcionan"]}}"""

RECETA = """Eres el Recetario de los Influencers. Escribe la RECETA para el canal «{nombre}» ({tema}), para que su Escritor
haga vídeos que se parezcan a lo que funciona, pero originales (nunca copiar a nadie).
Lo que han visto los Analistas: {analisis}
Palabras que busca la gente: {palabras}
Cómo le va al canal (datos reales): {propio}
Devuelve SOLO un JSON: {{"titulo": "fórmula de título con un ejemplo", "gancho": "cómo empezar los 2 primeros segundos",
"duracion": "segundos", "ritmo": "...", "final": "cómo acabar", "palabras_clave": ["3-6"], "hashtags": ["3-5"],
"evitar": ["lo que no funciona"]}}"""


def recetas(clave, tema, lista, palabras):
    if not lista:
        return None
    carpeta = tempfile.mkdtemp()
    top = lista[:6]
    portadas = [p for p in (_portada(v["id"], carpeta) for v in top) if p]
    texto_lista = "\n".join(f"{n}. «{v['titulo']}» · {v['visitas']} visitas · {v['segundos']} s" for n, v in enumerate(top, 1))
    try:
        analisis = gemini.preguntar(ANALISIS.format(tema=tema["q"], lista=texto_lista, palabras=", ".join(palabras)),
                                    imagenes=portadas, solo_bueno=True, temperatura=0.4)
        _apuntar("analistas_videos", "analisis", {"canal": clave, "videos": len(top)})
        propio = (privado.leer(os.path.join("estado", "analisis", "informe.json"), {}) or {}).get("youtube", {}).get(clave, {})
        propio = {k: propio.get(k) for k in ("media_visitas_48h", "mejor_7_dias", "ultimos") if propio.get(k)}
        receta = gemini.preguntar(RECETA.format(nombre=tema["nombre"], tema=tema["q"],
                                                analisis=json.dumps(analisis, ensure_ascii=False),
                                                palabras=", ".join(palabras),
                                                propio=json.dumps(propio, ensure_ascii=False)[:3000] or "sin datos"),
                                  temperatura=0.5, ligero_primero=True)
    except gemini.SinIA as e:
        print(f"estudio: sin IA para la receta ({e})", flush=True)
        return None
    todas = privado.leer(os.path.join(CARPETA, "recetas.json"), {}) or {}
    anterior = todas.setdefault("canales", {}).get(clave) or {}
    todas["canales"][clave] = dict(receta, fecha=privado.ahora(), basada_en=len(top))
    if anterior.get("radar"):                    # lo que ha visto el Radar de nichos se queda
        todas["canales"][clave]["radar"] = anterior["radar"]
    privado.guardar_estado("influencers/recetas.json", {"canales": todas["canales"]})
    _apuntar("recetario", "receta", {"canal": clave})
    return receta


def espia(yt, listas):
    cuenta = {}
    for lista in listas:
        for v in lista[:10]:
            cuenta.setdefault(v["canal_id"], {"canal": v["canal"], "veces": 0, "visitas": 0})
            cuenta[v["canal_id"]]["veces"] += 1
            cuenta[v["canal_id"]]["visitas"] += v["visitas"]
    rivales = sorted(cuenta.items(), key=lambda x: x[1]["visitas"], reverse=True)[:3]
    informe = []
    for cid, datos in rivales:
        try:
            ch = yt.channels().list(part="contentDetails,statistics", id=cid).execute()["items"][0]
            subidas = ch["contentDetails"]["relatedPlaylists"]["uploads"]
            items = yt.playlistItems().list(playlistId=subidas, part="contentDetails", maxResults=15).execute()["items"]
            fechas = sorted(i["contentDetails"].get("videoPublishedAt", "") for i in items)
            dias = max(1, (dt.datetime.fromisoformat(fechas[-1].replace("Z", "+00:00")) -
                           dt.datetime.fromisoformat(fechas[0].replace("Z", "+00:00"))).days) if len(fechas) > 1 else None
            informe.append(dict(datos, suscriptores=int(ch["statistics"].get("subscriberCount", 0)),
                                videos_por_dia=round(len(fechas) / dias, 1) if dias else None))
        except Exception:
            informe.append(datos)
    privado.guardar_estado("influencers/competencia.json", {"rivales": informe})
    _apuntar("espia_competencia", "espionaje", {"rivales": len(informe)})


SEMANAL = """Eres la Estratega de crecimiento y la Exploradora de temas de una fábrica de vídeos cortos gratis. Datos:
- Informe de la Analista: {informe}
- Recetas de cada canal: {recetas}
- Competencia: {competencia}
- Tendencias de hoy en España: {tendencias}
Devuelve SOLO un JSON: {{"estrategia": {{"por_canal": {{"clave": "qué hacer esta semana (frecuencia, series, qué probar)"}},
"prueba_de_la_semana": "un experimento concreto"}}, "temas_nuevos": [{{"tema": "...", "por_que": "...", "riesgo": "..."}}]}}
Ten en cuenta que monetizar pide 1.000 suscriptores y 4.000 horas o 10 millones de visitas de Shorts en 90 días, y que
YouTube rechaza lo que parece producido en masa: mejor calidad y variedad que cantidad."""


def semanal():
    leer = lambda r: json.dumps(privado.leer(os.path.join(CARPETA, r), {}) or {}, ensure_ascii=False)[:5000]
    informe = json.dumps((privado.leer(os.path.join("estado", "analisis", "informe.json"), {}) or {}).get("informe"),
                         ensure_ascii=False)[:3000]
    try:
        r = gemini.preguntar(SEMANAL.format(informe=informe, recetas=leer("recetas.json"), competencia=leer("competencia.json"),
                                            tendencias=leer("tendencias.json")[:2500]), temperatura=0.6)
    except gemini.SinIA as e:
        print(f"estudio: sin IA para la estrategia ({e})", flush=True)
        return
    privado.guardar_estado("influencers/estrategia.json", r.get("estrategia", {}) if isinstance(r, dict) else {})
    privado.guardar_estado("influencers/temas.json", {"temas": r.get("temas_nuevos", []) if isinstance(r, dict) else []})
    _apuntar("estratega_crecimiento", "plan", {"canales": len((r.get("estrategia") or {}).get("por_canal", {}))})
    _apuntar("exploradora_temas", "temas", {"temas": len(r.get("temas_nuevos", []))})


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--semanal", action="store_true")
    p.add_argument("--todos", action="store_true", help="estudia todos los temas (gasta más cuota)")
    a = p.parse_args()
    yt = buscador_clips.servicio()
    hechos = []
    try:
        tendencias(yt)
        hechos.append("tendencias")
    except Exception as e:
        print(f"estudio: tendencias fallaron ({type(e).__name__})", flush=True)
    lista_temas = list(temas().items())
    if not a.todos:                         # 2 temas al día para no gastar cuota: primero los que la fábrica está
        recetas_hechas = (privado.leer(os.path.join(CARPETA, "recetas.json"), {}) or {}).get("canales", {})
        orden = {k: i for i, k in enumerate(privado.ajustes().get("prioridad", []))}   # haciendo y no tienen receta

        def urgencia(item):
            clave = item[0]
            fecha = (recetas_hechas.get(clave) or {}).get("fecha")
            dias = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(fecha.replace("Z", "+00:00"))).days if fecha else 99
            return (-min(dias, 30), orden.get(clave, 99))
        lista_temas = sorted(lista_temas, key=urgencia)[:2]
    listas = []
    for clave, tema in lista_temas:
        try:
            lista = virales(yt, clave, tema)
            listas.append(lista)
            palabras = palabras_clave(clave, tema)
            recetas(clave, tema, lista, palabras)
            hechos.append(privado.alias(clave))
        except Exception as e:
            print(f"estudio: {privado.alias(clave)} falló ({type(e).__name__})", flush=True)
    if listas:
        try:
            espia(yt, listas)
        except Exception as e:
            print(f"estudio: espía falló ({type(e).__name__})", flush=True)
    if a.semanal or dt.datetime.now(dt.timezone.utc).weekday() == 0:
        semanal()
    gemini.apuntar_portero()
    print(f"estudio de los Influencers: {', '.join(hechos) or 'nada'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
