"""Turno de un canal en la Ciudad Central: el Escritor escribe, el Locutor pone la voz, el Dibujante dibuja, el Montador
monta, el Juez de guardia juzga y, si no es una prueba, el Subidor lo programa a su hora. Cada robot apunta en su cuaderno
lo que ha hecho, y el estado queda en el repositorio privado para la app.

Uso:  python bots/central/turno.py --canal terror [--prueba] [--salida carpeta]
      python bots/central/turno.py --peticion peticiones/prueba.json --prueba --salida privado/pruebas
"""
import argparse
import asyncio
import datetime as dt
import json
import os
import shutil
import sys
import traceback

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from bots.central import dibujante, escritor, montador  # noqa: E402
from bots.comun import privado  # noqa: E402
from bots.juzgado import juez_guardia  # noqa: E402
import voz as locutor  # noqa: E402  (herramientas/voz.py)

ROBOTS = ("escritor", "locutor", "dibujante", "montador", "juez_guardia", "subidor")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--canal")
    p.add_argument("--peticion")
    p.add_argument("--prueba", action="store_true", help="hace el vídeo pero no lo sube")
    p.add_argument("--salida", default="trabajo")
    a = p.parse_args()
    clave = a.canal or json.load(open(a.peticion, encoding="utf-8"))["canal"]
    canal = privado.canal(clave)
    hoy = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d-%H%M")
    trabajo = os.path.join(a.salida, f"{hoy}-{clave}")
    os.makedirs(trabajo, exist_ok=True)
    cuadernos = {r: privado.cuaderno(r) for r in ROBOTS}
    registro = []

    def paso(robot, texto):
        linea = f"[{dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%S')}] {robot}: {texto}"
        print(linea, flush=True)
        registro.append(linea)

    resumen = {"canal": clave, "nombre": canal["nombre"], "prueba": a.prueba, "empezado": privado.ahora()}
    try:
        paso("escritor", "escribiendo el guion")
        g = escritor.escribir(canal, cuadernos["escritor"].para_el_prompt(), privado.titulos_recientes(clave))
        json.dump(g, open(os.path.join(trabajo, "guion.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        id_guion = cuadernos["escritor"].apuntar("guion", {"canal": clave, "titulo": g["titulo"], "idea": g.get("idea"),
                                                           "prueba": a.prueba})
        paso("escritor", f"«{g['titulo']}» ({len(g['escenas'])} escenas)")

        paso("locutor", f"grabando la voz ({canal.get('voz')})")
        asyncio.run(locutor.generar(g["narracion"], canal.get("voz", "es-MX-JorgeNeural"), "+10%", "+0Hz", trabajo))
        cuadernos["locutor"].apuntar("voz", {"canal": clave, "guion": id_guion})

        paso("dibujante", f"pidiendo {len(g['escenas'])} dibujos a AI Horde ({canal.get('dibujos')})")
        imagenes = dibujante.dibujar(g["escenas"], canal.get("dibujos", "AlbedoBase XL (SDXL)"),
                                     os.path.join(trabajo, "dibujos"))
        faltan = imagenes.count(None)
        cuadernos["dibujante"].apuntar("dibujos", {"canal": clave, "pedidos": len(imagenes), "faltan": faltan})
        if faltan > 2:
            raise RuntimeError(f"faltan {faltan} dibujos de {len(imagenes)}")
        paso("dibujante", f"{len(imagenes) - faltan}/{len(imagenes)} dibujos hechos")

        paso("montador", "montando el vídeo")
        video = montador.montar(g, imagenes, os.path.join(trabajo, "voz.mp3"), os.path.join(trabajo, "palabras.json"),
                                os.path.join(trabajo, "video.mp4"))
        cuadernos["montador"].apuntar("montaje", {"canal": clave, "guion": id_guion,
                                                  "segundos": round(montador.duracion(video), 1)})

        paso("juez_guardia", "juzgando el vídeo")
        v = juez_guardia.juzgar(video, g, canal, cuadernos["juez_guardia"].para_el_prompt(), os.path.join(trabajo, "juicio"))
        id_juicio = cuadernos["juez_guardia"].apuntar("juicio", {"canal": clave, "guion": id_guion,
                                                                 "veredicto": v["veredicto"], "total": v.get("total")})
        cuadernos["escritor"].nota(id_guion, v.get("total"), "nota del Juez de guardia", v.get("consejo", ""))
        paso("juez_guardia", f"{v['veredicto']} ({v.get('total', '-')}/100) {v.get('consejo', '')}")
        resumen.update(titulo=g["titulo"], veredicto=v["veredicto"], nota=v.get("total"), consejo=v.get("consejo"),
                       juicio=id_juicio)

        if a.prueba:
            paso("subidor", "es una prueba: no se sube nada")
        elif v["veredicto"] == "suspendido":
            paso("subidor", "el Juzgado lo ha suspendido: no se sube")
        else:
            paso("subidor", "pendiente: la subida automática se activa después de la prueba")
        resumen["resultado"] = "hecho"
    except Exception as e:  # el turno nunca se queda a medias sin contarlo
        resumen.update(resultado="error", error=f"{type(e).__name__}: {e}")
        paso("turno", f"ERROR {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        resumen["terminado"] = privado.ahora()
        with open(os.path.join(trabajo, "registro.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(registro) + "\n")
        json.dump(resumen, open(os.path.join(trabajo, "resumen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        for c in cuadernos.values():
            c.guardar()
        privado.guardar_estado(f"central/{clave}.json", {"canal": clave, "ultimo_turno": resumen})
        shutil.rmtree(os.path.join(trabajo, "dibujos", "tmp"), ignore_errors=True)
    return 0 if resumen.get("resultado") == "hecho" else 1


if __name__ == "__main__":
    sys.exit(main())
