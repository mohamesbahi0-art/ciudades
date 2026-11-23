"""El Entrenador (Influencers): lee cómo van de verdad las cuentas y les pone deberes concretos.

Cada día, después del Estudio de los Influencers, mira para cada canal y barrio encendido:
- sus cifras (informe de la Analista: visitas a las 48 h, mejor vídeo de la semana, últimos vídeos);
- lo que dijo el Juzgado de sus últimos vídeos (notas y consejos de los turnos) y las notas reales del Cerebro;
- lo que funciona ahora en su nicho (receta: Radar de nichos y Ojeador de redes).
Y decide UNA cosa que mejorar, qué está yendo bien (para repetirlo), 3 ideas concretas y la prueba de la semana. Lo deja
en la receta del canal (la leen los guionistas antes de escribir) y en estado/influencers/entrenador.json para la app.
Piensa con el cerebro de las ideas (Claude si hay llave y presupuesto; si no, Gemini gratis).

Uso:  python bots/influencers/entrenador.py [--solo gta,barrio-2]
"""
import argparse
import datetime as dt
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import gemini, ia, privado  # noqa: E402

ROBOT = "entrenador"
ARCHIVO = os.path.join("influencers", "entrenador.json")      # dentro de estado/

PLANTILLA = """Eres el Entrenador de una fábrica de vídeos cortos. Tu trabajo: que esta cuenta mejore la semana que viene.
Cuenta: «{nombre}» ({red}). Tema: {tema}.
Cómo va de verdad (cifras): {cifras}
Lo que dijo el Juzgado de sus últimos vídeos (nota de 0 a 100 y consejo): {juicios}
Lo que funciona ahora en su nicho (YouTube, TikTok e Instagram): {nicho}
Lo que ha aprendido su escritor (lo del dueño manda): {lecciones}
El dueño solo publica vídeos de 90 o más y prefiere menos vídeos pero mejores y más virales.
Devuelve SOLO un JSON: {{"va_bien": "lo que está funcionando y hay que repetir, en una frase con un ejemplo real",
"mejorar": "UNA sola cosa concreta que cambiar en los próximos vídeos", "por_que": "en qué cifra o juicio lo ves",
"ideas": [{{"titulo": "...", "gancho": "primera frase, en el idioma de la cuenta", "por_que": "una frase"}}],
"prueba_semana": "un experimento concreto (qué cambiar y cómo sabremos si ha ido mejor)"}}  (3 ideas)
En español de España sencillo, salvo los ganchos de las ideas."""


def perfiles():
    cfg = privado.config()
    for seccion in ("canales", "barrios"):
        for clave, c in (cfg.get(seccion) or {}).items():
            if c.get("estado") == "en_pausa" or c.get("pausado"):
                continue
            yield {"clave": clave, "nombre": c.get("nombre", clave), "tema": (c.get("tema") or clave)[:200],
                   "red": "YouTube Shorts" if seccion == "canales" else "TikTok e Instagram"}


def _juicios(clave):
    """Las notas y consejos del Juzgado de los últimos turnos del canal."""
    d = privado.leer(os.path.join("estado", "central", f"{privado.alias(clave)}.json"), {}) or {}
    salida = []
    for t in (d.get("turnos") or [])[-8:]:
        if t.get("nota") is not None or t.get("consejo"):
            salida.append({"titulo": (t.get("titulo") or "")[:80], "nota": t.get("nota"),
                           "destino": t.get("destino_resultado"), "consejo": (t.get("consejo") or "")[:160]})
    return salida


def _cifras(clave, informe):
    yt = (informe.get("youtube") or {}).get(clave) or {}
    if yt:
        return {k: yt.get(k) for k in ("suscriptores", "suscriptores_7d", "publicados_7_dias", "media_visitas_48h",
                                       "mediana_visitas_48h", "mejor_7_dias", "ultimos") if yt.get(k) is not None}
    redes = (informe.get("instagram_tiktok") or {}).get(clave) or {}
    return redes or "todavía sin cifras (los vídeos de TikTok e Instagram los sube el dueño a mano)"


def _nicho(receta):
    corto = {}
    for parte in ("radar", "ojeador"):
        r = receta.get(parte) or {}
        if r:
            corto[parte] = {k: r.get(k) for k in ("lo_que_funciona", "ganchos", "temas", "formato", "duracion", "evitar")
                            if r.get(k)}
    return corto or "(todavía nada)"


def entrenar(perfil, informe, recetas):
    clave = perfil["clave"]
    receta = (recetas.get("canales") or {}).get(clave) or {}
    lecciones = privado.cuaderno("escritor" if perfil["red"] == "YouTube Shorts" else "guionista").para_el_prompt(8)
    texto = PLANTILLA.format(nombre=perfil["nombre"], red=perfil["red"], tema=perfil["tema"],
                             cifras=json.dumps(_cifras(clave, informe), ensure_ascii=False)[:1800],
                             juicios=json.dumps(_juicios(clave), ensure_ascii=False)[:1500] or "(todavía ninguno)",
                             nicho=json.dumps(_nicho(receta), ensure_ascii=False)[:1800], lecciones=lecciones[:1200])
    r = ia.preguntar(texto, papel="ideas", temperatura=0.6, ligero_primero=True)
    if isinstance(r, list) and r:
        r = r[0]
    if not isinstance(r, dict) or not r.get("mejorar"):
        raise gemini.SinIA("el Entrenador no ha recibido la forma pedida")
    return dict(r, fecha=privado.ahora(), cerebro=ia.quien().get("motor"))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--solo", default="")
    a = p.parse_args(argv)
    pedidos = {privado.resolver(x) for x in a.solo.split(",") if x.strip()}
    informe = privado.leer(os.path.join("estado", "analisis", "informe.json"), {}) or {}
    ruta_recetas = os.path.join("estado", "influencers", "recetas.json")
    archivo = privado.leer(os.path.join("estado", ARCHIVO), {}) or {}
    planes = archivo.get("cuentas") or {}
    cuaderno = privado.cuaderno(ROBOT)
    hechos = 0
    for perfil in perfiles():
        if pedidos and perfil["clave"] not in pedidos:
            continue
        alias = privado.alias(perfil["clave"])
        recetas = privado.leer(ruta_recetas, {}) or {}
        try:
            plan = entrenar(perfil, informe, recetas)
        except gemini.SinIA as e:
            print(f"entrenador: {alias} sin plan hoy ({str(e)[:80]})", flush=True)
            continue
        planes[perfil["clave"]] = dict(plan, nombre=perfil["nombre"], alias=alias)
        canales = recetas.setdefault("canales", {})
        canales.setdefault(perfil["clave"], {})["entrenador"] = {
            k: plan.get(k) for k in ("fecha", "va_bien", "mejorar", "por_que", "ideas", "prueba_semana")}
        privado.guardar_estado("influencers/recetas.json", {"canales": canales})
        cuaderno.apuntar("plan", {"canal": perfil["clave"], "mejorar": str(plan.get("mejorar"))[:160]})
        hechos += 1
        print(f"entrenador: {alias} → plan de la semana hecho", flush=True)
    privado.guardar_estado(ARCHIVO, {"cuentas": planes, "fecha": privado.ahora()})
    cuaderno.guardar()
    gemini.apuntar_portero()
    print(f"entrenador: {hechos} planes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
