"""El Presentador de directos (Ciudad Central): prepara cada semana el directo de cada cuenta de TikTok/Instagram.

Un directo necesita a una persona emitiendo, así que eso lo hace el dueño. Lo que sí se puede automatizar lo hace este
robot: cada lunes, para cada cuenta encendida, deja listo el directo de la semana en el idioma de la cuenta:
- título, mejor día y hora, y cuánto debe durar;
- el guion por bloques: el gancho de los 30 primeros segundos (cuando entra más gente), 3 o 4 temas con sus preguntas para
  el chat, una encuesta, un reto y el cierre;
- frases para saludar a los que entran, pedir que sigan la cuenta sin agobiar y responder a lo que más preguntarán;
- lo que no se debe hacer (las normas de TikTok: nada de pedir regalos a cambio de algo, ni sorteos de dinero).
Usa lo que funciona en el nicho (receta del Radar y del Ojeador) y los últimos temas de la cuenta. Lo deja en
estado/directos/<alias>.json (la ronda de Claude lo copia a la app). Los registros públicos solo llevan el alias.

Uso:  python bots/central/directos.py [--solo barrio-3] [--prueba]
"""
import argparse
import datetime as dt
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import gemini, ia, privado  # noqa: E402

ROBOT = "presentador_directos"
IDIOMAS = {"es": "español de España", "nl": "neerlandés de los Países Bajos", "en": "inglés"}

PLANTILLA = """Eres el Presentador de directos de una fábrica de vídeos cortos. Prepara el directo de esta semana en TikTok
para la cuenta «{nombre}» ({redes}). Tema de la cuenta: {tema}. Idioma de la cuenta: {idioma}.
Lo que funciona ahora en su nicho: {nicho}
Sus últimos vídeos: {titulos}
Quien presenta es el dueño, solo, con el móvil. Tiene que ser fácil de seguir y entretenido, para que la gente se quede y
siga la cuenta. Respeta las normas de TikTok: nada de pedir regalos a cambio de algo, ni sorteos de dinero, ni promesas.
Lo que dirá el dueño va en {idioma}; las explicaciones para él, en español de España sencillo.
Devuelve SOLO un JSON:
{{"titulo": "título del directo, en {idioma}, con gancho",
  "cuando": {{"dia": "el mejor día de la semana", "hora": "HH:MM, hora de España", "por_que": "una frase"}},
  "duracion_minutos": 30,
  "gancho": "lo que dice los 30 primeros segundos (en {idioma})",
  "bloques": [{{"minuto": 0, "tema": "...", "que_decir": "2 o 3 frases en {idioma}", "pregunta_chat": "en {idioma}"}}],
  "encuesta": {{"pregunta": "en {idioma}", "opciones": ["...", "..."]}},
  "reto": "un reto o juego para el chat, en {idioma}",
  "saludo": "frase para saludar a los que entran, en {idioma}",
  "seguir": "frase para pedir que sigan la cuenta sin agobiar, en {idioma}",
  "preguntas_previstas": [{{"pregunta": "en {idioma}", "respuesta": "corta, en {idioma}"}}],
  "cierre": "en {idioma}",
  "consejos": ["3 consejos en español de España sencillo"],
  "no_hacer": ["2 o 3 cosas que no hacer, en español de España"]}}"""


def cuentas(cfg, solo=None):
    for clave, b in cfg.get("barrios", {}).items():
        if solo and clave not in solo:
            continue
        if b.get("estado") == "activo":
            yield clave, privado.canal(clave)


def preparar(clave, canal):
    receta = ((privado.leer(os.path.join("estado", "influencers", "recetas.json"), {}) or {}).get("canales") or {}).get(clave) or {}
    nicho = {p: {k: (receta.get(p) or {}).get(k) for k in ("lo_que_funciona", "ganchos", "temas")
                 if (receta.get(p) or {}).get(k)} for p in ("radar", "ojeador") if receta.get(p)}
    titulos = privado.titulos_recientes(clave)[:10]
    idioma = IDIOMAS.get((canal.get("idioma") or "es")[:2], "español de España")
    texto = PLANTILLA.format(nombre=canal.get("nombre", clave), redes=", ".join(canal.get("redes") or ["tiktok"]),
                             tema=(canal.get("tema") or "")[:400], idioma=idioma,
                             nicho=json.dumps(nicho, ensure_ascii=False)[:1500] or "(todavía nada)",
                             titulos="; ".join(titulos) or "(todavía ninguno)")
    d = ia.preguntar(texto, papel="ideas", temperatura=0.8)
    if isinstance(d, list) and d:
        d = d[0]
    if not isinstance(d, dict) or not d.get("bloques"):
        raise gemini.SinIA("el directo no ha salido con la forma pedida")
    return d


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--solo", help="alias o claves separadas por comas")
    p.add_argument("--prueba", action="store_true")
    a = p.parse_args()
    cfg = privado.config()
    solo = {privado.resolver(x) for x in a.solo.split(",")} if a.solo else None
    semana = dt.date.today().isocalendar()
    hechos, codigo = 0, 0
    for clave, canal in cuentas(cfg, solo):
        alias = privado.alias(clave)
        try:
            d = preparar(clave, canal)
        except gemini.SinIA as e:
            print(f"directos: {alias}: la IA no contesta ahora ({str(e)[:60]})", flush=True)
            codigo = 1
            continue
        d.update(cuenta=clave, alias=alias, nombre=canal.get("nombre", clave), semana=f"{semana[0]}-{semana[1]:02d}",
                 idioma=(canal.get("idioma") or "es")[:2], cerebro=ia.quien().get("motor"))
        if a.prueba:
            print(json.dumps(d, ensure_ascii=False, indent=1)[:1500])
        else:
            privado.guardar_estado(os.path.join("directos", f"{alias}.json"), d)
            c = privado.cuaderno(ROBOT)
            c.apuntar("directo_preparado", {"cuenta": alias, "semana": d["semana"], "bloques": len(d.get("bloques") or [])})
            c.guardar()
        hechos += 1
        print(f"directos: {alias}: directo de la semana listo ({len(d.get('bloques') or [])} bloques)", flush=True)
    if not hechos:
        print("directos: no hay cuentas encendidas para preparar")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
