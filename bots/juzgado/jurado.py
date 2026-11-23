"""El Jurado popular del Juzgado (lo pidió el dueño el 23 nov): doce jurados, cada uno con su «piel», leen el GUION antes
de que se grabe (y, si los hay, los alegatos de la Sala de Ideas) y votan por separado, sin ver el voto de los demás:
«inocente» (que se haga) o «culpable» (que no). Así la respuesta es honesta y no un aplauso.

Va antes de gastar en voz, dibujos y montaje (lo barato filtra primero): si 9 o más lo declaran culpable, el Escritor lo
reescribe con lo que han dicho (hasta 2 veces) y, si aún no les convence, ese guion no se graba. Si el jurado no se
puede formar (la IA no contesta o se ha llegado al tope del día), el guion sigue y deciden los jueces del vídeo.
Cada reunión queda como un juicio de tipo «guion» para la app, y su nota media entra en la Liga de los Jueces.
Piensan con el cerebro de los jueces (Gemini gratis, el ligero, que basta para leer; Claude de reserva).
"""
import datetime as dt
import os

from bots.comun import gemini, ia, privado

DEFECTO = {"encendido": True, "por_dia": 15, "rechazo": 9, "minimo_votos": 7}
PIELES = [
    ("Nacho Madrugada", "el del scroll a las 2 de la mañana", "pasa vídeos sin parar y aburrido: ¿se pararía en este?"),
    ("Marta Fan", "fan del tema", "sabe mucho de este nicho: ¿aporta algo nuevo o es más de lo mismo?"),
    ("Raúl Pasota", "el que odia el tema", "no le interesa nada este tema: ¿le haría quedarse igualmente?"),
    ("Leo Quince", "un chaval de 15 años", "¿se lo pasaría a sus amigos o le da vergüenza ajena?"),
    ("Pilar Cuarenta", "una madre de 45 años", "¿lo entiende a la primera y le interesa?"),
    ("Iván Rival", "un creador rival del mismo nicho", "¿le daría envidia o le parece flojo y copiado?"),
    ("Algo Ritmo", "el algoritmo de la plataforma", "¿se verá entero, se repetirá, se comentará y se compartirá?"),
    ("Vera Datos", "la que comprueba los datos", "¿es verdad lo que dice? ¿hay errores que destrozarían los comentarios?"),
    ("Mudo Martín", "el que lo ve sin sonido", "¿se entiende solo con lo que se ve y se lee?"),
    ("Clara Marca", "una anunciante", "¿es un vídeo cuidado, de calidad y dentro de las normas?"),
    ("Tomi Comenta", "el que comenta todo", "¿le da un motivo para comentar, opinar o discutir?"),
    ("Paco Cuentas", "un contable", "¿vale el tiempo que pide? ¿da lo que promete en lo que dura?"),
]

JURADO = """Eres {nombre}, miembro del jurado popular del Juzgado de una fábrica de vídeos cortos. Tu piel: {piel}. Lo que
miras: {mira}
Se juzga este guion de {donde} (en {idioma}), ANTES de grabarlo:
- Título: {titulo}
- Lo que se verá y se leerá al empezar: {gancho}
- Lo que contará: {narracion}
{alegatos}Vota tú solo, desde tu piel y con sinceridad (no le des la razón a nadie por quedar bien). El dueño solo quiere vídeos
excelentes, que la gente vea enteros y comparta. Un tema duro u oscuro no es motivo para votar culpable.
Devuelve SOLO un JSON: {{"voto": "inocente" (que se suba) o "culpable" (que no), "nota": 0-100, "porque": "una frase desde tu piel"}}"""


def ajustes():
    a = dict(DEFECTO)
    a.update(((privado.ajustes() or {}).get("juzgado") or {}).get("jurado") or {})
    return a


def _hoy():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _cuenta():
    r = privado.leer(os.path.join("estado", "juzgado", "jurado.json"), {}) or {}
    hoy = r.get("hoy") or {}
    return r, (hoy if hoy.get("dia") == _hoy() else {"dia": _hoy(), "jurados": 0})


