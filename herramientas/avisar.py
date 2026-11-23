"""Manda un aviso al móvil del dueño, gratis. Es el Cartero de la Ciudad Central.

Dos caminos gratis (usa el que tenga secretos puestos; si están los dos, manda por los dos):
  · ntfy: la app «ntfy» en el móvil, suscrita a un tema secreto. Secreto NTFY_TEMA (un nombre largo y raro).
  · Telegram: un bot creado con @BotFather. Secretos TELEGRAM_TOKEN y TELEGRAM_CHAT.

Uso:  python avisar.py "Título" "Mensaje" [--prioridad alta] [--enlace https://...] [--urgente] [--prueba]
Por la noche (00:00-08:00, hora de España) solo salen los --urgente; el resto espera a la mañana.
"""
import argparse, datetime as dt, json, os, sys, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

PRIORIDAD = {"baja": "2", "normal": "3", "alta": "4", "maxima": "5"}


def enviar(url, datos, cabeceras):
    req = urllib.request.Request(url, data=datos, headers=cabeceras, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("titulo")
    p.add_argument("mensaje")
    p.add_argument("--prioridad", choices=PRIORIDAD, default="normal")
    p.add_argument("--enlace")
    p.add_argument("--urgente", action="store_true")
    p.add_argument("--prueba", action="store_true")
    a = p.parse_args()
    hora = dt.datetime.now(ZoneInfo("Europe/Madrid")).hour
    if hora < 8 and not a.urgente:
        print("Es de noche en España: el aviso no se manda ahora (no es urgente).")
        return 0
    tema, token, chat = os.environ.get("NTFY_TEMA"), os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT")
    if not (tema or (token and chat)) and not a.prueba:
        sys.exit("No hay ningún camino configurado: falta NTFY_TEMA o TELEGRAM_TOKEN y TELEGRAM_CHAT.")
    hechos = []
    if tema or a.prueba:
        # título, prioridad y enlace van en la dirección: así las tildes y la ñ llegan bien
        opciones = {"title": a.titulo, "priority": PRIORIDAD[a.prioridad],
                    "tags": "rotating_light" if a.urgente else "city_sunset"}
        if a.enlace:
            opciones["click"] = a.enlace
        if a.prueba:
            print("PRUEBA ntfy →", json.dumps(opciones, ensure_ascii=False), "|", a.mensaje)
        else:
            url = f"https://ntfy.sh/{urllib.parse.quote(tema)}?" + urllib.parse.urlencode(opciones)
            enviar(url, a.mensaje.encode("utf-8"), {"Content-Type": "text/plain; charset=utf-8"})
            hechos.append("ntfy")
    if token and chat:
        texto = f"{a.titulo}\n{a.mensaje}" + (f"\n{a.enlace}" if a.enlace else "")
        datos = urllib.parse.urlencode({"chat_id": chat, "text": texto}).encode()
        if a.prueba:
            print("PRUEBA telegram →", texto)
        else:
            enviar(f"https://api.telegram.org/bot{token}/sendMessage", datos,
                   {"Content-Type": "application/x-www-form-urlencoded"})
            hechos.append("telegram")
    print("OK aviso enviado por " + ", ".join(hechos) if hechos else "OK (prueba, no se ha enviado nada)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
