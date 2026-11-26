"""El cerebro de pago: Claude (Anthropic), con los créditos de API que trae el plan del dueño cada mes (100 $ con el
plan Max; caducan al final de cada mes de facturación y no se guardan). Escribe ideas y guiones y, si Gemini no puede,
hace de juez. Hace falta el secreto ANTHROPIC_API_KEY; sin él, o sin presupuesto, la fábrica sigue con Gemini gratis
(quién piensa cada trabajo lo decide bots/comun/ia.py).

Para que los créditos duren el mes entero:
- apunta en dólares lo que cuesta cada llamada (estado/claude.json del repositorio privado);
- cada día solo gasta su parte: lo que queda del mes entre los días que faltan para que lleguen los créditos nuevos
  (config/fabrica.json → "claude": {"mes_usd": 100, "renueva_dia": 15}); si aún no se sabe el día, 1/30 del mes;
- si la cuenta se queda sin saldo, lo apunta y no lo vuelve a intentar hasta pasadas 20 horas (cuando llegan los
  créditos nuevos, vuelve solo).
Si Claude no quiere escribir algo por sus normas, el servicio prueba solo otro modelo (fallbacks "default"); si tampoco,
lo hace Gemini. Claude no oye: cuando juzga, mira los fotogramas y lee la narración. No admite «temperatura».
"""
import base64
import datetime as dt
import io
import json
import os

from bots.comun.gemini import SinIA

MODELO = "claude-opus-5-5"
# Dólares por millón de tokens: (entrada, salida, leer de la caché, escribir en la caché). Si contesta otro modelo
# (el de reserva cuando el primero se niega), se cuenta con el precio de ese.
PRECIOS = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5),
    "claude-fable-5-2": (8.0, 40.0, 0.20, 10.0),
    "claude-opus-5": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-8": (5.0, 25.0, 0.50, 6.25),
    "claude-sonnet-5": (2.0, 10.0, 0.20, 2.5),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
CARO = (10.0, 50.0, 1.0, 12.5)          # modelo que no está en la lista: se cuenta caro, por prudencia
DEFECTO = {
    "encendido": True,
    "modelo": MODELO,
    "mes_usd": 100.0,                    # lo que trae el plan cada mes
    "renueva_dia": None,                 # día del mes en que llegan los créditos nuevos (sale en la consola)
    "dia_max_usd": 6.0,                  # nunca más de esto en un día, aunque sobre
    # trabajos que piensa Claude primero, con su esfuerzo (low, medium, high, xhigh, max)
    # «titulos» son los gladiadores del Coliseo (título, texto y hashtags): con el modelo pequeño cuestan céntimos
    # «arreglo» es la versión corregida de un vídeo que el Juzgado suspendió por poco (el mismo guion, con sus fallos)
    # «elite» es el Arquitecto de la Élite cuando decide un cambio gordo (pocas veces al día, con su propia hucha)
    "papeles": {"guionista": "high", "ideas": "medium", "titulos": "low", "arreglo": "medium", "elite": "high"},
    # trabajos que piensa Gemini (gratis; el juez, además, es así de otro «jurado» y oye la voz) y Claude si Gemini no puede
    "reserva": {"juez": "medium", "jurado": "low"},
    # modelo de cada papel si no es el de siempre: el Jurado popular y el Coliseo van con el pequeño (40 veces más barato)
    "modelos": {"jurado": "claude-haiku-5-5", "titulos": "claude-haiku-5-5"},
    # reparto por horas: a cada hora del día (UTC) solo se puede llevar gastada su parte (más este adelanto), para que la
    # fábrica tenga IA las 24 horas en vez de gastarlo todo de madrugada
    "ritmo": True, "adelanto": 0.12,
    # adelanto propio de algún papel: arreglar un vídeo que casi aprueba es lo que más rinde, así que va por delante
    "adelantos": {"arreglo": 0.30, "juez": 0.20},
    # dólares de más para un día concreto ({"2026-11-24": 1.5}), para una prueba; salen del mismo mes, no cuestan aparte
    "extra_usd": {},
    # papeles con hucha propia al día, aparte del reparto de la fábrica (así la Élite puede decidir aunque la fábrica
    # haya gastado ya su parte; sale del mismo mes y nunca pasa del tope del mes)
    "aparte": {"elite": 1.0},
}
ESTADO = os.path.join("estado", "claude.json")
DIAS_DETALLE = 40                        # días que se guarda cada llamada (después, solo el total del día)
REINTENTO_SIN_SALDO = 20 * 3600
MARGEN = 0.05                            # lo mínimo que tiene que quedar hoy para hacer otra llamada
LADO_MAXIMO = 1280                       # fotos más grandes se achican (cada píxel cuesta)
SISTEMA = ("Trabajas dentro de una fábrica de vídeos cortos (YouTube Shorts, TikTok e Instagram) de un creador adulto "
           "que se hace responsable de lo que publica. Sigue al pie de la letra lo que pide el mensaje. Cuando pida un "
           "JSON, contesta SOLO con ese JSON, válido, sin texto antes ni después y sin bloques de código.")

