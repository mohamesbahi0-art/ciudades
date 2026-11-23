"""Los huecos de cada canal: a qué hora sale el próximo vídeo.

Reglas del dueño:
- Solo se rellena DESPUÉS del último vídeo que ya está programado (los que dejó la fábrica antigua salen solos).
- Nunca más de un mes por delante sin preguntar.
- Cada canal sale a sus horas (hora de España); los de GTA, 3 al día como mucho (tienen 3 horas).
"""
import datetime as dt
from zoneinfo import ZoneInfo

ESPANA = ZoneInfo("Europe/Madrid")
MARGEN = dt.timedelta(minutes=90)      # lo que puede tardar en subirse; YouTube pide al menos 15 minutos


def fecha(texto):
    if not texto:
        return None
    if isinstance(texto, dt.datetime):
        return texto
    return dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))


def ocupados(revision, registro, cola, clave):
    """Todas las horas ya cogidas en un canal: lo programado en YouTube, lo que hemos subido y lo que espera en la cola."""
    horas = [fecha(p["sale"]) for p in (revision or {}).get("programados", [])]
    horas += [fecha(r["publica"]) for r in registro if r.get("canal") == clave and r.get("publica")]
    horas += [fecha(c["hora"]) for c in cola if c.get("canal") == clave and c.get("hora")]
    return sorted(h for h in horas if h)


def siguiente(horas_canal, ocupadas, ahora=None, dias_maximos=30):
    """El primer hueco libre del canal después de su último vídeo programado, o None si pasaría del mes."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    limite = ahora + dt.timedelta(days=dias_maximos)
    desde = max([ahora + MARGEN] + [h + dt.timedelta(minutes=30) for h in ocupadas])
    dia = desde.astimezone(ESPANA).date()
    while True:
        for hhmm in sorted(horas_canal):
            h, m = map(int, hhmm.split(":"))
            hueco = dt.datetime(dia.year, dia.month, dia.day, h, m, tzinfo=ESPANA).astimezone(dt.timezone.utc)
            if hueco > limite:
                return None
            if hueco >= desde:
                return hueco
        dia += dt.timedelta(days=1)


def colchon(ocupadas, ahora=None):
    """Cuántos días de vídeos le quedan al canal (0 si no tiene ninguno programado)."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    futuros = [h for h in ocupadas if h > ahora]
    return max(0.0, (max(futuros) - ahora).total_seconds() / 86400) if futuros else 0.0


def iso(h):
    return h.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
