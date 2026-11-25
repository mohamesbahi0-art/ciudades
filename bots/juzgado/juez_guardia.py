"""El Juez de guardia: juicio rápido de un vídeo ya montado. Mide el vídeo con fotogramas.py, mira los 7 fotogramas
y pone nota de 0 a 100 (gancho, retención, claridad y final, de 0 a 25 cada uno). Suspende con fallo grave o menos de 50.
Si la IA no contesta, el vídeo pasa sin juicio (regla del Juzgado: ningún canal se queda sin vídeos)."""
import json
import os
import subprocess
import sys

from bots.comun import gemini, ia

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import fotogramas  # noqa: E402

MINIMO = 90               # el dueño: solo se publica lo de 90 o más, en todas las plataformas

PLANTILLA = """Eres el Juez de guardia del Juzgado de {donde} llamado «{nombre}». El vídeo está en {idioma}.
Juzgas si este vídeo hará que la gente que va pasando vídeos cortos se pare y lo vea entero.
Te paso 7 fotogramas en orden (segundos 0,3 · 1,2 · 2,5, y al 30 %, 55 %, 80 % y el final) y estos datos:
- Título: {titulo}
- Texto en pantalla al empezar: {gancho}
- Narración: {narracion}
- Medidas del vídeo: {medidas}{formato}

Lo que ha aprendido el Juzgado (síguelo; lo del dueño manda):
{lecciones}

Puntúa de 0 a 25 cada apartado:
- gancho: ¿los 2 primeros segundos hacen parar el dedo?
- retencion: ¿hay partes muertas, silencios o relleno?
- claridad: ¿se entiende solo y sin sonido? ¿se ve bien?
- final: ¿acaba en algo que dé ganas de verlo otra vez o comentar?
Fallos graves (SOLO estos): pantalla negra, vídeo sin voz, imágenes rotas o con letras deformadas, título que no tiene nada
que ver con el vídeo, algo que rompa las normas de YouTube o TikTok. Un tema duro, oscuro o incómodo NO es un fallo
ni baja la nota: el dueño lo quiere así. Los dibujos están hechos con IA a propósito: ese estilo no es un fallo. El ritmo,
las pausas o un gancho flojo bajan la nota, pero no son fallos graves.
Devuelve SOLO un JSON: {{"gancho": 0, "retencion": 0, "claridad": 0, "final": 0, "fallos_graves": [], "consejo": "una frase concreta para mejorarlo"}}"""


def sin_musica(canal):
    return str(canal.get("musica_estudio") or "").strip().lower() in ("ninguna", "no", "sin", "sin musica", "sin música")


def nota_formato(canal):
    """Lo que el juez tiene que saber para no castigar lo que el dueño hace a propósito."""
    if not sin_musica(canal):
        return ""
    return ("\n- Va SIN música a propósito: el dueño le pone la música al subirlo a TikTok o Instagram. No restes por no "
            "tener música ni por el final tranquilo de un segundo (ahí entra su música).")


def medidas_para(datos, canal, guion=None):
    """Las medidas que ven los jueces y abogados (en palabras), con la música dicha cuando falta a propósito.
    En los vídeos animados del estudio se añade lo que sabe el guion: cuántas escenas tiene y cuándo llega la segunda.
    El detector de cortes de vídeo no cuenta una escena animada que entra con un fundido, así que solo con él un vídeo de
    10 escenas salía con «0 cortes por minuto»."""
    medidas = fotogramas.para_jueces(datos)
    if sin_musica(canal):
        medidas["musica"] = "ninguna, a propósito: el dueño pone su música al subirlo (no es un fallo)"
    try:
        inicios = [float(e["inicio"]) for e in (guion or {}).get("escenas") or [] if isinstance(e, dict) and "inicio" in e]
        duracion = float(medidas.get("duracion") or (guion or {}).get("duracion") or 0)
        if len(inicios) >= 2 and duracion > 0:
            medidas["escenas"] = len(inicios)
            medidas["cambios_de_escena_por_minuto"] = round((len(inicios) - 1) / duracion * 60, 1)
            medidas["segunda_escena_empieza"] = round(inicios[1], 2)
            medidas["nota_ritmo"] = ("es animación: cada escena cambia lo que se ve; «cortes» solo cuenta los cambios "
                                     "bruscos de imagen que detecta la máquina")
    except (TypeError, ValueError, KeyError):
        pass
    return medidas


def juzgar(video, guion, canal, lecciones, carpeta):
    subprocess.run([sys.executable, os.path.join(RAIZ, "herramientas", "fotogramas.py"), video, "--salida", carpeta],
                   check=True, capture_output=True)
    with open(os.path.join(carpeta, "datos.json"), encoding="utf-8") as f:
        datos = json.load(f)
    medidas = medidas_para(datos, canal, guion)
    fallos = []
    negras = [n for n in datos.get("pantallas_negras") or [] if n.get("hasta", 0) - n.get("desde", 0) >= 0.8]
    if negras:                       # un fundido corto no cuenta: solo pantallas negras de casi un segundo o más
        fallos.append("pantalla negra")
    if datos.get("sin_audio"):
        fallos.append("sin voz")
    donde = "un canal de YouTube Shorts" if canal.get("destino", "youtube") == "youtube" else "una cuenta de Instagram y TikTok"
    idioma = {"es": "español", "nl": "neerlandés", "en": "inglés"}.get(canal.get("idioma", "es")[:2], "español")
    texto = PLANTILLA.format(nombre=canal["nombre"], donde=donde, idioma=idioma, titulo=guion["titulo"], gancho=guion.get("texto_pantalla", ""),
                             narracion=guion["narracion"], medidas=json.dumps(medidas, ensure_ascii=False),
                             formato=nota_formato(canal), lecciones=lecciones)
    imagenes = [os.path.join(carpeta, f["archivo"]) for f in datos["fotogramas"]]
    imagenes = [r for r in imagenes if os.path.exists(r)]      # un fotograma que no se pudo sacar no tumba el juicio
    try:
        v = ia.preguntar(texto, papel="juez", imagenes=imagenes, solo_bueno=True, temperatura=0.3)
        if isinstance(v, list) and v:
            v = v[0]
        if not isinstance(v, dict):
            raise gemini.SinIA("respuesta con forma rara")
        notas = {k: max(0, min(25, int(v.get(k, 0) or 0))) for k in ("gancho", "retencion", "claridad", "final")}
        fallos += [str(x) for x in v.get("fallos_graves", []) if x]
        total = sum(notas.values())
        try:
            minimo = int(canal.get("nota_minima", MINIMO))
        except (TypeError, ValueError):
            minimo = MINIMO
        veredicto = "suspendido" if fallos or total < minimo else "aprobado"
        resultado = dict(notas, total=total, veredicto=veredicto, fallos_graves=fallos, consejo=v.get("consejo", ""))
    except (gemini.SinIA, TypeError, ValueError) as e:
        resultado = {"veredicto": "suspendido" if fallos else "sin_juicio", "fallos_graves": fallos,
                     "motivo": f"juicio sin IA: {e}"}
    resultado["medidas"] = medidas
    if resultado.get("total") is not None:
        resultado["cerebro"] = ia.quien().get("motor", "gemini")
    with open(os.path.join(carpeta, "veredicto.json"), "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)
    return resultado