def deliberar(guion, canal, alegatos, comun):
    """Los doce votan por separado. Devuelve el veredicto o None si hoy no hay jurado."""
    a = ajustes()
    registro, hoy = _cuenta()
    if not a.get("encendido", True) or int(hoy.get("jurados", 0)) >= int(a.get("por_dia", 12)):
        return None
    narracion = (guion.get("narracion") or " ".join(str(e.get("voz", "")) if isinstance(e, dict) else str(e)
                                                    for e in guion.get("escenas") or []))[:1500]
    texto_alegatos = ""
    if alegatos.get("defensa") or alegatos.get("fiscalia"):
        texto_alegatos = (f"Alegato de la defensa (dice que va a funcionar): {alegatos.get('defensa', '')}\n"
                          f"Alegato de la fiscalía (dice que va a fracasar): {alegatos.get('fiscalia', '')}\n")
    votos = []
    for nombre, piel, mira in PIELES:
        try:
            v = ia.preguntar(JURADO.format(nombre=nombre, piel=piel, mira=mira, donde=comun["donde"], idioma=comun["idioma"],
                                           titulo=guion.get("titulo", ""), gancho=comun.get("gancho") or "(sin texto)",
                                           narracion=narracion, alegatos=texto_alegatos),
                             papel="juez", temperatura=0.6, ligero_primero=True)
        except gemini.SinIA:
            continue
        if isinstance(v, list) and v:
            v = v[0]
        if not isinstance(v, dict) or str(v.get("voto", "")).lower() not in ("inocente", "culpable"):
            continue
        try:
            nota = max(0, min(100, int(v.get("nota", 0))))
        except (TypeError, ValueError):
            nota = None
        votos.append({"jurado": nombre, "piel": piel, "voto": str(v["voto"]).lower(), "nota": nota,
                      "porque": str(v.get("porque", ""))[:200]})
    if len(votos) < int(a.get("minimo_votos", 7)):
        return None
    culpable = sum(1 for v in votos if v["voto"] == "culpable")
    inocente = len(votos) - culpable
    notas = [v["nota"] for v in votos if v["nota"] is not None]
    resultado = {"votos": votos, "inocente": inocente, "culpable": culpable,
                 "veredicto": "culpable" if culpable > inocente else "inocente",
                 "rechaza": culpable >= int(a.get("rechazo", 9)), "nota_media": round(sum(notas) / len(notas)) if notas else None,
                 "cerebro": ia.quien().get("motor")}
    hoy["jurados"] = int(hoy.get("jurados", 0)) + 1
    privado.guardar_estado(os.path.join("juzgado", "jurado.json"), {"hoy": hoy, "ultimo": {
        "titulo": guion.get("titulo"), "inocente": inocente, "culpable": culpable, "fecha": privado.ahora()}})
    ahora = dt.datetime.now(dt.timezone.utc)
    id_juicio = f"{ahora.strftime('%Y%m%d-%H%M%S')}-{canal.get('clave', 'x')}-jurado".replace(".", "-")
    privado.guardar_estado(os.path.join("juzgado", "juicios", f"{id_juicio}.json"), {
        "canal": canal.get("clave"), "tipo": "guion", "titulo": guion.get("titulo"), "jurado": resultado,
        "sentencia": "no_sube" if resultado["rechaza"] else "sube", "fecha": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resumen": (f"Jurado popular: {inocente} inocente y {culpable} culpable. "
                    + ("Lo rechaza: el guion se reescribe." if resultado["rechaza"] else "El guion sigue: se graba.")),
        "prueba": bool(comun.get("prueba")), "turno": comun.get("turno"), "intento": comun.get("intento")})
    resultado["juicio_app"] = id_juicio
    c = privado.cuaderno("jurado_popular")
    c.apuntar("veredicto", {"canal": canal.get("clave"), "inocente": inocente, "culpable": culpable,
                            "rechaza": resultado["rechaza"]})
    c.guardar()
    return resultado
