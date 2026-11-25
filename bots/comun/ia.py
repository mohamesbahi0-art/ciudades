"""Quién piensa cada trabajo de la fábrica.

- guionista e ideas: Claude primero (de pago, con los créditos del plan del dueño) y, si no puede o se ha gastado la
  parte del día, la IA gratis (Gemini y, detrás, sus suplentes y la cadena de reserva);
- juez y jurado: Gemini de primera (gratis, un jurado distinto del que escribe y que además oye la voz); si no le queda
  cupo, los suplentes gratis (la segunda fila de Google y la cadena) y, si tampoco, Claude;
- lo demás (radar, analista, discoteca…) sigue llamando a la IA gratis directamente.
Los suplentes valen para todo menos para APROBAR un vídeo: eso solo lo hace un juez de primera (Gemini de primera o
Claude). Por eso el Juzgado pide la confirmación con `solo_primera=True` y mira es_suplente().
Mismo contrato que gemini.preguntar: devuelve el JSON y, si nadie contesta, lanza gemini.SinIA.
Qué cerebro pensó la última vez: quien() → {"motor": "claude"|"gemini"|"gemma"|"groq"…, ...}.
"""
from bots.comun import claude, gemini

SinIA = gemini.SinIA
ULTIMO = {}
SOLO_CLAUDE = False        # el turno lo enciende en las cuentas donde la Élite ha visto que el guion gratis no llega
ESCRIBEN = ("guionista", "arreglo")


DE_PRIMERA = ("claude",) + tuple(gemini.DE_PRIMERA)


def quien():
    return dict(ULTIMO)


def es_suplente(motor=None):
    """¿Contestó un suplente (la segunda fila o la cadena de reserva) y no un cerebro de primera?"""
    return str(motor or ULTIMO.get("motor") or "gemini") not in DE_PRIMERA


def hay_de_primera(papel="juez"):
    """¿Hay ahora un cerebro de primera para ese papel? Gemini de primera con cupo (según la última ronda: no se gasta
    una pregunta en comprobarlo) o Claude con presupuesto."""
    try:
        if not gemini.primera_agotada():
            return True
    except Exception:
        pass
    try:
        return bool(claude.puede(papel))
    except Exception:
        return False


def _con_claude(texto, papel, kw):
    r = claude.preguntar(texto, papel, imagenes=kw.get("imagenes", ()), json_salida=kw.get("json_salida", True),
                         sin_audio=bool(kw.get("audio")))
    ULTIMO.clear()
    ULTIMO.update(claude.ULTIMO)
    return r


def _con_gemini(texto, papel, kw):
    r = gemini.preguntar(texto, **kw)
    ULTIMO.clear()
    ULTIMO.update(motor=gemini.QUIEN.get("servicio", "gemini"), papel=papel)      # «gemini» o el servicio de reserva
    return r


def preguntar(texto, papel=None, solo_primera=False, **kw):
    """papel: «guionista», «ideas», «juez»… (o nada: la IA gratis). El resto de opciones, como en gemini.preguntar.
    solo_primera: solo cerebros de primera (Gemini de primera o Claude); lo usa el Juzgado para confirmar un aprobado."""
    try:
        a = claude.ajustes() if papel else {}
    except Exception:
        a = {}
    if solo_primera:
        try:
            return _con_gemini(texto, papel, dict(kw, fila="primera"))
        except gemini.SinIA as e:
            if papel and claude.puede(papel):
                try:
                    return _con_claude(texto, papel, kw)
                except claude.NoPuede as e2:
                    raise gemini.SinIA(f"{e} · Claude tampoco: {e2}") from e2
            raise
    if papel and claude.primero(papel, a) and claude.puede(papel):
        try:
            return _con_claude(texto, papel, kw)
        except claude.NoPuede as e:
            if SOLO_CLAUDE and papel in ESCRIBEN:
                raise gemini.SinIA(f"esta cuenta solo escribe con Claude y ahora no puede ({e})") from e
            print(f"cerebro: Claude no ha podido ({e}); piensa la IA gratis", flush=True)
        return _con_gemini(texto, papel, kw)
    if SOLO_CLAUDE and papel in ESCRIBEN:
        raise gemini.SinIA("esta cuenta solo escribe con Claude y ahora no tiene presupuesto: espera a su hora")
    if not (papel and claude.de_reserva(papel, a)):
        return _con_gemini(texto, papel, kw)
    # Con Claude de reserva (jueces y jurado): Gemini de primera → los suplentes gratis → Claude. Así el dinero de
    # Claude no se va en suspender vídeos flojos: queda para confirmar los que un suplente da por buenos.
    try:
        return _con_gemini(texto, papel, dict(kw, fila="primera"))
    except gemini.SinIA as e:
        try:
            r = _con_gemini(texto, papel, dict(kw, fila="segunda"))
            print(f"cerebro: Gemini de primera no contesta; piensa un suplente gratis ({ULTIMO.get('motor')})", flush=True)
            return r
        except gemini.SinIA as e2:
            if claude.puede(papel):
                print("cerebro: ni Gemini ni los suplentes contestan; piensa Claude", flush=True)
                try:
                    return _con_claude(texto, papel, kw)
                except claude.NoPuede as e3:
                    raise gemini.SinIA(f"{e} · los suplentes: {e2} · Claude: {e3}") from e3
            raise gemini.SinIA(f"{e} · y los suplentes tampoco: {e2}") from e2
