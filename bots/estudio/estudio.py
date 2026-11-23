"""El estudio de animación: hace vídeos animados (no imágenes fijas) con el estilo de las cuentas del dueño.

Tres fórmulas, sacadas de sus vídeos más virales (estado/referencias/ del repositorio privado):
- «idolo» (la sombra del ídolo): un famoso bajo un foco; del «nació con un don» a la realidad del trabajo diario;
  acaba con una pregunta. Con voz de hombre.
- «carrera» (A contra B): dos o tres personas parten igual; pasan los días, los contadores suben y una gana. Sin voz,
  solo música y efectos.
- «frases» (frases con iconos): frases grandes con una palabra resaltada y un icono que se dibuja. Con voz.

Gemini escribe el guion por escenas; la voz sale de edge-tts; escena.html dibuja cada fotograma (render.js, con el
navegador) y ffmpeg junta voz, música y efectos hechos por nosotros.

Uso:  python bots/estudio/estudio.py --canal barrio-2 [--formato idolo] [--salida carpeta] [--prueba]
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import musica  # noqa: E402
import voz as locutor  # noqa: E402
from bots.comun import gemini, privado  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
FORMATOS = ("idolo", "carrera", "frases")
CON_VOZ = {"idolo": True, "carrera": False, "frases": True}

ESQUEMAS = {
    "idolo": """{"formato": "idolo", "titulo": "título corto con gancho",
 "famoso": {"nombre": "APELLIDO EN MAYÚSCULAS", "camiseta": "#hex del color principal de su equipo o selección",
            "rayas": "#hex o null", "numero": "su dorsal o null", "piel": "#hex", "pelo": "#hex", "pantalon": "#hex"},
 "escenas": [{"voz": "lo que dice la voz en esta escena (1 o 2 frases)", "texto": "lo que se lee arriba (igual o más corto)",
              "resaltar": ["1 o 2 palabras clave del texto"], "accion": "quieto|camina|celebra|triste|trabaja|chuta|piensa",
              "props": ["0 a 3 iconos de la lista"], "sombras": ["0 a 4 etiquetas de figuras grises detrás, p. ej. EGO, EXCUSAS, MAGIA"],
              "etiqueta": "palabra encima del famoso o null", "contador": null}],
 "final": {"lineas": [{"texto": "frase final contundente", "resaltar": ["..."]}], "pregunta": "pregunta directa al espectador"}}""",
    "carrera": """{"formato": "carrera", "titulo": "título corto con gancho", "titulo_arriba": "A vs B (en mayúsculas)",
 "columnas": [{"etiqueta": "NOMBRE A", "color": "#hex", "desde": 0, "hasta": 1, "unidad": "lo que cuenta", "curva": "sube|cae", "techo": 1},
              {"etiqueta": "NOMBRE B", "color": "#hex", "desde": 0, "hasta": 17, "unidad": "...", "curva": "sube", "techo": 1}],
 "objeto": "ladrillos|monedas", "dias": ["L", "M", "X", "J", "V", "S", "D"],
 "escenas": [{"texto": "frase corta", "resaltar": ["..."], "dia": "L", "progreso": [0.1, 0.1], "poses": ["trabaja", "trabaja"]}],
 "final": {"lineas": [{"texto": "...", "resaltar": ["..."], "color": "#hex"}], "pregunta": "¿Cuál eres tú?"}}""",
    "frases": """{"formato": "frases", "titulo": "título corto con gancho",
 "escenas": [{"voz": "lo que dice la voz", "texto": "frase muy corta en mayúsculas (2 a 6 palabras)", "resaltar": ["..."],
              "icono": "un icono de la lista"}],
 "final": {"lineas": [{"texto": "...", "resaltar": ["..."]}], "pregunta": "llamada a la acción corta"}}""",
}

ICONOS = ("balon trofeo reloj_arena calendario bombilla puerta fuego lista moneda libro movil montana pesa cohete corazon "
          "estrella rayo check cruz pregunta reloj grafico personas cerebro hucha pizarra ladrillos foco").split()

PLANTILLA = """Eres el guionista de una cuenta de TikTok e Instagram llamada «{nombre}» ({tema}). Sus vídeos más virales
siguen esta fórmula (sacada de sus propios vídeos):
{formula}

Ejemplos reales de sus vídeos (escena a escena):
{ejemplos}

Lo que ha aprendido la cuenta (lo del dueño manda):
{lecciones}