APAGADO = None                           # motivo por el que en esta ronda ya no se usa (llave mala, sin saldo…)
RONDA = []                               # lo gastado en esta ronda, aunque el estado no se haya podido guardar
ULTIMO = {}                              # la última llamada: modelo, papel, dólares


class NoPuede(SinIA):
    """Claude no ha contestado (sin llave, sin saldo, se ha negado, caído…): piensa Gemini."""


def ajustes():
    from bots.comun import privado
    a = dict(DEFECTO)
    propios = (privado.ajustes() or {}).get("claude") or {}
    if isinstance(propios, dict):
        a.update(propios)
        for k in ("papeles", "reserva", "modelos", "adelantos", "aparte"):   # lo de la configuración se suma, no borra
            a[k] = dict(DEFECTO[k], **(propios.get(k) or {}))
    return a


def modelo_de(papel, a=None):
    a = a or ajustes()
    return (a.get("modelos") or {}).get(papel) or a.get("modelo") or MODELO


def esfuerzo(papel, a=None):
    a = a or ajustes()
    return (a.get("papeles") or {}).get(papel) or (a.get("reserva") or {}).get(papel)


def primero(papel, a=None):
    """¿Este trabajo lo piensa Claude antes que Gemini?"""
    return bool(papel) and papel in ((a or ajustes()).get("papeles") or {})


def de_reserva(papel, a=None):
    return bool(papel) and papel in ((a or ajustes()).get("reserva") or {})


def _estado():
    from bots.comun import privado
    e = privado.leer(ESTADO, {}) or {}
    e.setdefault("gastos", [])
    e.setdefault("dias", {})
    return e


def _hoy():
    return dt.datetime.now(dt.timezone.utc).date()


def _por_dia(e):
    """Dólares de cada día: el detalle de las llamadas (más lo de esta ronda) y, para días viejos, el total guardado."""
    dias = {d: v for d, v in (e.get("dias") or {}).items()}
    detalle = {}
    ids = set()
    for g in list(e.get("gastos") or []) + RONDA:
        if g.get("id") in ids:
            continue
        ids.add(g.get("id"))
        detalle[g.get("dia")] = detalle.get(g.get("dia"), 0) + (g.get("usd") or 0)
    dias.update(detalle)
    return dias


def _ciclo(hoy, dia):
    """(primer día del mes de créditos, día en que llegan los siguientes)."""
    dia = max(1, min(28, int(dia)))
    inicio = hoy.replace(day=dia) if hoy.day >= dia else \
        (hoy.replace(day=1) - dt.timedelta(days=1)).replace(day=dia)
    siguiente = (inicio.replace(day=28) + dt.timedelta(days=4)).replace(day=dia)
    return inicio, siguiente


