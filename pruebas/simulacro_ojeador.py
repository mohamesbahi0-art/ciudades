"""Simulacro del Ojeador de redes con ojos, cifras e IA de mentira (sin navegador, sin red y sin secretos).
Comprueba que hace el plan de páginas, que lee las cifras una sola vez, que la IA ve como mucho un vídeo por perfil, que
lo que funciona llega a la receta de cada perfil (junto a la del Radar), que saca las canciones y hashtags que más se
repiten y que, si una red dice que no, la deja en paz y no vuelve a abrirla en la ronda siguiente.

    python pruebas/simulacro_ojeador.py
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="simulacro-ojeador-")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), os.path.join(TMP, "privado"))
os.environ["PRIVADO"] = os.path.join(TMP, "privado")
os.environ["MEMORIA_DIR"] = os.path.join(TMP, "privado", "memoria")
os.environ["OJEADOR_PAUSA"] = "0"

from bots.comun import gemini, privado  # noqa: E402
from bots.influencers import ojeador  # noqa: E402

ruta = os.path.join(TMP, "privado", "config", "canales.json")
cfg = json.load(open(ruta, encoding="utf-8"))
cfg["canales"]["gta"]["ojeador"] = {"categorias": ["Juegos"], "temas": ["gta 6", "gta 6 noticias"]}
cfg["canales"]["terror"]["ojeador"] = {"categorias": ["Drama"], "temas": ["historias de terror"]}
cfg["barrios"]["barrio.prueba"]["ojeador"] = {"categorias": ["Educación"], "temas": ["dinero", "ahorrar dinero"]}
json.dump(cfg, open(ruta, "w", encoding="utf-8"), ensure_ascii=False)
os.makedirs(os.path.join(TMP, "privado", "estado", "influencers"), exist_ok=True)
json.dump({"canales": {"gta": {"fecha": "2026-11-20T00:00:00Z", "radar": {"fecha": "2026-11-22T00:00:00Z", "temas": ["x"]}}}},
          open(os.path.join(TMP, "privado", "estado", "influencers", "recetas.json"), "w"))

MODO = {"instagram": "bien"}
PLANES, PEDIDAS, VISTOS_IA = [], [], []


def falso_mirar(pasos):
    PLANES.append([p["id"] for p in pasos])
    salida = []
    for p in pasos:
        if p["tipo"] == "instagram" and MODO["instagram"] == "bloqueada":
            salida.append({"id": p["id"], "estado": "bloqueada", "motivo": "http 429", "videos": []})
            continue
        videos = []
        for categoria in (p.get("categorias") or [None]):
            for n in range(4):
                base = "https://www.instagram.com/reel/" if p["tipo"] == "instagram" else "https://www.tiktok.com/@c{}/video/"
                url = (base.format(n) if "{}" in base else base) + hashlib.md5(f"{p['id']}{categoria}{n}".encode()).hexdigest()[:10]
                videos.append({"url": url, "texto": "1,2 M", "cifra": "1,2 M", "categoria": categoria})
        salida.append({"id": p["id"], "estado": "bien", "videos": videos})
    return {"pasos": salida}


def falsos_datos(url):
    PEDIDAS.append(url)
    if "instagram.com" in url:
        return None                                   # Instagram no da cifras sin cuenta
    h = int(hashlib.md5(url.encode()).hexdigest(), 16)
    canciones = ["Canción A - Artista", "Canción B - Otro", "original sound"]
    return {"id": url.rsplit("/", 1)[-1], "red": "tiktok", "url": url, "creador": f"creador{h % 7}",
            "titulo": "vídeo de prueba", "texto": "texto #dinero #fyp #ahorro", "hashtags": ["dinero", "fyp", "ahorro"],
            "cancion": canciones[h % 3], "segundos": 20 + h % 40, "visitas": 50000 + h % 900000, "likes": 4000,
            "comentarios": 120, "compartidos": 30, "subido": "2026-11-20T10:00:00Z", "dias": 3.0,
            "visitas_dia": (50000 + h % 900000) // 3, "interaccion": 0.08}


def falso_bajar(url, carpeta, max_mb):
    archivo = os.path.join(carpeta, "video.mp4")
    open(archivo, "wb").write(b"0" * 1000)
    return archivo


def falso_gemini(texto, imagenes=(), video=None, **kw):
    if "Mira este vídeo" in texto:
        VISTOS_IA.append(video)
        assert video and os.path.exists(video), "la IA tiene que recibir el vídeo"
        return {"gancho": {"texto": "¿Sabías que…?", "que_se_ve": "cara de sorpresa"}, "tema": "ahorro",
                "formato": "dato", "estilo_visual": "texto grande", "ritmo": "rápido", "voz_y_musica": "voz",
                "estructura": ["gancho", "dato"], "final": "pregunta", "por_que_funciona": "sorprende",
                "idea_para_nosotros": {"titulo": "idea", "gancho": "Hoy...", "resumen": "..."}, "encaja": 80}
    if "lo que funciona ahora en TikTok e Instagram" in texto:
        assert "Canción" in texto, "el resumen tiene que conocer las canciones que más se repiten"
        return {"titular": "Datos rápidos con cara de sorpresa", "lo_que_funciona": ["gancho en 1 s"], "ganchos": ["¿Sabías…?"],
                "temas": ["ahorro"], "formato": "dato", "duracion": "25", "evitar": ["intros largas"],
                "sonidos": ["Canción A"], "ideas": [{"titulo": "i", "gancho": "g", "resumen": "r"}]}
    raise AssertionError("pregunta inesperada a la IA")


ojeador.mirar = falso_mirar
ojeador.datos = falsos_datos
ojeador.bajar = falso_bajar
ojeador.time.sleep = lambda s: None
gemini.preguntar = falso_gemini
gemini.apuntar_portero = lambda: None


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


# Ronda 1: todo deja mirar
ojeador.main([])
t = privado.leer("estado/influencers/ojeador/tendencias.json")
plan1 = PLANES[-1]
comprobar(plan1[0] == "tiktok-explorar" and any(p.startswith("instagram-") for p in plan1), "plan: Explorar, temas e Instagram")
comprobar(all("barrio.prueba" not in p for p in plan1), "en el plan (y en el registro) solo salen alias")
comprobar(len(VISTOS_IA) <= 3, f"la IA ve como mucho 3 vídeos por ronda ({len(VISTOS_IA)})")
comprobar(t["canciones"] and t["canciones"][0]["nombre"].startswith("Canción"), "sale la canción que más se repite")
comprobar(all(h["nombre"] not in ("fyp", "viral") for h in t["hashtags"]), "los hashtags de relleno no cuentan")
comprobar(t["ia"]["vistos"] == len(VISTOS_IA), "cuenta lo que la IA ha visto hoy")
recetas = privado.leer("estado/influencers/recetas.json")["canales"]
con_ojeador = [k for k, r in recetas.items() if r.get("ojeador")]
comprobar(con_ojeador, f"lo que funciona llega a la receta ({', '.join(privado.alias(k) for k in con_ojeador)})")
comprobar(recetas["gta"].get("radar"), "la parte del Radar de nichos se queda en la receta")
ig = sum(1 for u in PEDIDAS if "instagram" in u)
comprobar(ig <= 2, f"Instagram sin cifras: deja de preguntar enseguida ({ig})")

# Ronda 2: Instagram dice que no
MODO["instagram"] = "bloqueada"
pedidas_antes = len(PEDIDAS)
ojeador.main([])
t = privado.leer("estado/influencers/ojeador/tendencias.json")
comprobar(t["fuentes"]["instagram"]["estado"] == "bloqueada", "Instagram dijo que no: apuntado")
repetidas = [u for u in PEDIDAS[pedidas_antes:] if u in PEDIDAS[:pedidas_antes]]
comprobar(not repetidas, "las cifras ya leídas no se vuelven a pedir")

# Ronda 3: a Instagram se le deja en paz
ojeador.main([])
comprobar(not any(p.startswith("instagram-") for p in PLANES[-1]), "ronda siguiente: no vuelve a abrir Instagram")
comprobar(len(VISTOS_IA) <= 8, f"en todo el día la IA ve como mucho 8 vídeos ({len(VISTOS_IA)})")
estado = [f for f in os.listdir(os.path.join(TMP, "privado", "estado", "influencers", "ojeador")) if not f.startswith("_")]
comprobar(len(estado) >= 3, f"cada perfil tiene su ficha y hay tendencias ({len(estado)} ficheros)")
shutil.rmtree(TMP, ignore_errors=True)
print("Simulacro del Ojeador de redes: todo bien")
