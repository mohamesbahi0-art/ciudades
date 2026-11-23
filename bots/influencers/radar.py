"""El Radar de nichos (Influencers): cada día mira qué está funcionando en el nicho de cada perfil y se lo pasa a los
guionistas y a la app.

TikTok e Instagram no dejan que un robot mire vídeos de otras cuentas (no hay vía gratis ni permitida), así que el
Radar mira YouTube Shorts, donde se sube casi todo lo que peta en TikTok, con la API oficial; y Gemini «ve» por su
enlace los que más crecen (no se descarga nada).

Para cada perfil (canal de YouTube o barrio de TikTok/Instagram, también en pausa) con "nicho" en la config privada:
    "nicho": {"busquedas": ["texto", {"q": "texto", "idioma": "en", "region": "US"}], "idioma": "es", "region": "ES",
              "cada": 1, "minimo": 3000}
1. Busca los Shorts de los últimos 14 días (una búsqueda por pasada; van rotando; 100 unidades de cuota).
2. Saca sus cifras (1 unidad) y calcula las visitas por día.
3. Gemini ve los que más crecen y aún no había visto (uno por creador): gancho, tema, formato, estilo, ritmo, voz y
   música, por qué funciona y una idea ORIGINAL para nosotros.
4. Resume «lo que funciona esta semana» y lo deja en la receta del perfil (la leen los guionistas) y en
   estado/influencers/radar/<alias>.json (lo copia a la app la ronda de Claude).

Cuota: las subidas mandan. Gasta como mucho `radar_unidades_dia` (500) al día, lo apunta en el libro de cuota del
Subidor y, si la cuota del día se ha acabado, no busca nada.
Uso:  python bots/influencers/radar.py [--solo barrio-2,gta] [--videos 3] [--sin-ver] [--todos]
"""
import argparse
import datetime as dt
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.central import buscador_clips, subidor  # noqa: E402
from bots.comun import gemini, privado  # noqa: E402

ROBOT = "radar_nichos"
CARPETA = os.path.join("influencers", "radar")          # dentro de estado/
COSTE_BUSQUEDA, COSTE_LISTA = 100, 1
DIAS = 14
IDIOMAS = {"es": "español de España", "en": "inglés", "nl": "neerlandés", "fr": "francés", "pt": "portugués"}

VER = """Eres el Radar de nichos de una fábrica de vídeos cortos. Mira este Short de YouTube entero.
Lo hemos encontrado buscando «{busqueda}» para nuestro perfil «{nombre}» ({tema}). Lleva {visitas} visitas en {dias} días
(unas {por_dia} al día): está funcionando. Explica por qué, para que nuestros guionistas hagan vídeos ORIGINALES con la
misma fórmula (nunca copiar su texto, sus imágenes ni su idea exacta).
Devuelve SOLO un JSON:
{{"gancho": {{"texto": "lo que dice o pone en los 2 primeros segundos", "que_se_ve": "lo que se ve en esos 2 segundos"}},
"tema": "de qué va, en una frase", "formato": "tipo de vídeo (historia de famoso, lista, A contra B, pregunta, dato…)",
"estilo_visual": "cómo está hecho (animación, imágenes, grabado, texto en pantalla, colores…)",
"ritmo": "cortes, velocidad y duración", "voz_y_musica": "qué voz y qué música lleva", "estructura": ["paso 1", "paso 2"],
"final": "cómo acaba", "por_que_funciona": "una o dos frases",
"idea_para_nosotros": {{"titulo": "...", "gancho": "primera frase, en {idioma}", "resumen": "de qué iría"}},
"encaja": 0}}
(encaja: de 0 a 100, cuánto encaja con nuestro perfil; si el vídeo no es de este nicho, menos de 30)
Explica todo en español de España sencillo, salvo el gancho de la idea, que va en {idioma}."""

RESUMEN = """Eres el Radar de nichos de una fábrica de vídeos cortos. Estos son los Shorts que más están creciendo ahora en el
nicho de nuestro perfil «{nombre}» ({tema}) y lo que viste en cada uno:
{videos}
Escribe «lo que funciona esta semana» para nuestros guionistas, en español de España sencillo. Fórmulas, no copias:
nada de repetir sus frases ni sus ideas exactas.
Devuelve SOLO un JSON: {{"titular": "una frase", "lo_que_funciona": ["3-5 frases cortas"],
"ganchos": ["3 fórmulas de gancho, cada una con un ejemplo"], "temas": ["3-5 temas que están tirando"],
"formato": "el formato que más se repite", "duracion": "segundos", "evitar": ["1-3 cosas que no salen en los que funcionan"],
"ideas": [{{"titulo": "...", "gancho": "primera frase, en {idioma}", "resumen": "de qué iría"}}]}}  (3 ideas para nosotros)"""