def presupuesto(e=None, a=None):
    """Cuánto se ha gastado y cuánto se puede gastar hoy, para que los créditos lleguen a fin de mes."""
    e, a = e or _estado(), a or ajustes()
    hoy = _hoy()
    dias = _por_dia(e)
    mes = float(a.get("mes_usd") or DEFECTO["mes_usd"])
    gastado_hoy = dias.get(hoy.isoformat(), 0)
    if a.get("renueva_dia"):
        inicio, siguiente = _ciclo(hoy, a["renueva_dia"])
        antes = sum(v for d, v in dias.items() if inicio.isoformat() <= d < hoy.isoformat())
        quedan = max(1, (siguiente - hoy).days)
        tope_hoy = (mes - antes) / quedan
        en_el_mes = antes + gastado_hoy
    else:                                  # sin saber cuándo llegan: 1/30 al día y nunca más del mes en 30 días
        desde = (hoy - dt.timedelta(days=29)).isoformat()
        en_el_mes = sum(v for d, v in dias.items() if d >= desde)
        tope_hoy = mes / 30
        quedan = None
    tope_hoy = max(0.0, min(tope_hoy, float(a.get("dia_max_usd") or DEFECTO["dia_max_usd"])))
    try:                                     # un extra para hoy (una prueba): sale del mismo mes, nunca de fuera
        tope_hoy += max(0.0, float((a.get("extra_usd") or {}).get(hoy.isoformat()) or 0))
    except (TypeError, ValueError, AttributeError):
        pass
    tope_ahora = _tope_ahora(tope_hoy, a)
    # lo que gastan los papeles con hucha propia (la Élite) no se come el reparto de la fábrica (26 nov: la hucha de
    # la Élite contaba en el día y la fábrica se quedaba antes sin Claude)
    fuera = sum(gastado_hoy_papel(p, e) for p in (a.get("aparte") or {}))
    return {"hoy_usd": round(gastado_hoy, 4), "fabrica_hoy_usd": round(max(0.0, gastado_hoy - fuera), 4),
            "tope_hoy_usd": round(tope_hoy, 4), "tope_ahora_usd": round(tope_ahora, 4),
            "mes_usd": round(en_el_mes, 4), "tope_mes_usd": mes, "dias_para_creditos_nuevos": quedan}


def _tope_ahora(tope_hoy, a, papel=None, hora=None):
    """Lo que se puede llevar gastado a esta hora (UTC): la parte del día que ya ha pasado, más el adelanto del papel."""
    if not a.get("ritmo", True):
        return tope_hoy
    hora = dt.datetime.now(dt.timezone.utc).hour if hora is None else hora
    adelanto = (a.get("adelantos") or {}).get(papel, a.get("adelanto", 0.12))
    try:
        adelanto = float(adelanto)
    except (TypeError, ValueError):
        adelanto = 0.12
    return tope_hoy * min(1.0, (hora + 1) / 24 + adelanto)


