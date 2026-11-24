"""Quién piensa cada trabajo de la fábrica.

- guionista e ideas: Claude primero (de pago, con los créditos del plan del dueño) y, si no puede o se ha gastado la
  parte del día, Gemini gratis;
- juez: Gemini primero (gratis, un jurado distinto del que escribe y que además oye la voz) y Claude de reserva, para
  que la fábrica no se pare cuando Gemini se queda sin cupo;
- lo demás (radar, analista, discoteca…) sigue llamando a Gemini directamente.
Mismo contrato que gemini.preguntar: devuelve el JSON y, si nadie contesta, lanza gemini.SinIA.
Qué cerebro pensó la última vez: quien() → {"motor": "claude"|"gemini", ...}.
"""
from bots.comun import claude, gemini

SinIA = gemini.SinIA
ULTIMO = {}
SOLO_CLAUDE = False        # el turno lo enciende en las cuentas donde la Élite ha visto que el guion gratis no llega
ESCRIBEN = ("guionista", "arreglo")


def quien():
    return dict(ULTIMO)


def _con_claude(texto, papel, kw):
    r = claude.preguntar(texto, papel, imagenes=kw.get("imagenes", ()), json_salida=kw.get("json_salida", True),
                         sin_audio=bool(kw.get("audio")))
    ULTIMO.clear()
    ULTIMO.update(claude.ULTIMO)
    return r


def _con_gemini(texto, papel, kw):
    r = gemini.preguntar(texto, **kw)
    ULTIMO.clear()
    ULTIMO.update(motor="gemini", papel=papel)
    return r


def preguntar(texto, papel=None, **kw):
    """papel: «guionista», «ideas» o «juez» (o nada: Gemini). El resto de opciones, como en gemini.preguntar."""
    try:
        a = claude.ajustes() if papel else {}
    except Exception:
        a = {}
    if papel and claude.primero(papel, a) and claude.puede(papel):
        try:
            return _con_claude(texto, papel, kw)
        except claude.NoPuede as e:
            if SOLO_CLAUDE and papel in ESCRIBEN:
                raise gemini.SinIA(f"esta cuenta solo escribe con Claude y ahora no puede ({e})") from e
            print(f"cerebro: Claude no ha podido ({e}); piensa Gemini", flush=True)
        return _con_gemini(texto, papel, kw)
    if SOLO_CLAUDE and papel in ESCRIBEN:
        raise gemini.SinIA("esta cuenta solo escribe con Claude y ahora no tiene presupuesto: espera a su hora")
    try:
        return _con_gemini(texto, papel, kw)
    except gemini.SinIA as e:
        if papel and claude.de_reserva(papel, a) and claude.puede(papel):
            print(f"cerebro: Gemini no contesta ({str(e)[:80]}); piensa Claude", flush=True)
            try:
                return _con_claude(texto, papel, kw)
            except claude.NoPuede as e2:
                raise gemini.SinIA(f"{e} · Claude tampoco: {e2}") from e2
        raise
