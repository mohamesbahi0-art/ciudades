"""El Jurado popular del Juzgado (lo pidió el dueño el 23 nov): doce jurados, cada uno con su «piel», leen los dos alegatos
(la defensa dice que el vídeo va a funcionar y la fiscalía que va a fracasar) y votan por separado, sin ver el voto de
los demás: «inocente» (que se suba) o «culpable» (que no). Así la respuesta es honesta y no un aplauso.

Después el Juez Mayor lee el veredicto junto a las notas de los tres jueces: si 9 o más jurados lo declaran culpable, el
vídeo no se sube aunque los jueces le hayan dado 90 (la gente de la calle lo ha rechazado). Si el jurado no se puede
formar (la IA no contesta o se ha llegado al tope del día), deciden los jueces como siempre.

Los jurados no ven el vídeo: leen el título, lo que se ve al empezar, lo que cuenta y los dos alegatos (que sí lo
vieron). Piensan con el cerebro de los jueces (Gemini gratis, el ligero, que basta para leer; Claude de reserva).
"""
import datetime as dt
import os

from bots.comun import gemini, ia, privado

DEFECTO = {"encendido": True, "por_dia": 12, "rechazo": 9, "minimo_votos": 7}
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
Se juzga este vídeo de {donde} (en {idioma}):
- Título: {titulo}
- Lo que se ve y se lee al empezar: {gancho}
- Lo que cuenta: {narracion}
Alegato de la defensa (dice que va a funcionar): {defensa}
Alegato de la fiscalía (dice que va a fracasar): {fiscalia}
Vota tú solo, desde tu piel y con sinceridad (no le des la razón a nadie por quedar bien). El dueño solo quiere vídeos
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
    narracion = (guion.get("narracion") or " ".join(str(e.get("voz", "")) for e in guion.get("escenas") or []))[:1500]
    votos = []
    for nombre, piel, mira in PIELES:
        try:
            v = ia.preguntar(JURADO.format(nombre=nombre, piel=piel, mira=mira, donde=comun["donde"], idioma=comun["idioma"],
                                           titulo=guion.get("titulo", ""), gancho=comun.get("gancho") or "(sin texto)",
                                           narracion=narracion, defensa=alegatos.get("defensa", ""),
                                           fiscalia=alegatos.get("fiscalia", "")),
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
    c = privado.cuaderno("jurado_popular")
    c.apuntar("veredicto", {"canal": canal.get("clave"), "inocente": inocente, "culpable": culpable,
                            "rechaza": resultado["rechaza"]})
    c.guardar()
    return resultado
