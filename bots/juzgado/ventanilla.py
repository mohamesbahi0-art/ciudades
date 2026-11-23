"""La Ventanilla del Juzgado: juzga los vídeos que sube el dueño desde la app («Juzga mi vídeo»).

El dueño sube su vídeo en la app, elige la cuenta y, si quiere, pone título y texto. La ronda de Claude lo deja en una
rama temporal del repositorio privado, juicio/<codigo>, con el vídeo y peticion.json. Aquí, para cada rama:
1. Mira el vídeo entero con la IA (imagen y sonido): lo que dice la voz, el texto del principio y de qué va.
2. El Jurado popular (12 pieles) lo vota como si lo viera en el móvil.
3. El Juzgado completo (detectives, abogados, 3 jueces y el Juez Mayor) lo juzga con la nota mínima de esa cuenta.
4. Si aprueba, pasa por el Coliseo: 8 gladiadores pelean por su título, texto y hashtags, y gana el mejor.
5. Si no aprueba, junta los fallos y escribe en sencillo qué cambiar para que pase.
Deja el resultado en estado/propios/<codigo>.json (la ronda de Claude lo copia a la app), avisa al móvil (Cartero) y
borra la rama. Los registros públicos solo llevan el código, nunca el nombre de la cuenta.

Uso:  python bots/juzgado/ventanilla.py [--codigo X]
      python bots/juzgado/ventanilla.py --video prueba.mp4 --cuenta <clave> [--titulo "..."]   (prueba, sin rama)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.central import cartero  # noqa: E402
from bots.coliseo import coliseo  # noqa: E402
from bots.comun import gemini, ia, privado  # noqa: E402
from bots.juzgado import jurado, tribunal  # noqa: E402

ROBOT = "ventanilla"
RAMAS = "refs/heads/juicio/*"
EXTENSIONES = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".3gp")
SEGUNDOS = (2, 180)                 # de 2 segundos a 3 minutos
IDIOMAS = {"es": "español", "nl": "neerlandés", "en": "inglés"}

MIRAR = """Eres la Ventanilla del Juzgado de una fábrica de vídeos cortos. El dueño ha subido SU PROPIO vídeo para
{donde} (cuenta «{nombre}», en {idioma}; tema de la cuenta: {tema}). Míralo y escúchalo entero, sin juzgarlo todavía, y
devuelve SOLO un JSON:
{{"narracion": "lo que dice la voz, palabra por palabra, en su idioma (vacío si no habla nadie)",
  "texto_pantalla": "el texto grande que se lee en los 2 primeros segundos (vacío si no hay)",
  "de_que_va": "una frase en español de España",
  "titulo": "un título corto con gancho, en {idioma}",
  "texto_redes": "un texto para pegar al subirlo, en {idioma}: 1 o 2 frases y de 3 a 5 hashtags del nicho",
  "hashtags": ["#..."],
  "musica": "sí" o "no",
  "idioma_voz": "es, nl, en..."}}"""

ARREGLOS = """Eres el secretario del Juzgado de una fábrica de vídeos cortos. El dueño ha subido su propio vídeo para
{donde} y no ha llegado al mínimo de esa cuenta: ha sacado {nota}/100 y hace falta {minimo}.
Lo que han dicho de él:
- La defensa: {defensa}
- La fiscalía: {fiscalia}
- Los jueces: {votos}
- El Jurado popular (los que votaron en contra): {jurado}
- Fallos graves: {fallos}
- Medidas del vídeo: {medidas}
Escríbele al dueño, en español de España sencillo y sin tecnicismos, de 3 a 5 arreglos concretos, del más importante
al menos, para que el vídeo llegue a {minimo}. Cada arreglo, una frase que diga qué cambiar y dónde (en qué segundo, en
el texto, en la voz…). Nada de consejos de relleno. Devuelve SOLO un JSON:
{{"arreglos": ["...", "..."], "lo_bueno": "una frase con lo que sí funciona"}}"""


def _git(*args, texto=False):
    return subprocess.run(["git", "-C", privado.carpeta(), *args], capture_output=True, text=texto)


def _ffprobe(ruta, entradas):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entradas, "-of", "json", ruta],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        return {}


def segundos(ruta):
    try:
        return float(_ffprobe(ruta, "format=duration").get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        return 0.0


def tiene_video(ruta):
    return any(s.get("codec_type") == "video" for s in _ffprobe(ruta, "stream=codec_type").get("streams", []))


def ramas():
    r = _git("ls-remote", "origin", RAMAS, texto=True)
    if r.returncode != 0:
        return []
    return sorted(l.split("refs/heads/", 1)[-1].strip() for l in r.stdout.splitlines() if "refs/heads/" in l)


def sacar(rama, carpeta):
    """El vídeo y la petición que dejó la ronda de Claude en la rama juicio/<codigo>."""
    if _git("fetch", "-q", "--depth", "1", "origin", f"refs/heads/{rama}").returncode != 0:
        return None, {}
    nombres = _git("ls-tree", "--name-only", "FETCH_HEAD", texto=True).stdout.split("\n")
    peticion = {}
    if "peticion.json" in nombres:
        try:
            peticion = json.loads(_git("show", "FETCH_HEAD:peticion.json").stdout.decode("utf-8"))
        except ValueError:
            peticion = {}
    video = next((n for n in nombres if n.lower().endswith(EXTENSIONES)), None)
    if not video:
        return None, peticion
    destino = os.path.join(carpeta, "original" + os.path.splitext(video)[1].lower())
    with open(destino, "wb") as f:
        f.write(_git("show", f"FETCH_HEAD:{video}").stdout)
    return destino, peticion


def borrar_rama(rama):
    return _git("push", "-q", "origin", "--delete", rama).returncode == 0


def preparar(original, carpeta):
    """Una copia normal (vertical, h264) para los jueces, una pequeña para que la IA lo vea entero y su sonido."""
    normal = os.path.join(carpeta, "video.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", original, "-vf", "scale='min(1080,iw)':-2",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", normal], check=True)
    pequeno = os.path.join(carpeta, "pequeno.mp4")
    for altura, calidad in ((480, 30), (360, 34), (240, 38)):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", normal, "-vf", f"scale=-2:{altura}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(calidad), "-c:a", "aac", "-b:a", "64k",
                        pequeno], check=True)
        if os.path.getsize(pequeno) <= gemini.VIDEO_MAXIMO:
            break
    audio = os.path.join(carpeta, "voz.mp3")
    hecho = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", normal, "-vn", "-ac", "1", "-b:a", "64k", audio])
    return normal, pequeno, (audio if hecho.returncode == 0 and os.path.exists(audio) else None)


def mirar(pequeno, canal):
    """Lo que dice y enseña el vídeo (con Gemini, que ve y oye vídeos). Sin IA de vídeo, sigue sin transcripción."""
    idioma = IDIOMAS.get((canal.get("idioma") or "es")[:2], "español")
    donde = "YouTube Shorts" if canal.get("destino") == "youtube" else "TikTok e Instagram"
    if os.path.getsize(pequeno) > gemini.VIDEO_MAXIMO:
        return {}
    try:
        v = gemini.preguntar(MIRAR.format(donde=donde, nombre=canal.get("nombre", ""), idioma=idioma,
                                          tema=(canal.get("tema") or "")[:300]), video=pequeno, temperatura=0.2)
    except gemini.SinIA as e:
        print(f"ventanilla: la IA de vídeo no contesta ({str(e)[:80]}); se juzga con las fotos", flush=True)
        return {}
    if isinstance(v, list) and v:
        v = v[0]
    return v if isinstance(v, dict) else {}


def _hashtags(texto):
    return re.findall(r"#\w+", texto or "")


def guion_de(peticion, vista):
    """El «guion» del vídeo del dueño, con la forma que esperan el Jurado, el Juzgado y el Coliseo."""
    narracion = str(vista.get("narracion") or "").strip()
    texto = str(peticion.get("texto") or vista.get("texto_redes") or "").strip()
    titulo = str(peticion.get("titulo") or vista.get("titulo") or "Vídeo del dueño").strip()[:100]
    hashtags = _hashtags(texto) or [h if str(h).startswith("#") else f"#{h}" for h in vista.get("hashtags") or []][:5]
    return {"titulo": titulo, "texto_pantalla": str(vista.get("texto_pantalla") or "")[:120],
            "narracion": narracion or "(el vídeo no tiene voz, o no se ha podido oír)",
            "escenas": [{"voz": narracion, "texto": vista.get("texto_pantalla") or ""}],
            "texto_tiktok": texto, "texto_instagram": texto, "descripcion": texto, "hashtags": hashtags,
            "de_que_va": vista.get("de_que_va", ""), "propio": True}


def arreglos(v, minimo, canal):
    donde = "YouTube Shorts" if canal.get("destino") == "youtube" else "TikTok e Instagram"
    jur = v.get("jurado") or {}
    contra = "; ".join(f"{x.get('jurado')}: {x.get('porque')}" for x in jur.get("votos", []) if x.get("voto") == "culpable")
    votos = "; ".join(f"{x['juez']} ({x['nota']}/100): {x['razon']}" for x in v.get("votos", []))
    try:
        r = ia.preguntar(ARREGLOS.format(donde=donde, nota=v.get("total", "?"), minimo=minimo, defensa=v.get("defensa", ""),
                                         fiscalia=v.get("fiscalia", ""), votos=votos or "(no votaron)",
                                         jurado=contra[:1500] or "(nadie)", fallos=", ".join(v.get("fallos_graves") or [])
                                         or "ninguno", medidas=json.dumps(v.get("medidas") or {}, ensure_ascii=False)),
                         papel="juez", temperatura=0.3)
    except gemini.SinIA:
        r = None
    if isinstance(r, dict) and r.get("arreglos"):
        return [str(x) for x in r["arreglos"]][:5], str(r.get("lo_bueno") or "")
    sueltos = [x for x in (v.get("consejo"), v.get("fiscalia")) if x]       # sin IA: lo que dijeron, tal cual
    return sueltos[:3] or ["Los jueces no han dado detalles esta vez: prueba a subirlo otra vez más tarde."], ""


def cuenta_de(valor):
    """La clave de la cuenta, venga como venga de la app: la clave («terror»), el alias («barrio-2»), la cuenta con o
    sin @ («@grow.up.only») o su nombre («Overleef Dit»)."""
    v = str(valor or "").strip().lstrip("@")
    clave = privado.resolver(v)
    cfg = privado.config()
    if clave in cfg.get("canales", {}) or clave in cfg.get("barrios", {}):
        return clave
    bajo = clave.lower()
    for grupo in ("canales", "barrios"):
        for k, c in cfg.get(grupo, {}).items():
            if bajo in (k.lower(), str(c.get("cuenta") or "").lower().lstrip("@"), str(c.get("nombre") or "").lower()):
                return k
    return clave


def juzgar(original, peticion, codigo, trabajo, paso=print):
    """Pasa un vídeo del dueño por todo el Juzgado y el Coliseo. Devuelve el resultado (para la app)."""
    clave = cuenta_de(peticion.get("cuenta"))
    base = {"codigo": codigo, "cuenta": clave, "alias": privado.alias(clave) if clave else "",
            "recibido": peticion.get("subido") or peticion.get("creado"), "titulo_dueño": peticion.get("titulo", "")}
    try:
        canal = privado.canal(clave)
    except SystemExit:
        return dict(base, estado="error", problema="No sé de qué cuenta es: elige la cuenta al subirlo.")
    if not tiene_video(original):
        return dict(base, estado="rechazado", problema="El archivo no es un vídeo.")
    dura = segundos(original)
    if not SEGUNDOS[0] <= dura <= SEGUNDOS[1]:
        return dict(base, estado="rechazado", problema=f"Dura {round(dura)} segundos: tiene que durar entre "
                    f"{SEGUNDOS[0]} segundos y {SEGUNDOS[1] // 60} minutos.")
    normal, pequeno, audio = preparar(original, trabajo)
    paso("ventanilla", f"{codigo}: vídeo de {round(dura)} s; lo mira la IA")
    vista = mirar(pequeno, canal)
    g = guion_de(peticion, vista)
    idioma = IDIOMAS.get((canal.get("idioma") or "es")[:2], "español")
    donde = "YouTube Shorts" if canal["destino"] == "youtube" else "TikTok e Instagram"
    try:
        veredicto_jurado = jurado.deliberar(g, canal, {}, {"donde": donde, "idioma": idioma, "gancho": g["texto_pantalla"],
                                                           "prueba": False, "turno": f"propio-{codigo}", "intento": 1},
                                            forzar=True)
    except Exception as e:
        paso("jurado_popular", f"{codigo}: no se ha podido reunir ({type(e).__name__})")
        veredicto_jurado = None
    if veredicto_jurado:
        g["jurado"] = veredicto_jurado
        paso("jurado_popular", f"{codigo}: {veredicto_jurado['inocente']} inocente y {veredicto_jurado['culpable']} culpable")
    lecciones = privado.cuaderno("juez_guardia").para_el_prompt()
    v = tribunal.juzgar(normal, g, canal, lecciones, os.path.join(trabajo, "juicio"), audio=audio)
    if veredicto_jurado and not v.get("jurado"):
        v["jurado"] = veredicto_jurado
    minimo = tribunal.minima(canal)
    try:
        id_juicio = tribunal.guardar_juicio(clave, g, v)
    except Exception:
        id_juicio = None
    paso("juez_mayor", f"{codigo}: {v.get('veredicto')} ({v.get('total', '-')}/100, hace falta {minimo})")
    jur = v.get("jurado") or {}
    resultado = dict(base, estado=v.get("veredicto") if v.get("veredicto") in ("aprobado", "suspendido") else "sin_juicio",
                     nota=v.get("total"), minimo=minimo, segundos=round(dura, 1), juicio=id_juicio,
                     tribunal=v.get("tribunal"), defensa=v.get("defensa", ""), fiscalia=v.get("fiscalia", ""),
                     votos=v.get("votos", []), consejo=v.get("consejo", ""), fallos_graves=v.get("fallos_graves") or [],
                     medidas=v.get("medidas") or {},
                     jurado={"inocente": jur.get("inocente"), "culpable": jur.get("culpable"),
                             "en_contra": [{"quien": x.get("jurado"), "porque": x.get("porque")}
                                           for x in jur.get("votos", []) if x.get("voto") == "culpable"][:6],
                             "a_favor": [{"quien": x.get("jurado"), "porque": x.get("porque")}
                                         for x in jur.get("votos", []) if x.get("voto") == "inocente"][:4]} if jur else None,
                     visto={"narracion": g["narracion"][:1500], "texto_pantalla": g["texto_pantalla"],
                            "de_que_va": g.get("de_que_va", "")},
                     salida_antes={"titulo": g["titulo"], "texto": g["texto_tiktok"], "hashtags": g["hashtags"]})
    if v.get("veredicto") == "aprobado":
        nuevo = coliseo.luchar(clave, canal, g, v, paso=paso, forzar=True)
        if nuevo.get("coliseo"):
            texto = nuevo.get("descripcion") if canal["destino"] == "youtube" else nuevo.get("texto_tiktok")
            resultado["coliseo"] = dict(nuevo["coliseo"], titulo=nuevo.get("titulo"), texto=texto,
                                        hashtags=nuevo.get("hashtags") or [])
    else:
        resultado["arreglos"], resultado["lo_bueno"] = arreglos(v, minimo, canal)
    return resultado


def avisar(r):
    """El aviso al móvil (sin nombres de cuentas)."""
    if r.get("estado") == "aprobado":
        extra = " El Coliseo le ha puesto título, texto y hashtags." if r.get("coliseo") else ""
        return cartero.avisar(f"⚖️ Tu vídeo ha aprobado ({r.get('nota')}/100)",
                              f"Pasa el Juzgado.{extra} Lo tienes en la app, en «Juzga mi vídeo».", etiqueta="tada")
    if r.get("estado") == "suspendido":
        primero = (r.get("arreglos") or [""])[0]
        return cartero.avisar(f"⚖️ Tu vídeo no pasa ({r.get('nota')}/100, hace falta {r.get('minimo')})",
                              (f"Lo más importante: {primero} " if primero else "")
                              + "Tienes todos los fallos y cómo arreglarlos en la app, en «Juzga mi vídeo».",
                              etiqueta="scales")
    if r.get("problema") and r.get("estado") == "rechazado":      # con «error» se reintenta: todavía no se avisa
        return cartero.avisar("⚖️ No he podido juzgar tu vídeo", f"{r['problema']} Míralo en la app, en «Juzga mi vídeo».",
                              etiqueta="scales")
    return False


def guardar(r):
    r["juzgado"] = privado.ahora()
    privado.guardar_estado(os.path.join("propios", f"{r['codigo']}.json"), r)
    c = privado.cuaderno(ROBOT)
    c.apuntar("juicio_propio", {"codigo": r["codigo"], "cuenta": r.get("alias"), "estado": r.get("estado"),
                                "nota": r.get("nota"), "minimo": r.get("minimo")})
    c.guardar()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--codigo", help="solo esta rama (juicio/<codigo>)")
    p.add_argument("--video", help="prueba: juzga este archivo sin rama")
    p.add_argument("--cuenta", help="prueba: la cuenta (clave o alias)")
    p.add_argument("--titulo", default="")
    a = p.parse_args()
    paso = lambda robot, texto: print(privado.limpiar(f"[{robot}] {texto}"), flush=True)   # noqa: E731
    if a.video:
        with tempfile.TemporaryDirectory() as t:
            r = juzgar(a.video, {"cuenta": a.cuenta, "titulo": a.titulo}, "prueba", t, paso)
        print(json.dumps({k: r.get(k) for k in ("estado", "nota", "minimo", "arreglos", "coliseo", "problema")},
                         ensure_ascii=False, indent=1))
        return 0
    lista = [f"juicio/{a.codigo}"] if a.codigo else ramas()
    if not lista:
        print("ventanilla: no hay vídeos del dueño esperando")
        return 0
    for rama in lista:
        codigo = rama.split("/", 1)[-1]
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,60}", codigo):
            continue
        with tempfile.TemporaryDirectory() as t:
            original, peticion = sacar(rama, t)
            if not original:
                r = {"codigo": codigo, "estado": "error", "problema": "No he encontrado el vídeo en el buzón."}
            else:
                try:
                    r = juzgar(original, peticion, codigo, t, paso)
                except Exception as e:      # un vídeo roto no para a los demás
                    print(f"ventanilla: {codigo}: fallo {type(e).__name__}", flush=True)
                    r = {"codigo": codigo, "estado": "error", "problema": "No he podido juzgarlo por un fallo mío: "
                         "lo vuelvo a intentar solo en la siguiente vuelta.", "cuenta": cuenta_de(peticion.get("cuenta"))}
        antes = privado.leer(os.path.join("estado", "propios", f"{codigo}.json"), {}) or {}
        r["intentos"] = int(antes.get("intentos") or 0) + 1
        if r.get("estado") == "error" and r["intentos"] >= 3:
            r["problema"] = "No he podido juzgarlo después de 3 intentos. Súbelo otra vez, por favor."
            r["estado"] = "rechazado"
        guardar(r)
        if r.get("estado") != "error":     # con un fallo nuestro la rama se queda para el siguiente intento
            borrar_rama(rama)
        try:
            avisar(r)
        except Exception:
            pass
        paso(ROBOT, f"{codigo}: {r.get('estado')} {r.get('nota') or ''}".strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