def fecha(texto):
    return dt.datetime.fromisoformat(texto.replace("Z", "+00:00"))


def perfiles():
    """Los perfiles con nicho: canales de YouTube y barrios de TikTok/Instagram (también los que están en pausa, así hay
    ideas cuando vuelvan)."""
    cfg = privado.config()
    salida = {}
    for seccion in ("barrios", "canales"):
        for clave, c in (cfg.get(seccion) or {}).items():
            n = c.get("nicho") or {}
            if not n.get("busquedas"):
                continue
            barrio = seccion == "barrios"
            salida[clave] = {"clave": clave, "barrio": barrio, "nombre": c.get("nombre", clave), "nicho": n,
                             "tema": (c.get("tema") or c.get("busqueda") or clave)[:160],
                             "idioma": (n.get("idioma") or c.get("idioma") or "es")[:2].lower(),
                             "red": ", ".join(c.get("redes") or [c.get("red") or "tiktok"]) if barrio else "youtube",
                             "cada": float(n.get("cada", 1 if barrio else 3)), "pausa": c.get("estado") == "en_pausa"
                             or bool(c.get("pausado"))}
    return salida


def propios():
    """Los ids de nuestros canales de YouTube, para no estudiarnos a nosotros mismos."""
    return {c.get("id") for c in (privado.config().get("canales") or {}).values() if c.get("id")}


def leer_radar(clave):
    return privado.leer(os.path.join("estado", CARPETA, f"{privado.alias(clave)}.json"), {}) or {}


def presupuesto():
    """Las unidades de cuota que el Radar aún puede gastar hoy (0 si la cuota común se ha acabado)."""
    if subidor.cuota().get("agotada_hasta"):
        return 0
    limite = int(privado.ajustes().get("radar_unidades_dia", 500))
    return max(0, limite - subidor.gastado(ROBOT))


def buscar(yt, b, desde):
    params = dict(part="id", q=b["q"], type="video", videoDuration="short", order="viewCount", publishedAfter=desde,
                  maxResults=50)
    if b.get("idioma"):
        params["relevanceLanguage"] = b["idioma"]
    if b.get("region"):
        params["regionCode"] = b["region"]
    r = yt.search().list(**params).execute()
    return [x["id"]["videoId"] for x in r.get("items", []) if (x.get("id") or {}).get("videoId")]


def cifras(yt, ids):
    if not ids:
        return []
    r = yt.videos().list(id=",".join(ids[:50]), part="snippet,contentDetails,statistics").execute()
    ahora = dt.datetime.now(dt.timezone.utc)
    salida = []
    for v in r.get("items", []):
        sn, st = v.get("snippet") or {}, v.get("statistics") or {}
        if sn.get("liveBroadcastContent") not in (None, "none") or not sn.get("publishedAt"):
            continue
        dias = max((ahora - fecha(sn["publishedAt"])).total_seconds() / 86400, 0.5)
        visitas = int(st.get("viewCount", 0))
        salida.append({"id": v["id"], "url": f"https://youtube.com/shorts/{v['id']}", "titulo": sn.get("title", ""),
                       "canal": sn.get("channelTitle", ""), "canal_id": sn.get("channelId", ""),
                       "publicado": sn["publishedAt"], "dias": round(dias, 1),
                       "segundos": buscador_clips.segundos((v.get("contentDetails") or {}).get("duration")),
                       "visitas": visitas, "me_gusta": int(st.get("likeCount", 0)),
                       "comentarios": int(st.get("commentCount", 0)), "visitas_dia": int(visitas / dias),
                       "idioma": (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "")[:2].lower()})
    return salida


def elegir(lista, vistos, nuestros, idioma, cuantos, minimo):
    """Los que más crecen (visitas por día), que no hayamos visto, uno por creador y en el idioma del nicho."""
    creadores, elegidos = set(), []
    for v in sorted(lista, key=lambda v: v["visitas_dia"], reverse=True):
        if (v["id"] in vistos or v["canal_id"] in nuestros or v["canal_id"] in creadores or v["visitas"] < minimo
                or not 5 <= v["segundos"] <= 180 or (v["idioma"] and idioma and v["idioma"] != idioma)):
            continue
        creadores.add(v["canal_id"])
        elegidos.append(v)
        if len(elegidos) >= cuantos:
            break
    return elegidos


