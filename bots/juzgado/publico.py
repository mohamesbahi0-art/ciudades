"""El Cine (octava ciudad): 100 espectadores distintos miran el vídeo YA MONTADO antes del juicio y dicen si se quedan o pasan de largo
(lo pidió el dueño: «100 o 200 personas, cada una con su manera de ver el vídeo; si se enganchan o se van»).

Cada espectador tiene su edad, su momento del día, su paciencia y lo que le interesa. Se les enseñan los fotogramas (del
primer segundo al final), lo primero que se lee y lo que dice la voz, y cada uno contesta: ¿paro el dedo?, ¿hasta qué
segundo aguanto?, ¿por qué? De ahí sale la retención de mentira: cuántos pasan del segundo 3, cuántos llegan al final,
dónde se va la gente y por qué. El Juzgado lo recibe como prueba y los arreglos lo usan para corregir el vídeo.
Todos opinan en UNA sola pregunta a la IA pequeña (cuesta céntimos); si no hay IA, el juicio sigue sin público.
"""
import json
import random

from bots.comun import ia, privado

ARCHIVO = "estado/cine/sesiones.json"        # las últimas sesiones, para «El Cine» de la app

EDADES = ("14", "16", "18", "21", "24", "27", "31", "36", "42", "50")
MOMENTOS = ("en el bus, medio dormido", "en clase, a escondidas", "en el baño", "en la cama antes de dormir",
            "esperando la comida", "en un descanso del trabajo", "aburrido en el sofá", "con la tele puesta de fondo",
            "en el gimnasio entre series", "recién levantado")
PACIENCIAS = ("pasa de todo en 1 segundo", "da 2 segundos y si no, fuera", "aguanta si hay una pregunta abierta",
              "se queda si aprende algo", "ve casi todo entero", "solo se queda si le hace gracia o le choca")
GUSTOS = ("fútbol", "dinero y negocios", "videojuegos", "cotilleos", "ciencia y curiosidades", "gimnasio", "humor",
          "miedo y misterio", "coches", "historia", "música", "moda", "cocina", "viajes", "tecnología", "series")

PREGUNTA = """Eres el simulador de público de {donde}. Abajo hay {n} espectadores de verdad, cada uno distinto. A todos
les sale este vídeo en su móvil mientras pasan vídeos con el dedo. El vídeo está en {idioma} y dura {duracion} segundos.
Título: {titulo}
Lo primero que se lee en pantalla: {gancho}
Lo que dice la voz: {narracion}
Te paso sus fotogramas en orden (segundos 0,3 · 1,2 · 2,5 · al 30 % · al 55 % · al 80 % · el final).

Para CADA espectador decide, metiéndote en su piel (su edad, dónde está, su paciencia y lo que le gusta), sin ser amable:
- hasta qué segundo lo ve antes de pasar al siguiente (0 = ni para el dedo; {duracion} = lo ve entero);
- por qué se va o por qué se queda, en 6 palabras como mucho;
- si lo compartiría o comentaría (1) o no (0).
La gente real es impaciente: en un vídeo normal más de la mitad se va antes del segundo 3. No regales nada.

Espectadores:
{espectadores}

Devuelve SOLO un JSON: {{"publico": [[número de espectador, segundo en que se va, "por qué", 0 o 1], ...]}} con los {n}."""


def espectadores(n=100, semilla=None):
    r = random.Random(semilla)
    return [f"{i}. {r.choice(EDADES)} años, {r.choice(MOMENTOS)}; {r.choice(PACIENCIAS)}; le gusta {r.choice(GUSTOS)} y "
            f"{r.choice(GUSTOS)}" for i in range(1, n + 1)]


