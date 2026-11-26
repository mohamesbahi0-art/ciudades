"""El Ojeador de redes (ciudad de los Influencers): un robot «enganchado» a TikTok e Instagram que solo mira, sin cuenta
y sin disfrazarse, como alguien que cotillea el móvil. Es los ojos de los Influencers: lo que ve se lo pasa al
Recetario (la receta de cada perfil, que leen los guionistas), al Estudio de los Influencers y a la app.

Cada ronda (GitHub Actions, cada 3 horas):
1. Ojos (ojeador.js): abre «Explorar» de TikTok y sus categorías, las páginas de temas de TikTok (/discover/) y los
   reels populares de Instagram de los temas de unos pocos perfiles (van rotando), baja despacio y descansa entre
   página y página. Si una red dice que no (captcha, «inténtalo más tarde», 403/429), la deja en paz unas horas y lo
   vuelve a intentar después: no se salta nada ni se hace pasar por nadie.
2. Datos: lee con yt-dlp las cifras de cada vídeo nuevo (visitas, me gusta, comentarios, compartidos, canción,
   hashtags y fecha) y calcula cuánto crece (visitas al día).
3. Ver: Gemini ve enteros los que más crecen de cada perfil (uno por creador; el vídeo se baja un momento y se borra):
   gancho, formato, ritmo, por qué funciona y una idea ORIGINAL para nosotros (fórmulas, nunca copias).
4. Pasar: resume «lo que funciona ahora en TikTok e Instagram» de cada perfil y lo deja en su receta y en
   estado/influencers/ojeador/<alias>.json; lo que más se repite en todo TikTok (canciones, hashtags y lo que más
   crece) va a estado/influencers/ojeador/tendencias.json. La ronda de Claude lo copia a la app.

Configuración (repositorio privado):
- config/canales.json → en cada perfil: "ojeador": {"categorias": ["Educación"], "temas": ["dinero"]} (sin "temas",
  usa las búsquedas del nicho; sin "categorias", solo mira sus temas);
- config/fabrica.json → "ojeador": {"perfiles_ronda": 3, "datos_ronda": 60, "ia_ronda": 3, "ia_dia": 8,
  "minimo": 20000, "descanso_horas": 12}.
En el registro público solo salen alias y cuentas.
Uso:  python bots/influencers/ojeador.py [--solo barrio-2,gta] [--sin-ver] [--vista salida.json]
"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import gemini, privado  # noqa: E402

ROBOT = "ojeador_redes"
CARPETA = os.path.join("influencers", "ojeador")          # dentro de estado/
TENDENCIAS = os.path.join(CARPETA, "tendencias.json")
CACHE = os.path.join(CARPETA, "_cifras.json")             # las cifras ya leídas (2 días), para no preguntar dos veces
EXPLORAR = "https://www.tiktok.com/explore"
PAUSA_IA = float(os.environ.get("OJEADOR_PAUSA", 25))     # segundos entre vídeo y vídeo: no comerse la IA de la fábrica
DEFECTO = {"perfiles_ronda": 3, "datos_ronda": 60, "ia_ronda": 3, "ia_dia": 8, "minimo": 20000, "descanso_horas": 12,
           "max_mb": 12}
IDIOMAS = {"es": "español de España", "en": "inglés", "nl": "neerlandés", "fr": "francés", "pt": "portugués"}
RELLENO = {"fyp", "foryou", "foryoupage", "parati", "viral", "viralvideo", "trending", "tiktok", "fy", "xyzbca", "capcut",
           "reels", "reel", "explore", "explorepage", "instagram", "fypシ", "fypage", "foryourpage", "paratii"}
SONIDO_PROPIO = re.compile(r"original sound|sonido original|son original|origineel geluid|som original|оригинальный звук",
                           re.I)

VER = """Eres el Ojeador de redes de una fábrica de vídeos cortos. Mira este vídeo de {red} entero.
Lo hemos visto mirando «{donde}» para nuestro perfil «{nombre}» ({tema}). Lleva {visitas} visitas en {dias} días (unas
{por_dia} al día), {likes} me gusta y {comentarios} comentarios: está funcionando. Explica por qué, para que nuestros
guionistas hagan vídeos ORIGINALES con la misma fórmula (nunca copiar su texto, sus imágenes ni su idea exacta).
Devuelve SOLO un JSON:
{{"gancho": {{"texto": "lo que dice o pone en los 2 primeros segundos", "que_se_ve": "lo que se ve en esos 2 segundos"}},
"tema": "de qué va, en una frase", "formato": "tipo de vídeo (historia, lista, A contra B, pregunta, dato, tutorial…)",
"estilo_visual": "cómo está hecho (animación, grabado, texto en pantalla, colores…)", "ritmo": "cortes, velocidad y
duración", "voz_y_musica": "qué voz y qué música o sonido lleva", "estructura": ["paso 1", "paso 2"],
"final": "cómo acaba", "por_que_funciona": "una o dos frases",
"idea_para_nosotros": {{"titulo": "...", "gancho": "primera frase, en {idioma}", "resumen": "de qué iría"}},
"encaja": 0}}
(encaja: de 0 a 100, cuánto encaja con nuestro perfil; si el vídeo no es de este nicho, menos de 30)
Explica todo en español de España sencillo, salvo el gancho de la idea, que va en {idioma}."""

RESUMEN = """Eres el Ojeador de redes de una fábrica de vídeos cortos. Estos son vídeos de TikTok e Instagram que están
creciendo ahora en el nicho de nuestro perfil «{nombre}» ({tema}) y lo que viste en cada uno:
{videos}
Canciones y hashtags que más se repiten ahora en TikTok: {tendencias}
Escribe «lo que funciona ahora en TikTok e Instagram» para nuestros guionistas, en español de España sencillo.
Fórmulas, no copias: nada de repetir sus frases ni sus ideas exactas.
Devuelve SOLO un JSON: {{"titular": "una frase", "lo_que_funciona": ["3-5 frases cortas"],
"ganchos": ["3 fórmulas de gancho, cada una con un ejemplo"], "temas": ["3-5 temas que están tirando"],
"formato": "el formato que más se repite", "duracion": "segundos", "evitar": ["1-3 cosas que no salen en los que funcionan"],
"sonidos": ["1-3 canciones o sonidos que encajan, si los hay"],
"ideas": [{{"titulo": "...", "gancho": "primera frase, en {idioma}", "resumen": "de qué iría"}}]}}  (3 ideas para nosotros)"""


def ajustes():
    a = dict(DEFECTO)
    a.update((privado.ajustes() or {}).get("ojeador") or {})
    return a


def _sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def trozo(texto):
    """«finanzas personales» → «finanzas-personales» (páginas de temas de TikTok)."""
    return re.sub(r"[^a-z0-9]+", "-", _sin_tildes(texto.lower())).strip("-")


def etiqueta(texto):
    """«finanzas personales» → «finanzaspersonales» (hashtags de Instagram)."""
    return re.sub(r"[^a-z0-9]", "", _sin_tildes(texto.lower()))


def perfiles():
    """Los perfiles que vigila: canales de YouTube y barrios de TikTok/Instagram con temas (también en pausa, para que
    haya ideas cuando vuelvan; van los últimos)."""
    cfg = privado.config()
    salida = []
    for seccion in ("barrios", "canales"):
        for clave, c in (cfg.get(seccion) or {}).items():
            o = c.get("ojeador") or {}
            if o.get("apagado"):
                continue
            n = c.get("nicho") or {}
            temas = [t for t in (o.get("temas") or [b if isinstance(b, str) else b.get("q")
                                                     for b in n.get("busquedas") or []]) if t]
            if not temas:
                continue
            salida.append({"clave": clave, "barrio": seccion == "barrios", "nombre": c.get("nombre", clave),
                           "tema": (c.get("tema") or clave)[:160], "temas": temas,
                           "categorias": o.get("categorias") or [],
                           "idioma": (n.get("idioma") or c.get("idioma") or "es")[:2].lower(),
                           "pausa": c.get("estado") == "en_pausa" or bool(c.get("pausado"))})
    salida.sort(key=lambda p: (p["pausa"], not p["barrio"]))
    return salida


def leer(clave):
    return privado.leer(os.path.join("estado", CARPETA, f"{privado.alias(clave)}.json"), {}) or {}


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _iso(momento):
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fecha(texto):
    try:
        return dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None


def libre(tendencias, fuente, horas):
    """¿Se puede volver a mirar esta fuente? Si la última vez dijo que no, se la deja en paz unas horas."""
    f = (tendencias.get("fuentes") or {}).get(fuente) or {}
    if f.get("estado") != "bloqueada":
        return True
    cuando = _fecha(f.get("fecha"))
    return not cuando or (_ahora() - cuando).total_seconds() > horas * 3600


def plan(elegidos, tendencias, a):
    pasos = []
    if libre(tendencias, "tiktok-explorar", a["descanso_horas"]):
        categorias = []
        for p in elegidos:
            categorias += [c for c in p["categorias"] if c not in categorias]
        pasos.append({"id": "tiktok-explorar", "tipo": "tiktok-explorar", "url": EXPLORAR,
                      "categorias": (["Todo"] + categorias)[:5], "rondas": 3})
    for n, p in enumerate(elegidos):
        estado = leer(p["clave"])
        hace_semana = _ahora() - dt.timedelta(days=7)
        vacios = {t for t, f in (estado.get("temas_vacios") or {}).items() if (_fecha(f) or _ahora()) > hace_semana}
        temas = [t for t in p["temas"] if t not in vacios] or p["temas"]    # los temas sin página se saltan una semana
        tema = temas[int(estado.get("siguiente", 0)) % len(temas)]
        alias = privado.alias(p["clave"])
        if libre(tendencias, "tiktok-temas", a["descanso_horas"]):
            pasos.append({"id": f"tiktok-temas-{alias}", "tipo": "tiktok-temas", "perfil": p["clave"], "tema": tema,
                          "url": f"https://www.tiktok.com/discover/{trozo(tema)}", "rondas": 2})
        # Instagram corta enseguida si se le piden muchas páginas seguidas: una sola por ronda
        if n == 0 and libre(tendencias, "instagram", a["descanso_horas"]):
            pasos.append({"id": f"instagram-{alias}", "tipo": "instagram", "perfil": p["clave"], "tema": tema,
                          "url": f"https://www.instagram.com/explore/tags/{etiqueta(tema)}/", "rondas": 2})
    return pasos


def mirar(pasos):
    """Los ojos (ojeador.js con un navegador normal). Devuelve los pasos con lo que ha visto cada uno."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada, salida = os.path.join(tmp, "plan.json"), os.path.join(tmp, "vista.json")
        with open(entrada, "w", encoding="utf-8") as f:
            json.dump({"pasos": pasos}, f, ensure_ascii=False)
        r = subprocess.run(["node", os.path.join(RAIZ, "bots", "influencers", "ojeador.js"), entrada, salida],
                           text=True, timeout=1800)
        if r.returncode != 0 or not os.path.exists(salida):
            raise RuntimeError("el navegador no ha podido mirar")
        with open(salida, encoding="utf-8") as f:
            return json.load(f)


