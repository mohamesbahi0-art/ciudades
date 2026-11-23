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
    "papeles": {"guionista": "high", "ideas": "medium"},
    # trabajos que piensa Gemini (gratis; el juez, además, es así de otro «jurado» y oye la voz) y Claude si Gemini no puede
    "reserva": {"juez": "medium"},
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
    return a


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
    return {"hoy_usd": round(gastado_hoy, 4), "tope_hoy_usd": round(tope_hoy, 4), "mes_usd": round(en_el_mes, 4),
            "tope_mes_usd": mes, "dias_para_creditos_nuevos": quedan}


def puede(papel):
    """¿Puede pensar Claude este trabajo ahora? Hace falta llave, el papel encendido y presupuesto de hoy."""
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
    return p["hoy_usd"] + MARGEN <= p["tope_hoy_usd"] and p["mes_usd"] + MARGEN <= p["tope_mes_usd"]


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
    modelo = a.get("modelo") or MODELO
    if sin_audio:
        texto += ("\n\n(Esta vez no te llega el audio: juzga la voz por la narración escrita y las medidas, y no "
                  "bajes la nota por no poder oírla.)")
    contenido = [_imagen(r) for r in imagenes] + [{"type": "text", "text": texto}]
    try:
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
