"""Simulacro de la Ventanilla del Juzgado («Juzga mi vídeo») con una IA de mentira (sin red ni secretos).
Comprueba que un vídeo del dueño pasa por el Jurado popular, el Juzgado completo y, si aprueba, por el Coliseo (con su
salida campeona); que si suspende vuelve con los arreglos en sencillo; y que un archivo raro o demasiado largo se
rechaza con su motivo, sin gastar IA.

    python pruebas/simulacro_ventanilla.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="simulacro-ventanilla-")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), os.path.join(TMP, "privado"))
os.environ["PRIVADO"] = os.path.join(TMP, "privado")
os.environ["MEMORIA_DIR"] = os.path.join(TMP, "privado", "memoria")
os.environ["CARTERO_PRUEBA"] = "1"
os.environ["NTFY_TEMA"] = "prueba"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["GEMINI_API_KEY"] = "falsa"

from bots.comun import gemini, privado  # noqa: E402
from bots.juzgado import ventanilla  # noqa: E402

MODO = {"nota": 94, "vista": True}
VISTO = {"video": 0, "secretario": 0}


def falso(texto, imagenes=(), video=None, **kw):
    if "Ventanilla del Juzgado" in texto:
        VISTO["video"] += 1
        assert video and os.path.exists(video), "la IA tiene que ver el vídeo entero"
        if not MODO["vista"]:
            raise gemini.SinIA("sin cupo de vídeo")
        return {"narracion": "Nadie te cuenta esto del dinero: ahorra primero y gasta después.", "texto_pantalla":
                "AHORRA PRIMERO", "de_que_va": "un consejo de ahorro", "titulo": "El truco que nadie te cuenta 💸",
                "texto_redes": "Ahorra primero y gasta después. ¿Lo haces? #ahorro #dinero #finanzas", "hashtags": ["#ahorro"],
                "musica": "no", "idioma_voz": "es"}
    if "miembro del jurado popular" in texto:
        return {"voto": "inocente" if MODO["nota"] >= 90 else "culpable", "nota": MODO["nota"], "porque": "me para el dedo"}
    if texto.startswith("Eres el Juzgado de") and "defensa" in texto and '"fiscalia"' in texto:
        return {"defensa": "Engancha desde el segundo uno.", "fiscalia": "El final se alarga.", "fallos_graves": []}
    if "Tres jueces deciden" in texto:
        voto = "sube" if MODO["nota"] >= 90 else "no"
        return {"votos": [{"juez": k, "voto": voto, "nota": MODO["nota"], "razon": f"razón de {k}"}
                          for k in ("gancho", "reloj", "calle")], "consejo": "Corta el final un segundo antes."}
    if "secretario del Juzgado" in texto:
        VISTO["secretario"] += 1
        return {"arreglos": ["Pon el texto grande desde el segundo 0.", "Corta el final un segundo antes.",
                             "Di la cifra en la primera frase."], "lo_bueno": "La voz se entiende muy bien."}
    if "gladiador del Coliseo" in texto:
        return {"titulo": "Ahorra primero: el truco que nadie te cuenta 💸", "texto": "¿Tú ahorras primero?",
                "hashtags": ["#ahorro", "#dinero", "#finanzas"], "por_que": "curiosidad"}
    if "Coliseo, combate" in texto:
        return {"critica_a_b": "flojo", "critica_b_a": "largo"}
    if "Juez ciego" in texto:
        return {"ganador": 1, "razon": "engancha más", "nota_1": 91, "nota_2": 80}
    raise AssertionError("pregunta inesperada: " + texto[:90])


gemini.preguntar = falso


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


def video(ruta, segundos, voz=True):
    entradas = ["-f", "lavfi", "-i", f"testsrc2=size=540x960:rate=30:duration={segundos}"]
    if voz:
        entradas += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    *(["-c:a", "aac", "-shortest"] if voz else []), ruta], check=True)
    return ruta


cuenta = next(iter(privado.config()["barrios"]))
alias = privado.alias(cuenta)
paso = lambda robot, texto: None   # noqa: E731

# 1. Un vídeo bueno: Jurado, Juzgado y Coliseo
t = tempfile.mkdtemp(dir=TMP)
r = ventanilla.juzgar(video(os.path.join(t, "bueno.mp4"), 8), {"cuenta": alias, "titulo": ""}, "p-bueno", t, paso)
comprobar(VISTO["video"] == 1, "la IA mira el vídeo entero (imagen y sonido)")
comprobar(r["estado"] == "aprobado" and r["nota"] == 94 and r["minimo"] >= 90, f"aprueba con {r.get('nota')}/100")
comprobar((r.get("jurado") or {}).get("inocente", 0) >= 7, "el Jurado popular vota el vídeo del dueño")
comprobar(bool(r.get("coliseo")) and r["coliseo"].get("campeon"), "pasa por el Coliseo y sale con la salida campeona")
comprobar(r["coliseo"]["titulo"].startswith("Ahorra primero") and len(r["coliseo"]["hashtags"]) <= 5,
          "la salida del Coliseo trae título y como mucho 5 hashtags")
comprobar(r["salida_antes"]["titulo"] == "El truco que nadie te cuenta 💸", "sin título del dueño, la IA le pone uno")
comprobar(not r.get("arreglos"), "si aprueba no hay arreglos")
ventanilla.guardar(dict(r, intentos=1))
comprobar(bool(privado.leer(os.path.join("estado", "propios", "p-bueno.json"))), "deja el resultado para la app")

# 2. Un vídeo flojo: suspende y vuelve con los arreglos
MODO["nota"] = 72
t = tempfile.mkdtemp(dir=TMP)
r = ventanilla.juzgar(video(os.path.join(t, "flojo.mp4"), 8), {"cuenta": alias, "titulo": "Mi vídeo",
                                                                 "texto": "Texto mío #ahorro"}, "p-flojo", t, paso)
comprobar(r["estado"] == "suspendido" and r["nota"] == 72, "suspende con 72/100")
comprobar(len(r.get("arreglos") or []) >= 3 and r.get("lo_bueno"), "vuelve con 3 arreglos en sencillo y lo que funciona")
comprobar(r["salida_antes"]["titulo"] == "Mi vídeo" and r["salida_antes"]["texto"] == "Texto mío #ahorro",
          "respeta el título y el texto que puso el dueño")
comprobar(not r.get("coliseo"), "si suspende no pasa por el Coliseo")
comprobar(r.get("fiscalia") and len(r.get("votos") or []) == 3, "guarda lo que dijo la fiscalía y los 3 jueces")

# 3. Sin IA de vídeo: se juzga igual, con las fotos
MODO.update(nota=93, vista=False)
t = tempfile.mkdtemp(dir=TMP)
r = ventanilla.juzgar(video(os.path.join(t, "sinvista.mp4"), 6), {"cuenta": alias}, "p-sinvista", t, paso)
comprobar(r["estado"] == "aprobado", "si la IA no puede ver el vídeo, se juzga con las fotos y la voz")

# 4. Archivos que no valen: se rechazan sin gastar IA
antes = VISTO["video"]
t = tempfile.mkdtemp(dir=TMP)
raro = os.path.join(t, "raro.mp4")
open(raro, "w").write("esto no es un vídeo")
r = ventanilla.juzgar(raro, {"cuenta": alias}, "p-raro", t, paso)
comprobar(r["estado"] == "rechazado" and "no es un vídeo" in r["problema"], "un archivo que no es vídeo se rechaza")
r = ventanilla.juzgar(video(os.path.join(t, "largo.mp4"), 200, voz=False), {"cuenta": alias}, "p-largo", t, paso)
comprobar(r["estado"] == "rechazado" and "Dura 200 segundos" in r["problema"], "uno de más de 3 minutos se rechaza")
r = ventanilla.juzgar(video(os.path.join(t, "corto.mp4"), 4), {"cuenta": "no-existe"}, "p-cuenta", t, paso)
comprobar(r["estado"] == "error" and "cuenta" in r["problema"], "sin cuenta conocida, pide elegir la cuenta")
comprobar(VISTO["video"] == antes, "los rechazados no gastan IA")

# 5. Los avisos al móvil no llevan nombres de cuentas
from bots.central import cartero  # noqa: E402
cartero.ENVIADOS.clear()
ventanilla.avisar({"estado": "suspendido", "nota": 72, "minimo": 90, "arreglos": ["Pon el texto desde el segundo 0."]})
ventanilla.avisar({"estado": "aprobado", "nota": 94, "coliseo": {"campeon": "x"}})
textos = " ".join(e["titulo"] + e["mensaje"] for e in cartero.ENVIADOS)
nombre = privado.config()["barrios"][cuenta].get("nombre") or cuenta
comprobar(cuenta not in textos and nombre not in textos, "los avisos no dicen el nombre de la cuenta")
print("Simulacro de la Ventanilla: todo bien")
