"""Simulacro del Radar de nichos: YouTube y Gemini DE MENTIRA (sin secretos ni internet).
Comprueba que el Radar elige los que más crecen (uno por creador, sin repetir), que Gemini los «ve», que deja el
resumen en la receta de los guionistas, que apunta la cuota que gasta y que no pasa del tope del día.

    cp -r pruebas/privado_ejemplo /tmp/privado3
    PRIVADO=/tmp/privado3 MEMORIA_DIR=/tmp/privado3/memoria python pruebas/simulacro_radar.py
"""
import datetime as dt
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ.setdefault("PRIVADO", os.path.join(RAIZ, "pruebas", "privado_ejemplo"))
os.environ.setdefault("MEMORIA_DIR", os.path.join(os.environ["PRIVADO"], "memoria"))
from bots.central import buscador_clips, subidor  # noqa: E402
from bots.comun import gemini, privado  # noqa: E402
from bots.influencers import estudio, radar  # noqa: E402

PRIV = privado.carpeta()
assert "privado_ejemplo" not in os.path.abspath(PRIV) or os.environ.get("SIMULACRO_EN_SITIO"), \
    "copia antes pruebas/privado_ejemplo a otra carpeta (el simulacro escribe en ella)"

# --- la config de ejemplo, con nicho para un barrio y un canal ---------------------------------------------------
ruta_cfg = os.path.join(PRIV, "config", "canales.json")
cfg = json.load(open(ruta_cfg, encoding="utf-8"))
cfg["barrios"]["barrio.prueba"]["nicho"] = {"busquedas": ["motivación animada", {"q": "motivation", "idioma": "en",
                                                                                 "region": "US"}], "region": "ES"}