def _encaja(analisis):
    try:
        return int(float(analisis.get("encaja")))
    except (TypeError, ValueError):
        return 50


def _linea(v):
    a = v.get("analisis") or {}
    g = a.get("gancho") or {}
    if not isinstance(g, dict):
        g = {"texto": str(g)}
    return (f"- «{v['titulo'][:90]}» ({v['visitas']} visitas en {v['dias']} días, {v['segundos']} s). "
            f"Gancho: {g.get('texto', '')} / {g.get('que_se_ve', '')}. Formato: {a.get('formato', '')}. "
            f"Estilo: {a.get('estilo_visual', '')}. Ritmo: {a.get('ritmo', '')}. "
            f"Por qué funciona: {a.get('por_que_funciona', '')}")[:600]


def resumir(perfil, videos):
    idioma = IDIOMAS.get(perfil["idioma"], perfil["idioma"])
    r = gemini.preguntar(RESUMEN.format(nombre=perfil["nombre"], tema=perfil["tema"], idioma=idioma,
                                        videos="\n".join(_linea(v) for v in videos)),
                         temperatura=0.5, ligero_primero=True)
    if not isinstance(r, dict):
        raise gemini.SinIA("el resumen no ha salido en el formato pedido")
    return dict(r, fecha=privado.ahora(), basado_en=len(videos))


def receta(perfil, radar):
    """Lo que funciona en el nicho entra en la receta del perfil, que el Escritor/Guionista lee antes de escribir."""
    r = radar.get("resumen") or {}
    todas = privado.leer(os.path.join("estado", "influencers", "recetas.json"), {}) or {}
    canales = todas.setdefault("canales", {})
    canales.setdefault(perfil["clave"], {})["radar"] = {
        "fecha": privado.ahora(), "lo_que_funciona": (r.get("lo_que_funciona") or [])[:5],
        "ganchos": (r.get("ganchos") or [])[:3], "temas": (r.get("temas") or [])[:5], "formato": r.get("formato"),
        "duracion": r.get("duracion"), "evitar": (r.get("evitar") or [])[:3], "ideas": (r.get("ideas") or [])[:3],
        "ejemplos": [v["url"] for v in radar.get("videos", []) if v.get("analisis")][-3:]}
    privado.guardar_estado("influencers/recetas.json", {"canales": canales})