def cuando_puede(papel="guionista"):
    """Si ahora no hay presupuesto para ese papel, cuándo vuelve a haberlo (UTC, ISO): la hora en que el reparto del día
    le alcanza o, si hoy ya se ha gastado la parte entera, las 00:00 de mañana. None si no depende del reloj."""
    try:
        a, e = ajustes(), _estado()
        p = presupuesto(e, a)
    except Exception:
        return None
    if p["mes_usd"] + MARGEN > p["tope_mes_usd"]:
        return None
    ahora = dt.datetime.now(dt.timezone.utc)
    for hora in range(ahora.hour, 24):
        if p["fabrica_hoy_usd"] + MARGEN <= _tope_ahora(p["tope_hoy_usd"], a, papel, hora):
            cuando = ahora.replace(hour=hora, minute=0, second=0, microsecond=0)
            return max(cuando, ahora.replace(microsecond=0)).strftime("%Y-%m-%dT%H:%M:%SZ")
    manana = (ahora + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return manana.strftime("%Y-%m-%dT%H:%M:%SZ")


def gastado_hoy_papel(papel, e=None):
    return gastado_hoy(papel, e)


def gastado_hoy(papel, e=None):
    """Dólares que lleva gastados hoy un papel concreto."""
    hoy = _hoy().isoformat()
    vistos, total = set(), 0.0
    for g in list((e or _estado()).get("gastos") or []) + RONDA:
        if g.get("id") in vistos:
            continue
        vistos.add(g.get("id"))
        if g.get("dia") == hoy and g.get("papel") == papel:
            total += g.get("usd") or 0
    return total


def puede(papel, a_su_hora=False):
    """¿Puede pensar Claude este trabajo ahora? Hace falta llave, el papel encendido y presupuesto de hoy.
    a_su_hora=True aplica el reparto por horas también a los papeles de reserva (el juez): la fábrica lo pregunta así
    ANTES de empezar un vídeo, para no empezar más de los que el día puede juzgar; el vídeo ya hecho se juzga siempre."""
    if APAGADO or not papel or not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        a = ajustes()
        e = _estado()
    except Exception:
        return False
    if not a.get("encendido", True) or not esfuerzo(papel, a):
        return False
    if e.get("sin_saldo"):
        try:
            desde = dt.datetime.strptime(e["sin_saldo"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
            if (dt.datetime.now(dt.timezone.utc) - desde).total_seconds() < REINTENTO_SIN_SALDO:
                return False
        except ValueError:
            pass
    p = presupuesto(e, a)
    hucha = (a.get("aparte") or {}).get(papel)
    if hucha:                                # hucha propia del día: no depende de lo que haya gastado la fábrica
        return gastado_hoy(papel, e) + MARGEN <= float(hucha) and p["mes_usd"] + MARGEN <= p["tope_mes_usd"]
    # El reparto por horas frena solo lo que Claude piensa primero y cuesta (guiones e ideas). Los jueces de reserva
    # no esperan a su hora (un vídeo ya hecho no se queda sin juicio) y el modelo pequeño cuesta céntimos.
    con_ritmo = (primero(papel, a) or a_su_hora) and not modelo_de(papel, a).startswith("claude-haiku")
    tope = _tope_ahora(p["tope_hoy_usd"], a, papel) if con_ritmo else p["tope_hoy_usd"]
    return p["fabrica_hoy_usd"] + MARGEN <= tope and p["mes_usd"] + MARGEN <= p["tope_mes_usd"]


def coste(modelo, entrada, salida, leido=0, escrito=0):
    p_ent, p_sal, p_leer, p_escr = PRECIOS.get(modelo, CARO)
    return (entrada * p_ent + salida * p_sal + leido * p_leer + escrito * p_escr) / 1_000_000


def _coste_respuesta(r, modelo_pedido):
    """Dólares de una respuesta. Si contestó un modelo de reserva, cada tramo se cuenta a su precio."""
    u = r.usage
    total = 0.0
    for t in list(getattr(u, "iterations", None) or []):
        if getattr(t, "type", "") == "compaction":
            continue
        total += coste(getattr(t, "model", None) or modelo_pedido, getattr(t, "input_tokens", 0) or 0,
                       getattr(t, "output_tokens", 0) or 0, getattr(t, "cache_read_input_tokens", 0) or 0,
                       getattr(t, "cache_creation_input_tokens", 0) or 0)
    if total:
        return total
    return coste(getattr(r, "model", None) or modelo_pedido, u.input_tokens or 0, u.output_tokens or 0,
                 getattr(u, "cache_read_input_tokens", 0) or 0, getattr(u, "cache_creation_input_tokens", 0) or 0)


def _apuntar(papel, modelo, r, usd, donde):
    ahora = dt.datetime.now(dt.timezone.utc)
    g = {"id": f"{ahora.strftime('%Y%m%dT%H%M%S%f')}-{os.environ.get('GITHUB_RUN_ID', 'local')}",
         "fecha": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), "dia": ahora.strftime("%Y-%m-%d"), "papel": papel,
         "modelo": getattr(r, "model", None) or modelo, "entrada": r.usage.input_tokens,
         "salida": r.usage.output_tokens, "usd": round(usd, 5), "donde": donde}
    RONDA.append(g)
    ULTIMO.clear()
    ULTIMO.update(motor="claude", modelo=g["modelo"], papel=papel, usd=g["usd"])
    try:
        _guardar(sin_saldo=None, aviso="")
    except Exception as ex:                # se volverá a intentar en la siguiente llamada
        print(f"cerebro: no he podido apuntar el gasto ({type(ex).__name__})", flush=True)


def _guardar(sin_saldo="igual", aviso=None):
    from bots.comun import privado
    e = _estado()
    ids = {g.get("id") for g in e["gastos"]}
    e["gastos"] += [g for g in RONDA if g["id"] not in ids]
    e["dias"] = {d: round(v, 4) for d, v in _por_dia(e).items()}
    corte = (_hoy() - dt.timedelta(days=DIAS_DETALLE)).isoformat()
    e["gastos"] = [g for g in e["gastos"] if g.get("dia", "") >= corte]
    if sin_saldo != "igual":
        e["sin_saldo"] = sin_saldo
    if aviso is not None:
        e["aviso"] = aviso
    a = ajustes()
    e["resumen"] = dict(presupuesto(e, a), modelo=a.get("modelo"), total_usd=round(sum(e["dias"].values()), 2),
                        llamadas_hoy=sum(1 for g in e["gastos"] if g.get("dia") == _hoy().isoformat()))
    privado.guardar_estado("claude.json", e)


def _imagen(ruta):
    """La foto en JPEG y, si es muy grande, achicada."""
    try:
        from PIL import Image
        with Image.open(ruta) as im:
            im = im.convert("RGB")
            if max(im.size) > LADO_MAXIMO:
                im.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
            datos = buf.getvalue()
    except Exception:
        with open(ruta, "rb") as f:
            datos = f.read()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(datos).decode()}}


