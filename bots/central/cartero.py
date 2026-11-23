"""El Cartero: manda avisos gratis al móvil del dueño con ntfy, una app gratis y sin cuenta, suscrita a un tema secreto.

- Cuando hay un vídeo nuevo en «Para subir» (TikTok o Instagram): «🎬 Vídeo nuevo para subir».
- Cada tarde (cartero.yml, 19:41 UTC = 20:41 en España): el resumen del día (vídeos subidos, los que esperan, clips
  nuevos de la Videoteca y lo que lleva gastado Claude).
Los avisos no llevan nombres de cuentas ni nada privado, solo cifras y frases en sencillo. De noche (de 00:00 a 08:00
en España) solo salen los urgentes; si no hay tema configurado, no hace nada y la fábrica sigue igual.

El tema va en config/fabrica.json → "cartero": {"ntfy_tema": "...", "encendido": true} del repositorio privado (o en la
variable NTFY_TEMA). El dueño se suscribe a ese tema en la app ntfy.

Uso:  python bots/central/cartero.py resumen [--prueba]
      python bots/central/cartero.py aviso "Título" "Mensaje" [--urgente] [--prueba]
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import privado  # noqa: E402

PRIORIDAD = {"baja": "2", "normal": "3", "alta": "4", "maxima": "5"}
ENVIADOS = []          # lo que se ha mandado en este proceso (para las pruebas)


def ajustes():
    try:
        return (json.load(open(os.path.join(privado.carpeta(), "config", "fabrica.json"), encoding="utf-8"))
                .get("cartero") or {})
    except (OSError, ValueError):
        return {}


def tema():
    a = ajustes()
    if a.get("encendido") is False:
        return None
    return os.environ.get("NTFY_TEMA") or a.get("ntfy_tema")


def avisar(titulo, mensaje, prioridad="normal", urgente=False, etiqueta="city_sunset", prueba=False):
    """Manda el aviso. Devuelve True si ha salido. Nunca rompe nada: si falla, lo dice y sigue."""
    t = tema()
    if not t:
        return False
    if dt.datetime.now(ZoneInfo("Europe/Madrid")).hour < 8 and not urgente:
        return False                           # de noche, solo lo urgente
    opciones = {"title": titulo, "priority": PRIORIDAD.get(prioridad, "3"),
                "tags": "rotating_light" if urgente else etiqueta}
    ENVIADOS.append({"titulo": titulo, "mensaje": mensaje, "opciones": opciones})
    if prueba or os.environ.get("CARTERO_PRUEBA"):
        print(f"cartero (prueba): {titulo} · {mensaje}", flush=True)
        return True
    url = f"https://ntfy.sh/{urllib.parse.quote(t)}?" + urllib.parse.urlencode(opciones)
    try:
        req = urllib.request.Request(url, data=mensaje.encode("utf-8"), method="POST",
                                     headers={"Content-Type": "text/plain; charset=utf-8"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:
        print(f"cartero: no ha podido mandar el aviso ({type(e).__name__})", flush=True)
        return False


def video_para_subir(cuantos_esperan):
    """Un vídeo nuevo en «Para subir» (sin nombres de cuentas)."""
    return avisar("🎬 Vídeo nuevo para subir",
                  f"Hay un vídeo nuevo listo para TikTok e Instagram. Esperando en total: {cuantos_esperan}. "
                  "Lo tienes en la app, en «Para subir», con el texto y los hashtags.", etiqueta="clapper")


def resumen(prueba=False):
    """El resumen del día, en sencillo y sin nada privado."""
    hoy = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    registro = privado.leer(os.path.join("registro", "subidas.json"), []) or []
    subidos = [r for r in registro if str(r.get("fecha") or r.get("subido") or "").startswith(hoy)]
    if not subidos:                               # el registro puede no llevar fecha: lo cuenta la cuota del día
        cuota = privado.leer(os.path.join("estado", "cuota.json"), {}) or {}
        n_subidos = int(cuota.get("subidas") or 0) if cuota.get("dia") == hoy else 0
    else:
        n_subidos = len(subidos)
    esperan = 0
    carpeta = os.path.join(privado.carpeta(), "parasubir")
    if os.path.isdir(carpeta):
        for f in os.listdir(carpeta):
            try:
                d = json.load(open(os.path.join(carpeta, f), encoding="utf-8"))
            except (OSError, ValueError):
                continue
            esperan += isinstance(d, dict) and d.get("estado") == "pendiente"
    tomas = (privado.leer(os.path.join("estado", "clips", "videoteca.json"), {}) or {}).get("tomas") or []
    nuevas = sum(1 for t in tomas if str(t.get("entrada") or "").startswith(hoy))
    claude = (privado.leer(os.path.join("estado", "claude.json"), {}) or {}).get("resumen") or {}
    partes = [f"Vídeos subidos hoy a YouTube (cada uno sale a su hora): {n_subidos}.",
              f"Esperando en «Para subir»: {esperan}." if esperan else "Nada esperando en «Para subir».",
              f"Clips nuevos en la Videoteca: {nuevas} (en total {len(tomas)})."]
    if claude:
        partes.append(f"Claude lleva gastados {float(claude.get('mes_usd') or 0):.2f} $ este mes.")
    return avisar("🏙️ Tu fábrica hoy", " ".join(partes), prueba=prueba)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("que", choices=["resumen", "aviso"])
    p.add_argument("titulo", nargs="?")
    p.add_argument("mensaje", nargs="?")
    p.add_argument("--urgente", action="store_true")
    p.add_argument("--prueba", action="store_true")
    a = p.parse_args()
    if not tema():
        print("cartero: no hay tema de ntfy configurado; no se manda nada")
        return 0
    hecho = resumen(a.prueba) if a.que == "resumen" else avisar(a.titulo or "Aviso", a.mensaje or "", urgente=a.urgente,
                                                                 prueba=a.prueba)
    print("cartero: aviso enviado" if hecho else "cartero: no se ha mandado (de noche o sin tema)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
