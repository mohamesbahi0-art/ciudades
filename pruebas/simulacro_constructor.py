"""Simulacro del Constructor de canales con una IA de mentira (sin red ni secretos): un canal de YouTube nuevo y una cuenta
de TikTok e Instagram nueva. Comprueba la ficha, la entrada en la configuración (copiando lo técnico de la cuenta más
parecida), la foto y el banner, los pasos del dueño y que una cuenta nueva de TikTok espera a que el dueño vea su muestra.

    python pruebas/simulacro_constructor.py
"""
import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="simulacro-constructor-")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), os.path.join(TMP, "privado"))
os.environ["PRIVADO"] = os.path.join(TMP, "privado")
os.environ["MEMORIA_DIR"] = os.path.join(TMP, "privado", "memoria")
os.environ.pop("ANTHROPIC_API_KEY", None)
for k in [k for k in os.environ if k.startswith("YT_")]:
    os.environ.pop(k)

from bots.central import constructor  # noqa: E402
from bots.comun import almacen, gemini, privado  # noqa: E402

ESTANTE = os.path.join(TMP, "estanteria")
os.makedirs(ESTANTE)
almacen.guardar = lambda etiqueta, ruta, nombre=None: shutil.copy(ruta, os.path.join(ESTANTE, nombre or os.path.basename(ruta)))


def falso(texto, imagenes=(), **kw):
    assert "Constructor de canales" in texto, texto[:80]
    return {"tema": "acertijos y paradojas de lógica en menos de un minuto, con la respuesta al final",
            "descripcion": "Un acertijo cada día. ¿Lo resuelves antes que nadie? #shorts #acertijos #logica",
            "etiquetas": ["acertijos", "paradojas", "retos mentales", "lógica", "adivinanzas"],
            "estilo_dibujo": "clean flat illustration, puzzle pieces, bright colors",
            "busquedas": ["acertijos", "paradojas", "retos de lógica"], "ojeador_temas": ["acertijos", "retos"],
            "categorias": ["Educación"], "horas": ["20:00", "25:99"], "ideas": [f"Idea {i}" for i in range(10)],
            "colores": ["#1B1F3B", "#FFD43B"], "lema": "Un reto cada día"}


gemini.preguntar = falso


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


nuevos = os.path.join(os.environ["PRIVADO"], "config", "nuevos")
os.makedirs(nuevos)
json.dump({"alias": "nuevo-1", "red": "youtube", "clave": "acertijos", "nombre": "Piensa Rápido", "tema": "acertijos",
           "idioma": "es"}, open(os.path.join(nuevos, "nuevo-1.json"), "w", encoding="utf-8"))
json.dump({"alias": "nuevo-2", "red": "tiktok+instagram", "cuenta": "cuenta.prueba", "nombre": "Cuenta Prueba",
           "tema": "trucos de cocina", "idioma": "es"}, open(os.path.join(nuevos, "nuevo-2.json"), "w", encoding="utf-8"))

comprobar(constructor.main.__doc__ is None and len(constructor.peticiones()) == 2, "lee las 2 peticiones del privado")
r = constructor.construir(constructor.peticiones("nuevo-1")[0], paso=lambda t: None)
cfg = privado.config()
c = cfg["canales"].get("acertijos")
comprobar(bool(c) and c["nombre"] == "Piensa Rápido" and c["tema"].startswith("acertijos"), "crea el canal en la configuración")
comprobar(c["horas"] == ["20:00"], "solo guarda horas que existen")
comprobar(bool(c.get("voz")) and bool(c.get("descripcion")) and len(c["etiquetas"]) == 5, "copia la voz de la cuenta parecida y guarda descripción y etiquetas")
comprobar(r["estado"] == "construido" and not r["youtube"]["conectado"], "sin permiso de YouTube queda construido, esperando conexión")
comprobar(any("Crea el canal" in x for x in r["pasos_dueno"]) and r["pasos_claude"], "deja los pasos del dueño y de Claude")
from PIL import Image  # noqa: E402
comprobar(Image.open(os.path.join(ESTANTE, "nuevo-1-foto.png")).size == (800, 800), "foto de perfil de 800×800")
comprobar(Image.open(os.path.join(ESTANTE, "nuevo-1-banner.png")).size == (2560, 1440), "banner de 2560×1440")
comprobar(bool(privado.leer(os.path.join("estado", "constructor", "nuevo-1.json"))), "deja el resultado para la app")

r = constructor.construir(constructor.peticiones("nuevo-2")[0], paso=lambda t: None)
b = privado.config()["barrios"].get("cuentaprueba") or privado.config()["barrios"].get("cuenta.prueba")
comprobar(bool(b) and b["estado"] == "en_pausa" and "muestra" in b["motivo"], "la cuenta de TikTok espera a que el dueño vea su muestra")
comprobar(b["redes"] == ["instagram", "tiktok"], "con sus dos redes")
comprobar(any("primera muestra" in x for x in r["pasos_dueno"]), "pide al dueño que mire la primera muestra")
print("Simulacro del Constructor: todo bien")