def _red(url):
    return "instagram" if "instagram.com" in url else "tiktok"


def datos(url):
    """Las cifras de un vídeo con yt-dlp (sin cuenta, sin cookies). None si la red no las da."""
    try:
        r = subprocess.run(["yt-dlp", "-j", "--skip-download", "--no-warnings", "--no-playlist", url],
                           capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        d = json.loads(r.stdout.splitlines()[0])
    except ValueError:
        return None
    visitas = d.get("view_count") or d.get("play_count")
    texto = (d.get("description") or d.get("title") or "").strip()
    subido = None
    if d.get("timestamp"):
        subido = dt.datetime.fromtimestamp(int(d["timestamp"]), dt.timezone.utc)
    elif d.get("upload_date"):
        subido = dt.datetime.strptime(d["upload_date"], "%Y%m%d").replace(tzinfo=dt.timezone.utc)
    dias = max(0.5, round((_ahora() - subido).total_seconds() / 86400, 1)) if subido else None
    likes, comentarios, compartidos = d.get("like_count") or 0, d.get("comment_count") or 0, d.get("repost_count") or 0
    cancion = " - ".join(x for x in (d.get("track"), d.get("artist")) if x) or None
    return {"id": str(d.get("id") or url), "red": _red(url), "url": d.get("webpage_url") or url,
            "creador": d.get("uploader") or d.get("channel") or d.get("uploader_id"), "titulo": texto.split("\n")[0][:120],
            "texto": texto[:300], "hashtags": [h.lower() for h in re.findall(r"#(\w+)", texto)][:12],
            "cancion": cancion, "segundos": int(d.get("duration") or 0), "visitas": visitas, "likes": likes,
            "comentarios": comentarios, "compartidos": compartidos, "subido": _iso(subido) if subido else None,
            "dias": dias, "visitas_dia": int(visitas / dias) if visitas and dias else None,
            "interaccion": round((likes + comentarios + compartidos) / visitas, 4) if visitas else None}


def bajar(url, carpeta, max_mb):
    destino = os.path.join(carpeta, "video.%(ext)s")
    try:
        subprocess.run(["yt-dlp", "-q", "--no-warnings", "--no-playlist", "--max-filesize", f"{max_mb}M", "-f",
                        f"b[height<=720][filesize<{max_mb}M]/b[height<=720]/b", "-o", destino, url],
                       capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return None
    hechos = [f for f in glob.glob(os.path.join(carpeta, "video.*")) if not f.endswith(".part")]
    return hechos[0] if hechos and os.path.getsize(hechos[0]) < gemini.VIDEO_MAXIMO else None


def _linea(v):
    a = v.get("analisis") or {}
    g = a.get("gancho") or {}
    if not isinstance(g, dict):
        g = {"texto": str(g)}
    return (f"- {v['red']}: «{v.get('titulo', '')[:90]}» ({v.get('visitas')} visitas en {v.get('dias')} días, "
            f"{v.get('segundos')} s, canción: {v.get('cancion') or 'sonido propio'}). Gancho: {g.get('texto', '')} / "
            f"{g.get('que_se_ve', '')}. Formato: {a.get('formato', '')}. Estilo: {a.get('estilo_visual', '')}. "
            f"Ritmo: {a.get('ritmo', '')}. Por qué funciona: {a.get('por_que_funciona', '')}")[:650]


def _encaja(analisis):
    try:
        return int(float(analisis.get("encaja")))
    except (TypeError, ValueError):
        return 50


def recuento(videos, cuantos=12):
    """Las canciones y los hashtags que más se repiten (sin el relleno de siempre)."""
    canciones, hashtags = collections.Counter(), collections.Counter()
    for v in videos:
        if v.get("cancion") and not SONIDO_PROPIO.search(v["cancion"]):
            canciones[v["cancion"]] += 1
        for h in set(v.get("hashtags") or []):
            if h not in RELLENO and len(h) > 2 and not h.isdigit():
                hashtags[h] += 1
    return ([{"nombre": c, "veces": n} for c, n in canciones.most_common(cuantos)],
            [{"nombre": h, "veces": n} for h, n in hashtags.most_common(cuantos)])


def resumir(perfil, videos, tendencias, lecciones=""):
    idioma = IDIOMAS.get(perfil["idioma"], perfil["idioma"])
    lista = ", ".join(c["nombre"] for c in (tendencias.get("canciones") or [])[:5]) or "(ninguna)"
    lista += " · " + ", ".join("#" + h["nombre"] for h in (tendencias.get("hashtags") or [])[:8])
    r = gemini.preguntar(RESUMEN.format(nombre=perfil["nombre"], tema=perfil["tema"], idioma=idioma, tendencias=lista,
                                        videos="\n".join(_linea(v) for v in videos)) + lecciones,
                         temperatura=0.5, ligero_primero=True)
    if not isinstance(r, dict):
        raise gemini.SinIA("el resumen no ha salido en el formato pedido")
    return dict(r, fecha=privado.ahora(), basado_en=len(videos))


def receta(perfil, estado):
    """Lo que funciona en TikTok e Instagram entra en la receta del perfil, junto a lo del Radar de nichos."""
    r = estado.get("resumen") or {}
    todas = privado.leer(os.path.join("estado", "influencers", "recetas.json"), {}) or {}
    canales = todas.setdefault("canales", {})
    canales.setdefault(perfil["clave"], {})["ojeador"] = {
        "fecha": privado.ahora(), "lo_que_funciona": (r.get("lo_que_funciona") or [])[:5],
        "ganchos": (r.get("ganchos") or [])[:3], "temas": (r.get("temas") or [])[:5], "formato": r.get("formato"),
        "duracion": r.get("duracion"), "evitar": (r.get("evitar") or [])[:3], "sonidos": (r.get("sonidos") or [])[:3],
        "ideas": (r.get("ideas") or [])[:3],
        "ejemplos": [v["url"] for v in estado.get("videos", []) if v.get("analisis")][-3:]}
    privado.guardar_estado("influencers/recetas.json", {"canales": canales})


def elegir(candidatos, vistos, cuantos, minimo):
    """Los que más crecen, que no hayamos visto, uno por creador, ni muy cortos ni muy largos."""
    creadores, elegidos = set(), []
    if cuantos <= 0:
        return elegidos
    for v in sorted(candidatos, key=lambda v: v.get("visitas_dia") or 0, reverse=True):
        if (v["id"] in vistos or (v.get("creador") and v["creador"] in creadores) or (v.get("visitas") or 0) < minimo
                or not 5 <= (v.get("segundos") or 0) <= 180):
            continue
        creadores.add(v.get("creador"))
        elegidos.append(v)
        if len(elegidos) >= cuantos:
            break
    return elegidos


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--solo", default="", help="alias o claves separadas por comas")
    p.add_argument("--sin-ver", action="store_true", help="no gasta IA: solo mira y lee cifras")
    p.add_argument("--vista", help="usar lo que ya vieron los ojos (un salida.json) en vez de abrir el navegador")
    a = p.parse_args(argv)
    aj = ajustes()
    cuaderno = privado.cuaderno(ROBOT)
    lecciones = cuaderno.para_el_prompt()
    lecciones = f"\n\nLo que ha aprendido el Ojeador (lo del dueño manda):\n{lecciones}" if lecciones.strip() else ""
    tendencias = privado.leer(os.path.join("estado", TENDENCIAS), {}) or {}
    hoy = _ahora().strftime("%Y-%m-%d")
    ia = tendencias.get("ia") if (tendencias.get("ia") or {}).get("dia") == hoy else {"dia": hoy, "vistos": 0}

    todos = perfiles()
    if a.solo:
        pedidos = {privado.resolver(x.strip()) for x in a.solo.split(",") if x.strip()}
        todos = [x for x in todos if x["clave"] in pedidos or privado.alias(x["clave"]) in pedidos]
    if not todos:
        print("ojeador: no hay perfiles con temas que mirar")
        return 0
    n = int(aj["perfiles_ronda"])
    inicio = int(tendencias.get("siguiente_perfil", 0)) % len(todos)
    elegidos = (todos[inicio:] + todos[:inicio])[:n] if not a.solo else todos
    tendencias["siguiente_perfil"] = (inicio + n) % len(todos)

    # 1. Los ojos
    pasos = plan(elegidos, tendencias, aj)
    if a.vista:
        with open(a.vista, encoding="utf-8") as f:
            vista = json.load(f)
    elif pasos:
        try:
            vista = mirar(pasos)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
            print(f"ojeador: {e}; se intenta en la siguiente ronda")
            vista = {"pasos": []}
    else:
        print("ojeador: todas las redes pidieron descanso hace poco; hoy toca esperar")
        vista = {"pasos": []}
    por_id = {x["id"]: x for x in pasos}
    fuentes = tendencias.setdefault("fuentes", {})
    tendencias["ultima_vista"] = [{k: r.get(k) for k in ("id", "estado", "http", "motivo", "cartel", "por_categoria",
                                                         "faltan", "fallos")} | {"videos": len(r.get("videos", []))}
                                  for r in vista.get("pasos", [])]
    for r in vista.get("pasos", []):
        tipo = (por_id.get(r["id"]) or {}).get("tipo") or r["id"].split("-")[0]
        antes = fuentes.get(tipo) or {}
        if r["estado"] == "vacia" and antes.get("estado") == "bien":
            continue                                  # una página sin vídeos no cambia lo que se sabe de la red
        nueva = {"estado": r["estado"], "fecha": privado.ahora(), "motivo": r.get("motivo")}
        if r["estado"] == "bloqueada":                # desde cuándo no deja mirar (el Archivo de casos lo vigila)
            nueva["bloqueada_desde"] = antes.get("bloqueada_desde") if antes.get("estado") == "bloqueada" \
                else privado.ahora()
        fuentes[tipo] = nueva

    # 2. Datos de cada vídeo nuevo (con caché, para no preguntar dos veces por lo mismo)
    conocidos = (privado.leer(os.path.join("estado", CACHE), {}) or {}).get("videos") or {}
    vistos_ahora, sin_datos_ig, pedidos_datos = [], 0, 0
    colas = [[(r, v) for v in r.get("videos", [])] for r in vista.get("pasos", [])]
    turnos = []                                       # por turnos: un vídeo de cada página, para que todas tengan cifras
    while any(colas):
        for cola in colas:
            if cola:
                turnos.append(cola.pop(0))
    for r, v in turnos:
        paso = por_id.get(r["id"]) or {}
        entrada = {"url": v["url"], "red": _red(v["url"]), "tipo": paso.get("tipo"), "perfil": paso.get("perfil"),
                   "categoria": v.get("categoria"), "tema": paso.get("tema"), "cifra_pagina": v.get("cifra")}
        clave_url = v["url"]
        if clave_url in conocidos:
            entrada.update(conocidos[clave_url])
        elif pedidos_datos < int(aj["datos_ronda"]) and not (entrada["red"] == "instagram" and sin_datos_ig >= 2):
            pedidos_datos += 1
            d = datos(v["url"])
            time.sleep(1.5)
            if d:
                conocidos[clave_url] = dict({k: x for k, x in d.items() if k != "texto"}, leido=privado.ahora())
                entrada.update(d)
            elif entrada["red"] == "instagram":
                sin_datos_ig += 1
        vistos_ahora.append(entrada)
    corte = _ahora() - dt.timedelta(days=2)
    conocidos = dict(sorted(((u, d) for u, d in conocidos.items() if (_fecha(d.get("leido")) or _ahora()) >= corte),
                            key=lambda x: x[1].get("leido", ""))[-700:])
    privado.guardar_estado(CACHE, {"videos": conocidos})
    con_datos = [v for v in vistos_ahora if v.get("visitas")]
    print(f"ojeador: {len(vistos_ahora)} vídeos vistos en las páginas, {len(con_datos)} con cifras "
          f"({pedidos_datos} preguntadas ahora)")

    # Lo que más se repite en todo TikTok e Instagram (los últimos 2 días)
    recientes = list(conocidos.values())
    canciones, hashtags = recuento(recientes)
    top = sorted((v for v in recientes if v.get("visitas_dia")), key=lambda v: v["visitas_dia"], reverse=True)[:15]
    tendencias.update(ultimo=privado.ahora(), canciones=canciones, hashtags=hashtags,
                      top=[{k: v.get(k) for k in ("red", "url", "creador", "titulo", "visitas", "likes", "comentarios",
                                                  "dias", "visitas_dia", "segundos", "cancion")} for v in top])
    explorar = [v for v in vistos_ahora if v.get("tipo") == "tiktok-explorar" and v.get("visitas_dia")]
    por_categoria = collections.defaultdict(list)
    for v in explorar:
        por_categoria[v.get("categoria") or "Todo"].append(v)
    if por_categoria:
        tendencias["categorias"] = {c: {"videos": len(vs), "visitas_dia_media": int(sum(x["visitas_dia"] for x in vs) / len(vs)),
                                        "fecha": privado.ahora()} for c, vs in por_categoria.items()}

    # 3 y 4. Para cada perfil: sus candidatos, la IA ve los mejores y se resume lo que funciona
    resumen_ronda = []
    for perfil in elegidos:
        clave, alias = perfil["clave"], privado.alias(perfil["clave"])
        estado = leer(clave)
        suyos = [v for v in con_datos if v.get("perfil") == clave
                 or (v.get("tipo") == "tiktok-explorar" and v.get("categoria") in perfil["categorias"])]
        vistos = set(estado.get("vistos", []))
        cupo = min(int(aj["ia_ronda"]) - sum(x["vistos_ia"] for x in resumen_ronda),
                   int(aj["ia_dia"]) - int(ia["vistos"]), 1)
        nuevos = []
        for n, v in enumerate(elegir(suyos, vistos, max(0, cupo), int(aj["minimo"])) if not a.sin_ver else [], 1):
            entrada = dict(v, visto=privado.ahora())
            entrada.pop("perfil", None)
            with tempfile.TemporaryDirectory() as tmp:
                archivo = bajar(v["url"], tmp, int(aj["max_mb"]))
                if not archivo:
                    entrada["sin_ver"] = "no se ha podido bajar"
                else:
                    donde = {"tiktok-explorar": f"TikTok, Explorar ({v.get('categoria') or 'Todo'})",
                             "tiktok-temas": f"TikTok, el tema «{v.get('tema')}»",
                             "instagram": f"Instagram, los reels de «{v.get('tema')}»"}.get(v.get("tipo"), v["red"])
                    try:
                        analisis = gemini.preguntar(VER.format(
                            red="TikTok" if v["red"] == "tiktok" else "Instagram", donde=donde, nombre=perfil["nombre"],
                            tema=perfil["tema"], visitas=v.get("visitas"), dias=v.get("dias"),
                            por_dia=v.get("visitas_dia"), likes=v.get("likes"), comentarios=v.get("comentarios"),
                            idioma=IDIOMAS.get(perfil["idioma"], perfil["idioma"])) + lecciones,
                            video=archivo, ligero_primero=True, temperatura=0.4)   # los buenos, para los jueces
                        if isinstance(analisis, list) and analisis:
                            analisis = analisis[0]
                        if isinstance(analisis, dict):
                            entrada["analisis"] = analisis
                            ia["vistos"] = int(ia["vistos"]) + 1
                    except gemini.SinIA as e:
                        entrada["sin_ver"] = str(e)[:160]
            nuevos.append(entrada)
            print(f"ojeador: {alias} vídeo {n}: {'visto' if entrada.get('analisis') else 'sin ver'}", flush=True)
            time.sleep(PAUSA_IA)
        sin_pagina = [(por_id.get(r["id"]) or {}).get("tema") for r in vista.get("pasos", [])
                      if (por_id.get(r["id"]) or {}).get("perfil") == clave and r["estado"] == "vacia"
                      and (por_id.get(r["id"]) or {}).get("tipo") == "tiktok-temas"]
        if sin_pagina:
            estado.setdefault("temas_vacios", {}).update({t: privado.ahora() for t in sin_pagina if t})
        estado.update(clave=clave, alias=alias, nombre=perfil["nombre"], idioma=perfil["idioma"], tema=perfil["tema"],
                      en_pausa=perfil["pausa"], temas=perfil["temas"], categorias=perfil["categorias"],
                      siguiente=int(estado.get("siguiente", 0)) + 1, ultimo=privado.ahora())
        estado["vistos"] = (estado.get("vistos", []) + [v["id"] for v in nuevos if v.get("analisis")])[-600:]
        hace = _ahora() - dt.timedelta(days=21)
        ids_nuevos = {v["id"] for v in nuevos}
        estado["videos"] = [v for v in estado.get("videos", []) if v["id"] not in ids_nuevos
                            and (_fecha(v.get("visto")) or _ahora()) >= hace]
        estado["videos"] = (estado["videos"] + nuevos)[-40:]
        estado["top_ahora"] = [{k: v.get(k) for k in ("red", "url", "creador", "titulo", "visitas", "likes", "dias",
                                                      "visitas_dia", "segundos", "cancion")}
                               for v in sorted(suyos, key=lambda x: x.get("visitas_dia") or 0, reverse=True)[:8]]
        estado["instagram_pagina"] = [{"url": v["url"], "cifra": v.get("cifra_pagina"), "tema": v.get("tema")}
                                      for v in vistos_ahora if v.get("perfil") == clave and v["red"] == "instagram"
                                      and not v.get("visitas")][:12] or estado.get("instagram_pagina", [])
        estado["historial"] = (estado.get("historial", []) + [{"fecha": privado.ahora(), "candidatos": len(suyos),
                                                                "vistos_ia": sum(1 for v in nuevos if v.get("analisis"))}])[-60:]
        buenos = [v for v in estado["videos"] if v.get("analisis") and _encaja(v["analisis"]) >= 30]
        vistos_ia = sum(1 for v in nuevos if v.get("analisis"))
        if vistos_ia and buenos:
            try:
                estado["resumen"] = resumir(perfil, buenos[-12:], tendencias, lecciones)
                receta(perfil, estado)
            except gemini.SinIA as e:
                print(f"ojeador: {alias} sin resumen esta vez ({type(e).__name__})", flush=True)
        privado.guardar_estado(os.path.join(CARPETA, f"{alias}.json"), estado)
        resumen_ronda.append({"perfil": alias, "candidatos": len(suyos), "vistos_ia": vistos_ia})
        print(f"ojeador: {alias} → {len(suyos)} candidatos, {vistos_ia} vistos con la IA", flush=True)

    tendencias["ia"] = ia
    tendencias["rondas"] = (tendencias.get("rondas", []) + [{"fecha": privado.ahora(),
                                                              "fuentes": {k: v.get("estado") for k, v in fuentes.items()},
                                                              "vistos": len(vistos_ahora), "con_cifras": len(con_datos),
                                                              "perfiles": resumen_ronda}])[-40:]
    privado.guardar_estado(TENDENCIAS, tendencias)
    cuaderno.apuntar("ronda", {"fuentes": {k: v.get("estado") for k, v in fuentes.items()}, "vistos": len(vistos_ahora),
                               "con_cifras": len(con_datos), "perfiles": resumen_ronda})
    cuaderno.guardar()
    gemini.apuntar_portero()
    estados = ", ".join(f"{k}: {v.get('estado')}" for k, v in sorted(fuentes.items()))
    print(f"ojeador: fuentes → {estados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