def mirar(guion, canal, imagenes, duracion, prueba=False):
    """Devuelve el resumen del público ({"personas", "paran", "pasan_3s", "mitad", "final", "comparten", "se_van_en",
    "motivos_irse", "motivos_quedarse"}) o None si hoy no hay público (apagado, sin IA o respuesta rara)."""
    a = ((privado.ajustes() or {}).get("juzgado") or {}).get("publico") or {}
    if a.get("encendido") is False or not imagenes or not duracion:
        return None
    n = max(20, min(200, int(a.get("personas", 100))))
    idioma = {"es": "español", "nl": "neerlandés", "en": "inglés"}.get((canal.get("idioma") or "es")[:2], "español")
    texto = PREGUNTA.format(donde="YouTube Shorts" if canal.get("destino", "youtube") == "youtube" else "TikTok e Instagram",
                            n=n, idioma=idioma, duracion=round(float(duracion)), titulo=guion.get("titulo", ""),
                            gancho=guion.get("texto_pantalla", ""), narracion=str(guion.get("narracion", ""))[:2500],
                            espectadores="\n".join(espectadores(n, semilla=guion.get("titulo"))))
    try:
        r = ia.preguntar(texto, papel="jurado", imagenes=imagenes, solo_bueno=True, temperatura=0.8)
    except Exception:
        return None
    filas = r.get("publico") if isinstance(r, dict) else r
    votos = []
    for f in filas if isinstance(filas, list) else []:
        try:
            votos.append((max(0.0, min(float(duracion), float(f[1]))), str(f[2])[:60], 1 if f[3] in (1, True, "1") else 0))
        except (TypeError, ValueError, IndexError):
            continue
    if len(votos) < n * 0.6:                  # contestaron pocos: no vale como prueba
        return None
    total, d = len(votos), float(duracion)
    def parte(cond):
        return round(100 * sum(1 for v in votos if cond(v)) / total)
    def mas_dichos(lista, k=4):
        cuenta = {}
        for m in lista:
            cuenta[m.lower().strip(" .")] = cuenta.get(m.lower().strip(" ."), 0) + 1
        return [m for m, _ in sorted(cuenta.items(), key=lambda x: -x[1])[:k]]
    se_van = sorted(v[0] for v in votos if v[0] < d * 0.9)
    resumen = {"personas": total, "paran": parte(lambda v: v[0] >= 1), "pasan_3s": parte(lambda v: v[0] >= 3),
               "mitad": parte(lambda v: v[0] >= d * 0.5), "final": parte(lambda v: v[0] >= d * 0.9),
               "comparten": parte(lambda v: v[2] == 1),
               "se_van_en": round(se_van[len(se_van) // 2], 1) if se_van else None,
               "motivos_irse": mas_dichos([v[1] for v in votos if v[0] < d * 0.5]),
               "motivos_quedarse": mas_dichos([v[1] for v in votos if v[0] >= d * 0.9], 3),
               "cerebro": ia.quien().get("motor", "gemini"), "prueba": prueba}
    try:                                   # la sesión queda apuntada para «El Cine» de la app (las 40 últimas)
        clave = canal.get("clave", "")
        sesion = dict(resumen, canal=clave, titulo=str(guion.get("titulo", ""))[:120], fecha=privado.ahora(),
                      version=guion.get("version", 1), frase=en_palabras(resumen),
                      id=f"{privado.ahora()[:19].replace(':', '').replace('-', '')}-{privado.alias(clave)}".replace(".", "-"))
        d = privado.leer(ARCHIVO, {}) or {}
        d["sesiones"] = ((d.get("sesiones") or []) + [sesion])[-40:]
        privado.escribir(ARCHIVO, dict(d, actualizado=privado.ahora()))
        for robot, que in (("publico_cine", "sesion"), ("acomodador", "recuento")):
            c = privado.cuaderno(robot)
            c.apuntar(que, {"canal": clave, "personas": total, "final": resumen["final"], "pasan_3s": resumen["pasan_3s"]})
            c.guardar()
    except Exception:
        pass
    return resumen


def en_palabras(p):
    """El resumen en una frase, para los jueces, los arreglos y la app."""
    if not p:
        return ""
    return (f"Público de {p['personas']} espectadores distintos: paran el dedo el {p['paran']} %, pasan del segundo 3 el "
            f"{p['pasan_3s']} %, llegan a la mitad el {p['mitad']} % y lo ven entero el {p['final']} %; lo compartirían el "
            f"{p['comparten']} %."
            + (f" Los que se van lo hacen hacia el segundo {p['se_van_en']}" if p.get("se_van_en") is not None else "")
            + (f" y dicen: {'; '.join(p['motivos_irse'])}." if p.get("motivos_irse") else ".")
            + (f" Los que se quedan: {'; '.join(p['motivos_quedarse'])}." if p.get("motivos_quedarse") else ""))