cfg["canales"]["gta"]["nicho"] = {"busquedas": ["videojuego noticias"], "cada": 3}
cfg["canales"]["gta"]["id"] = "NUESTRO"            # nuestro propio canal: el Radar no se estudia a sí mismo
json.dump(cfg, open(ruta_cfg, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


class _Hecho:
    def __init__(self, datos):
        self.datos = datos

    def execute(self):
        return self.datos


class FalsoYouTube:
    def __init__(self):
        self.busquedas = []

    def search(self):
        yt = self

        class Busqueda:
            def list(self, **kw):
                assert kw["type"] == "video" and kw["videoDuration"] == "short" and kw["order"] == "viewCount", kw
                yt.busquedas.append(kw)
                base = len(yt.busquedas) * 100
                return _Hecho({"items": [{"id": {"videoId": f"v{base + i}"}} for i in range(10)]})
        return Busqueda()

    def videos(self):
        yt = self

        class Videos:
            def list(self, id, part):
                ahora = dt.datetime.now(dt.timezone.utc)
                idioma = yt.busquedas[-1].get("relevanceLanguage", "es")
                items = []
                for n, vid in enumerate(id.split(",")):
                    canal = "NUESTRO" if n == 0 else f"C{n % 4}"          # el más visto es nuestro: fuera
                    items.append({"id": vid, "snippet": {
                        "title": f"Vídeo {vid}", "channelTitle": f"Creador {canal}", "channelId": canal,
                        "publishedAt": (ahora - dt.timedelta(days=1 + n)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "defaultAudioLanguage": "fr" if n == 1 else idioma, "liveBroadcastContent": "none"},
                        "contentDetails": {"duration": "PT9M" if n == 2 else "PT35S"},
                        "statistics": {"viewCount": str(900000 // (n + 1)), "likeCount": "10", "commentCount": "2"}})
                return _Hecho({"items": items})
        return Videos()


YT = FalsoYouTube()
buscador_clips.servicio = lambda: YT
VISTOS = []


def falso_ver(url, texto, **kw):
    assert url.startswith("https://www.youtube.com/watch?v="), url
    assert "nunca copiar" in texto
    VISTOS.append(url)
    return {"gancho": {"texto": "¿Sabías que…?", "que_se_ve": "un muñeco bajo un foco"}, "tema": "disciplina",
            "formato": "historia de famoso", "estilo_visual": "animación 2D", "ritmo": "cortes cada 2 s",
            "voz_y_musica": "voz grave y piano", "estructura": ["gancho", "giro", "pregunta"], "final": "pregunta",
            "por_que_funciona": "promete un secreto", "encaja": 0 if len(VISTOS) == 2 else 80,
            "idea_para_nosotros": {"titulo": "t", "gancho": "g", "resumen": "r"}}


RESUMENES = []


def falso_preguntar(texto, imagenes=(), **kw):
    if texto.startswith("Eres el Radar de nichos"):
        RESUMENES.append(texto)
        return {"titular": "Gana la historia de famoso con pregunta final", "lo_que_funciona": ["gancho con secreto"],
                "ganchos": ["¿Sabías que…?"], "temas": ["disciplina"], "formato": "historia de famoso",
                "duracion": "25", "evitar": ["intros largas"], "ideas": [{"titulo": "t", "gancho": "g", "resumen": "r"}]}
    if "Analistas" in texto or "Recetario" in texto or "RECETA" in texto:
        return {"titulo": "fórmula", "gancho": "pregunta", "duracion": "25", "ritmo": "rápido", "final": "pregunta",
                "palabras_clave": ["a"], "hashtags": ["#a"], "evitar": []}
    return {"resumen": "ok", "titulo": "fórmula", "gancho": "pregunta", "duracion": "25"}


gemini.ver_youtube = falso_ver
gemini.preguntar = falso_preguntar


def leer(ruta):
    return json.load(open(os.path.join(PRIV, ruta), encoding="utf-8"))


# 1) Primera pasada: los dos perfiles, 3 vídeos cada uno, sin el nuestro, sin el francés, sin el de 9 minutos
radar.main(["--todos"])
assert len(YT.busquedas) == 2, YT.busquedas
b1 = leer("estado/influencers/radar/barrio-1.json")
g1 = leer("estado/influencers/radar/gta.json")
for r in (b1, g1):
    ids = [v["id"] for v in r["videos"]]
    assert len(ids) == 3, ids
    assert not any(i.endswith(("00", "01", "02")) for i in ids), ids    # nuestro, francés y largo: fuera
    assert len({v["canal_id"] for v in r["videos"]}) == 3                # uno por creador
    assert r["resumen"]["titular"] and r["top_ahora"] and r["historial"]
assert "NUESTRO" not in json.dumps(b1["top_ahora"])
assert YT.busquedas[0]["relevanceLanguage"] == "es" and YT.busquedas[0]["regionCode"] == "ES"
recetas = leer("estado/influencers/recetas.json")["canales"]
assert recetas["barrio.prueba"]["radar"]["lo_que_funciona"] and recetas["gta"]["radar"]["ejemplos"], recetas
assert subidor.gastado("radar_nichos") == 202, subidor.cuota()
assert RESUMENES[0].count("\n- «") == 2, "el vídeo que Gemini dijo que no encaja no entra en el resumen"
print("  primera pasada: 2 perfiles, 6 vídeos vistos, receta y cuota apuntadas")

# 2) Hoy ya no les toca (sin --todos): no gasta nada
radar.main([])
assert len(YT.busquedas) == 2, "no tenía que buscar: hoy ya había mirado"
print("  segunda pasada: hoy ya no le toca a nadie")

# 3) Tope del día: con 303 unidades (ya ha gastado 202), solo cabe una búsqueda más
ruta_aj = os.path.join(PRIV, "config", "fabrica.json")
aj = json.load(open(ruta_aj, encoding="utf-8"))
json.dump(dict(aj, radar_unidades_dia=303), open(ruta_aj, "w", encoding="utf-8"))
radar.main(["--todos"])
assert len(YT.busquedas) == 3, YT.busquedas
assert subidor.gastado("radar_nichos") == 303
b2 = leer("estado/influencers/radar/barrio-1.json")
assert b2["historial"][-1]["idioma"] == "en", "la segunda búsqueda del barrio era la de inglés"
assert len({v["id"] for v in b2["videos"]}) == len(b2["videos"]) == 6, "no repite vídeos ya vistos"
print("  tercera pasada: respeta el tope de cuota del día y rota las búsquedas")

# 4) Si la cuota común se ha acabado, no busca nada
subidor.agotada()
radar.main(["--todos"])
assert len(YT.busquedas) == 3
print("  cuarta pasada: cuota agotada, el Radar no toca nada")

# 5) El Recetario no borra lo del Radar al escribir su receta
estudio._portada = lambda vid, carpeta: None
estudio.recetas("gta", {"q": "videojuego", "nombre": "gta"}, [{"id": "x", "titulo": "t", "visitas": 1, "segundos": 30}], ["a"])
assert leer("estado/influencers/recetas.json")["canales"]["gta"].get("radar"), "el Recetario ha borrado el Radar"
print("  el Recetario respeta lo que deja el Radar")

# 6) Dos turnos a la vez: el libro de cuota y las recetas se juntan sin perder nada
dia = subidor.cuota()["dia"]
j = privado.fusionar("estado/cuota.json", {"dia": dia, "subidas": 3, "intentos": 4, "otros": {"radar_nichos": 101}},
                     {"dia": dia, "subidas": 2, "intentos": 2, "otros": {"radar_nichos": 202, "otro": 5},
                      "agotada_hasta": None})
assert j["subidas"] == 3 and j["intentos"] == 4 and j["otros"] == {"radar_nichos": 202, "otro": 5}, j
j = privado.fusionar("estado/influencers/recetas.json",
                     {"canales": {"gta": {"gancho": "nuevo", "fecha": "2026-11-24T09:00:00Z",
                                          "radar": {"fecha": "2026-11-20T00:00:00Z", "v": 1}}}},
                     {"canales": {"gta": {"gancho": "viejo", "fecha": "2026-11-20T09:00:00Z",
                                          "radar": {"fecha": "2026-11-24T08:00:00Z", "v": 2}}, "terror": {"radar": {}}}})
assert j["canales"]["gta"]["gancho"] == "nuevo" and j["canales"]["gta"]["radar"]["v"] == 2 and "terror" in j["canales"], j
print("  las fusiones de la cuota y de las recetas no pierden nada")
print("simulacro del Radar de nichos: todo bien")