def _json(texto):
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0].strip() if "\n" in t else ""
    try:
        return json.loads(t)
    except ValueError:
        pass
    inicios = [i for i in (t.find("{"), t.find("[")) if i >= 0]
    fin = max(t.rfind("}"), t.rfind("]"))
    if inicios and fin > min(inicios):
        return json.loads(t[min(inicios):fin + 1])
    raise ValueError("la respuesta no trae JSON")


def _cliente():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=2, timeout=600)


def preguntar(texto, papel, imagenes=(), json_salida=True, sin_audio=False, donde=None):
    """Como gemini.preguntar, pero pensando Claude. Lanza NoPuede si no puede (y entonces piensa Gemini)."""
    global APAGADO
    import anthropic
    a = ajustes()
    modelo = modelo_de(papel, a)
    if sin_audio:
        texto += ("\n\n(Esta vez no te llega el audio: juzga la voz por la narración escrita y las medidas, y no "
                  "bajes la nota por no poder oírla.)")
    contenido = [_imagen(r) for r in imagenes] + [{"type": "text", "text": texto}]
    try:
        if modelo.startswith("claude-haiku"):          # el modelo pequeño no tiene reserva en el servicio: sin «fallbacks»
            r = _cliente().messages.create(
                model=modelo, max_tokens=16000, system=SISTEMA,
                messages=[{"role": "user", "content": contenido}],
                output_config={"effort": esfuerzo(papel, a) or "medium"})
        else:
            r = _cliente().beta.messages.create(
                model=modelo, max_tokens=16000, system=SISTEMA,
                messages=[{"role": "user", "content": contenido}],
                output_config={"effort": esfuerzo(papel, a) or "high"},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        APAGADO = "la llave de Claude no vale o no tiene permiso"
        _guardar(aviso=f"{APAGADO} ({type(e).__name__})")
        raise NoPuede(APAGADO) from e
    except anthropic.NotFoundError as e:
        APAGADO = f"el modelo «{modelo}» no está disponible en esta cuenta"
        _guardar(aviso=APAGADO)
        raise NoPuede(APAGADO) from e
    except anthropic.BadRequestError as e:
        mensaje = str(getattr(e, "message", e)).lower()
        if "credit" in mensaje or "billing" in mensaje or "balance" in mensaje:
            APAGADO = "la cuenta de Claude se ha quedado sin saldo (hasta que lleguen los créditos del mes)"
            _guardar(sin_saldo=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), aviso=APAGADO)
            raise NoPuede(APAGADO) from e
        raise NoPuede(f"petición rechazada ({str(getattr(e, 'message', e))[:160]})") from e
    except anthropic.RateLimitError as e:
        raise NoPuede("demasiadas peticiones seguidas") from e
    except anthropic.APIStatusError as e:
        raise NoPuede(f"el servicio ha fallado (HTTP {e.status_code})") from e
    except anthropic.APIConnectionError as e:
        raise NoPuede(f"sin conexión con Claude ({type(e).__name__})") from e
    _apuntar(papel, modelo, r, _coste_respuesta(r, modelo), donde or os.environ.get("GITHUB_WORKFLOW", "local"))
    if r.stop_reason == "refusal":
        raise NoPuede("Claude (y su reserva) no ha querido hacerlo")
    if r.stop_reason == "max_tokens":
        raise NoPuede("la respuesta se ha cortado por larga")
    respuesta = "".join(getattr(b, "text", "") or "" for b in r.content if getattr(b, "type", "") == "text")
    if not json_salida:
        return respuesta
    try:
        return _json(respuesta)
    except ValueError as e:
        raise NoPuede("no ha devuelto el JSON pedido") from e


def en_esta_ronda():
    """(dólares, llamadas) de esta ronda: para el registro público, sin nada privado."""
    return round(sum(g.get("usd", 0) for g in RONDA), 4), len(RONDA)


if __name__ == "__main__":          # resumen: PRIVADO=<carpeta> python -m bots.comun.claude
    p = presupuesto()
    print(f"Claude: hoy {p['hoy_usd']:.2f} de {p['tope_hoy_usd']:.2f} $ · este mes {p['mes_usd']:.2f} de "
          f"{p['tope_mes_usd']:.0f} $ · llave: {'sí' if os.environ.get('ANTHROPIC_API_KEY') else 'no'}")