Ya hechos (no repitas tema ni famoso en la misma semana):
{hechos}
{extra}
Escribe UN vídeo nuevo con el formato «{formato}», en {idioma}, que enganche desde el primer segundo y haga que la gente
quiera saber cómo acaba. Duración: {duracion}. Entre {escenas_min} y {escenas_max} escenas más el final.
Iconos disponibles para "props" e "icono": {iconos}.
Si sale una persona famosa, que sea de las que más interesan ahora (deportistas, cantantes, empresarios muy conocidos) y
cuenta solo cosas ciertas y conocidas de su vida; nada inventado ni ofensivo. Sin logotipos ni marcas.
Devuelve SOLO un JSON con esta forma (más "descripcion", "hashtags" (3-5), "texto_instagram" y "texto_tiktok"):
{esquema}"""


def referencias(clave):
    """La fórmula y 3 ejemplos de los vídeos de referencia del dueño, si están analizados."""
    d = privado.leer(os.path.join("estado", "referencias", f"{privado.alias(clave)}.json"), {}) or {}
    formula = json.dumps(d.get("formula") or {}, ensure_ascii=False)[:6000]
    ejemplos = []
    for nombre, v in list((d.get("videos") or {}).items())[:4]:
        if isinstance(v, dict) and v.get("escenas"):
            ejemplos.append(f"- {v.get('formato')} · {v.get('tema')}: " + " / ".join(
                str(e.get("texto_pantalla", "")) for e in v["escenas"][:8]))
    return formula or "(sin fórmula todavía)", "\n".join(ejemplos) or "(sin ejemplos)"


def elegir_formato(clave, pedido=None):
    if pedido in FORMATOS:
        return pedido
    hechos = (privado.leer(os.path.join("estado", "estudio", f"{privado.alias(clave)}.json"), {}) or {}).get("videos", [])
    usados = [v.get("formato") for v in hechos[-6:]]
    # el que menos se ha usado últimamente; los «ídolos» pesan el doble (son los que más funcionan)
    return min(FORMATOS, key=lambda f: usados.count(f) / (2 if f == "idolo" else 1))


def guionizar(canal, formato, lecciones):
    clave = canal["clave"]
    formula, ejemplos = referencias(clave)
    hechos = (privado.leer(os.path.join("estado", "estudio", f"{privado.alias(clave)}.json"), {}) or {}).get("videos", [])
    rangos = {"idolo": ("25-30 segundos", 6, 8), "carrera": ("14-18 segundos", 5, 7), "frases": ("20-26 segundos", 5, 7)}
    duracion, emin, emax = rangos[formato]
    texto = PLANTILLA.format(nombre=canal["nombre"], tema=canal.get("tema", ""), formula=formula, ejemplos=ejemplos,
                             lecciones=lecciones, hechos="\n".join(f"- {h.get('titulo')}" for h in hechos[-30:]) or "- (nada)",
                             extra="", formato=formato, idioma={"es": "español de España", "nl": "neerlandés"}.get(
                                 canal.get("idioma", "es")[:2], "español"),
                             duracion=duracion, escenas_min=emin, escenas_max=emax, iconos=", ".join(ICONOS),
                             esquema=ESQUEMAS[formato])
    for _ in range(3):
        g = gemini.preguntar(texto, temperatura=0.95)
        if isinstance(g, list) and g:
            g = g[0]
        if isinstance(g, dict) and g.get("escenas") and g.get("final"):
            g["formato"] = formato
            for e in g["escenas"]:
                e["props"] = [p for p in e.get("props", []) or [] if p in ICONOS][:3]
                if e.get("icono") not in ICONOS:
                    e["icono"] = "estrella" if formato == "frases" else None
            return g
        texto += "\n\nEl intento anterior no tenía la forma pedida. Devuelve SOLO el JSON."
    raise ValueError("Gemini no dio un guion válido para el estudio")


def tiempos_con_voz(g, carpeta, canal):
    """Graba la voz de todas las escenas y reparte el tiempo según lo que tarda en decir cada una."""
    narracion = " ".join(e.get("voz") or e.get("texto", "") for e in g["escenas"])
    asyncio.run(locutor.generar(narracion, canal.get("voz_estudio", "es-ES-AlvaroNeural"),
                                canal.get("velocidad_estudio", "-4%"), canal.get("tono_estudio", "-3Hz"), carpeta))
    locutor.apretar(carpeta, hueco_max=0.35)
    palabras = json.load(open(os.path.join(carpeta, "palabras.json"), encoding="utf-8"))
    cuenta = [max(1, len(re.findall(r"\w+", e.get("voz") or e.get("texto", "")))) for e in g["escenas"]]
    total_esc = sum(cuenta)
    escala = len(palabras) / total_esc if total_esc else 1
    acumulado, inicio = 0, 0.0
    for i, e in enumerate(g["escenas"]):
        e["inicio"] = 0.0 if i == 0 else palabras[min(len(palabras) - 1, int(round(acumulado * escala)))]["inicio"] - 0.05
        acumulado += cuenta[i]
    for i, e in enumerate(g["escenas"]):
        e["fin"] = g["escenas"][i + 1]["inicio"] if i + 1 < len(g["escenas"]) else palabras[-1]["fin"] + 0.5
    inicio_final = g["escenas"][-1]["fin"]
    g["final"]["inicio"] = inicio_final
    g["duracion"] = round(inicio_final + 3.2, 2)
    return os.path.join(carpeta, "voz.mp3")


def tiempos_sin_voz(g):
    t = 0.0
    previo = None
    for e in g["escenas"]:
        largo = max(1.8, min(3.2, 1.2 + len(str(e.get("texto", ""))) * 0.035))
        e["inicio"], e["fin"] = round(t, 2), round(t + largo, 2)
        if previo is not None:
            e["progresoAntes"] = previo
        previo = e.get("progreso")
        t += largo
    g["final"]["inicio"] = round(t, 2)
    g["duracion"] = round(t + 3.4, 2)


def efectos(g, carpeta):
    """Pista de efectos: un «whoosh» en cada cambio de escena, un «pop» cuando salen los iconos y un golpe al final."""
    sonidos = {
        "whoosh": "anoisesrc=d=0.4:c=pink:a=0.5,highpass=f=500,lowpass=f=3500,afade=t=in:d=0.15,afade=t=out:st=0.2:d=0.2",
        "pop": "sine=f=880:d=0.09,afade=t=out:d=0.09,volume=0.6",
        "golpe": "sine=f=65:d=0.45,afade=t=out:d=0.45,volume=1.6",
    }
    rutas = {}
    for nombre, expr in sonidos.items():
        rutas[nombre] = os.path.join(carpeta, f"{nombre}.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", expr, rutas[nombre]], check=True)
    eventos = []
    for i, e in enumerate(g["escenas"]):
        if i:
            eventos.append(("whoosh", e["inicio"]))
        if e.get("props") or e.get("icono"):
            eventos.append(("pop", e["inicio"] + 0.38))
    eventos.append(("golpe", g["final"]["inicio"] + 0.1))
    entradas, filtros = [], []
    for n, (nombre, cuando) in enumerate(eventos):
        entradas += ["-i", rutas[nombre]]
        ms = int(cuando * 1000)
        filtros.append(f"[{n}:a]adelay={ms}|{ms}[e{n}]")
    salida = os.path.join(carpeta, "efectos.wav")
    mezcla = "".join(f"[e{n}]" for n in range(len(eventos)))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex",
                    ";".join(filtros) + f";{mezcla}amix=inputs={len(eventos)}:normalize=0,volume=0.5[s]", "-map", "[s]",
                    "-t", str(g["duracion"]), salida], check=True)
    return salida


def hacer(canal, lecciones="", formato=None, carpeta=None, avisar=print):
    """Hace un vídeo completo. Devuelve (ruta del mp4, guion)."""
    carpeta = carpeta or tempfile.mkdtemp(prefix="estudio-")
    os.makedirs(carpeta, exist_ok=True)
    formato = elegir_formato(canal["clave"], formato or canal.get("formato"))
    avisar(f"estudio: guion «{formato}»")
    g = guionizar(canal, formato, lecciones)
    voz = None
    if CON_VOZ[formato]:
        avisar("estudio: voz")
        voz = tiempos_con_voz(g, carpeta, canal)
    else:
        tiempos_sin_voz(g)
    with open(os.path.join(carpeta, "guion_estudio.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)
    avisar(f"estudio: dibujando {g['duracion']} s fotograma a fotograma")
    mudo = os.path.join(carpeta, "imagen.mp4")
    subprocess.run(["node", os.path.join(AQUI, "render.js"), os.path.join(carpeta, "guion_estudio.json"), mudo, "30"],
                   check=True)
    avisar("estudio: sonido")
    pista = musica.crear(canal.get("musica", "energia" if formato == "carrera" else "calma"), g["duracion"],
                         os.path.join(carpeta, "musica.m4a"))
    fx = efectos(g, carpeta)
    entradas = ["-i", mudo, "-i", pista, "-i", fx]
    if voz:
        entradas += ["-i", voz]
        mezcla = "[1:a]volume=0.55[m];[2:a]volume=0.9[f];[3:a]volume=1.0[v];[v][m][f]amix=inputs=3:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5[a]"
    else:
        mezcla = "[1:a]volume=1.0[m];[2:a]volume=1.0[f];[m][f]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5[a]"
    salida = os.path.join(carpeta, "video.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", mezcla, "-map", "0:v",
                    "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", str(g["duracion"]),
                    "-movflags", "+faststart", salida], check=True)
    return salida, g


def apuntar(clave, g):
    ruta = os.path.join("estado", "estudio", f"{privado.alias(clave)}.json")
    d = privado.leer(ruta, {}) or {}
    d["videos"] = (d.get("videos", []) + [{"titulo": g.get("titulo"), "formato": g.get("formato"),
                                           "famoso": (g.get("famoso") or {}).get("nombre"), "fecha": privado.ahora()}])[-200:]
    privado.escribir(ruta, d)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--canal", required=True)
    p.add_argument("--formato", choices=FORMATOS)
    p.add_argument("--salida", default=None)
    a = p.parse_args()
    canal = privado.canal(privado.resolver(a.canal))
    video, g = hacer(canal, formato=a.formato, carpeta=a.salida,
                     avisar=lambda t: print(privado.limpiar(t), flush=True))
    print(privado.limpiar(f"estudio: vídeo listo ({g['duracion']} s, {g['formato']})"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