def pasar(yt, perfil, radar, desde, a, cuaderno):
    """Una pasada del Radar por un perfil: una búsqueda, las cifras, Gemini ve los mejores y el resumen."""
    clave = perfil["clave"]
    busquedas = perfil["nicho"]["busquedas"]
    i = int(radar.get("siguiente", 0)) % len(busquedas)
    b = busquedas[i]
    b = {"q": b} if isinstance(b, str) else dict(b)
    b.setdefault("idioma", perfil["idioma"])
    b.setdefault("region", perfil["nicho"].get("region"))
    desde_cuando = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=21)
    try:
        ids = buscar(yt, b, desde)
    except Exception as e:
        if "quotaExceeded" in str(e) or "dailyLimitExceeded" in str(e):
            subidor.agotada()
            raise RuntimeError("la cuota de YouTube de hoy se ha acabado") from None
        raise
    subidor.gastar(COSTE_BUSQUEDA, ROBOT)
    lista = cifras(yt, ids)
    subidor.gastar(COSTE_LISTA, ROBOT)
    nuestros = propios()
    elegidos = elegir(lista, set(radar.get("vistos", [])), nuestros, b["idioma"], a.videos,
                      int(perfil["nicho"].get("minimo", 3000)))
    idioma = IDIOMAS.get(perfil["idioma"], perfil["idioma"])
    nuevos = []
    for v in elegidos:
        entrada = dict(v, busqueda=b["q"], visto=privado.ahora())
        if not a.sin_ver:
            try:
                analisis = gemini.ver_youtube(f"https://www.youtube.com/watch?v={v['id']}", VER.format(
                    busqueda=b["q"], nombre=perfil["nombre"], tema=perfil["tema"], visitas=v["visitas"], dias=v["dias"],
                    por_dia=v["visitas_dia"], idioma=idioma))
                if isinstance(analisis, dict):
                    entrada["analisis"] = analisis
            except gemini.SinIA as e:
                entrada["sin_ver"] = str(e)[:160]
        nuevos.append(entrada)
    radar.update(clave=clave, alias=privado.alias(clave), nombre=perfil["nombre"], red=perfil["red"],
                 idioma=perfil["idioma"], tema=perfil["tema"], en_pausa=perfil["pausa"], siguiente=i + 1,
                 ultimo=privado.ahora(), busquedas=[x if isinstance(x, str) else x.get("q") for x in busquedas])
    radar["vistos"] = (radar.get("vistos", []) + [v["id"] for v in nuevos])[-600:]
    radar["videos"] = [v for v in radar.get("videos", []) + nuevos if fecha(v["visto"]) >= desde_cuando][-40:]
    radar["top_ahora"] = [{k: v[k] for k in ("titulo", "canal", "url", "visitas", "visitas_dia", "dias", "segundos")}
                          for v in sorted((x for x in lista if x["canal_id"] not in nuestros),
                                          key=lambda x: x["visitas_dia"], reverse=True)[:5]]
    radar["historial"] = (radar.get("historial", []) + [{"fecha": privado.ahora(), "busqueda": b["q"],
                                                          "idioma": b["idioma"], "encontrados": len(lista),
                                                          "nuevos": len(nuevos)}])[-60:]
    buenos = [v for v in radar["videos"] if v.get("analisis") and _encaja(v["analisis"]) >= 30]
    vistos_ia = sum(1 for v in nuevos if v.get("analisis"))
    if vistos_ia and buenos:
        try:
            radar["resumen"] = resumir(perfil, buenos[-12:])
            receta(perfil, radar)
        except gemini.SinIA as e:
            print(f"radar: {privado.alias(clave)} sin resumen hoy ({type(e).__name__})", flush=True)
    privado.guardar_estado(os.path.join(CARPETA, f"{privado.alias(clave)}.json"), radar)
    cuaderno.apuntar("radar", {"canal": clave, "busqueda": b["q"], "encontrados": len(lista), "nuevos": len(nuevos),
                               "vistos": vistos_ia, "resumen": bool(vistos_ia and buenos)})
    return f"{len(nuevos)} nuevos, {vistos_ia} vistos con la IA"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--solo", default="", help="perfiles separados por comas (clave o alias, p. ej. barrio-2,gta)")
    p.add_argument("--videos", type=int, default=3, help="cuántos vídeos nuevos ve Gemini por perfil")
    p.add_argument("--sin-ver", action="store_true", help="solo busca y cuenta, sin que Gemini vea los vídeos")
    p.add_argument("--todos", action="store_true", help="mira todos aunque no les toque hoy (respeta la cuota)")
    a = p.parse_args(argv)
    lista = perfiles()
    if a.solo:
        quiero = {privado.resolver(x) for x in a.solo.split(",") if x.strip()}
        lista = {k: v for k, v in lista.items() if k in quiero}
    ahora = dt.datetime.now(dt.timezone.utc)
    radares = {k: leer_radar(k) for k in lista}

    def atraso(k):                    # días que lleva sin mirar, menos cada cuánto le toca (>= 0: le toca)
        ultimo = radares[k].get("ultimo")
        dias = (ahora - fecha(ultimo)).total_seconds() / 86400 if ultimo else 999
        return dias - lista[k]["cada"]

    orden = sorted(lista, key=lambda k: (-atraso(k), not lista[k]["barrio"], lista[k]["pausa"]))
    if not (a.todos or a.solo):
        orden = [k for k in orden if atraso(k) >= -0.15]     # unas horas de margen por si GitHub se retrasa
    if not orden:
        print("radar: hoy no le toca a ningún perfil", flush=True)
        return 0
    cuaderno = privado.cuaderno(ROBOT)
    hechos, sin_cuota = [], []
    yt = None
    desde = (ahora - dt.timedelta(days=DIAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for k in orden:
        if presupuesto() < COSTE_BUSQUEDA + COSTE_LISTA:
            sin_cuota.append(privado.alias(k))
            continue
        yt = yt or buscador_clips.servicio()
        try:
            hechos.append(f"{privado.alias(k)}: {pasar(yt, lista[k], radares[k], desde, a, cuaderno)}")
        except Exception as e:      # un perfil que falla no para a los demás
            print(f"radar: {privado.alias(k)} falló ({type(e).__name__})", flush=True)
            cuaderno.apuntar("error", {"canal": k, "error": privado.limpiar(f"{type(e).__name__}: {e}")[:300]})
            if "cuota" in str(e):
                break
    if sin_cuota:
        print(f"radar: sin cuota para {len(sin_cuota)} perfiles más hoy (las subidas mandan): "
              f"{', '.join(sin_cuota)}", flush=True)
    cuaderno.guardar()
    gemini.apuntar_portero()
    print(f"radar de nichos: {'; '.join(hechos) or 'nada'} · gastado hoy {subidor.gastado(ROBOT)} unidades", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
