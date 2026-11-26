"""Rehacer un vídeo de «Para subir» con otra voz o con el muñeco narrador, sin reescribir el guion.

Lo pidió el dueño el 26 nov: el vídeo de una cuenta ya aprobado por el Juzgado, igual, pero con el muñeco y la voz nueva,
para subirlo ya. Coge el guion guardado con el vídeo (estado/guiones/), busca otra vez las fotos libres, graba la voz que
tenga ahora la cuenta, lo monta y cambia el vídeo de la bandeja (mismo nombre). No pasa otra vez por el Juzgado: el guion
es el mismo que ya aprobó (lo dijo el dueño).

    python bots/central/rehacer.py --cuenta barrio-3            (el último pendiente de esa cuenta)
"""
import argparse
import asyncio
import glob
import json
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from bots.central import fotografo, montador  # noqa: E402
from bots.comun import almacen, privado  # noqa: E402
import voz as locutor  # noqa: E402

EMOCIONES = ("enfadado", "sorprendido", "serio", "triste", "pensativo", "contento")


def caras(escenas):
    """Si el guion no trae las caras del muñeco, las pone según la frase (que cambien a menudo)."""
    for n, e in enumerate(escenas):
        if e.get("emocion") in EMOCIONES:
            continue
        t = str(e.get("texto") or "").lower()
        if "?" in t:
            e["emocion"] = "pensativo"
        elif "!" in t or any(c.isdigit() for c in t) or any(w in t for w in ("miljoen", "record", "wereld", "beste")):
            e["emocion"] = "sorprendido"
        elif any(w in t for w in ("stierf", "overleed", "operatie", "verloor", "ziek", "dood")):
            e["emocion"] = "triste"
        elif any(w in t for w in ("won", "kampioen", "goud", "succes", "rijk")):
            e["emocion"] = "contento"
        else:
            e["emocion"] = ("enfadado", "serio", "pensativo")[n % 3]
    return escenas


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--cuenta", required=True, help="alias de la cuenta (barrio-N)")
    a = p.parse_args(argv)
    clave = privado.resolver(a.cuenta)
    canal = privado.canal(clave)
    docs = []
    for f in glob.glob(os.path.join(privado.carpeta(), "parasubir", "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if d.get("barrio") == clave and d.get("estado") == "pendiente" and d.get("guion_id"):
            docs.append((d.get("creado", ""), f, d))
    if not docs:
        print(f"{a.cuenta}: no hay ningún vídeo pendiente con su guion guardado")
        return 1
    docs.sort()
    guion_id = docs[-1][2]["guion_id"]
    g = (privado.leer(os.path.join("estado", "guiones", f"{guion_id}.json"), {}) or {}).get("guion")
    if not g:
        print(f"{a.cuenta}: falta el guion guardado")
        return 1
    trabajo = tempfile.mkdtemp(prefix="rehacer-")
    g["escenas"] = caras(g["escenas"])
    g["narracion"] = " ".join(e.get("voz") or e.get("texto", "") for e in g["escenas"])
    print(f"{a.cuenta}: rehaciendo su último vídeo ({len(g['escenas'])} escenas)", flush=True)
    imagenes, origen = fotografo.fotografiar(g["escenas"], os.path.join(trabajo, "fotos"), persona=str(g.get("persona") or ""))
    print(f"{a.cuenta}: {len(imagenes) - imagenes.count(None)}/{len(imagenes)} escenas con foto libre", flush=True)
    asyncio.run(locutor.generar(g["narracion"], canal.get("voz"), canal.get("velocidad", "+0%"), "+0Hz", trabajo))
    print(f"{a.cuenta}: voz con {locutor.MOTOR.get('motor')}", flush=True)
    locutor.apretar(trabajo)
    g["narrador"] = bool(canal.get("narrador"))
    salida = os.path.join(trabajo, f"{guion_id}.mp4")
    montador.montar(g, imagenes, os.path.join(trabajo, "voz.mp3"), os.path.join(trabajo, "palabras.json"), salida)
    segundos = montador.duracion(salida)
    enlace = almacen.guardar("para-subir", salida, f"{guion_id}.mp4")
    for _, f, d in docs:
        if d.get("guion_id") == guion_id:
            d.update(video=enlace, duracion=round(segundos, 1), voz=locutor.MOTOR.get("motor"), narrador=g["narrador"],
                     rehecho=privado.ahora())
            json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{a.cuenta}: listo, vídeo de {segundos:.1f} s cambiado en la bandeja", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
