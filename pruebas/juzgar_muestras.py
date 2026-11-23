"""El Juzgado juzga muestras ya hechas (vídeo + guion del repositorio privado), igual que en un turno de verdad.

Sirve para que el dueño vea qué opinan los jueces de una muestra antes de encender un perfil. Deja el resultado en
estado/juzgado/muestras.json y el juicio en la app (marcado como prueba). En el registro público solo salen alias.

    PRIVADO=... GEMINI_API_KEY=... python pruebas/juzgar_muestras.py peticiones/juzgar.json
"""
import json
import os
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from bots.comun import gemini, privado  # noqa: E402
from bots.juzgado import tribunal  # noqa: E402


def main(peticion):
    pet = json.load(open(peticion, encoding="utf-8"))
    base = os.environ.get("PRIVADO", "privado")
    resultados = []
    for m in pet.get("muestras", []):
        clave = privado.resolver(m["canal"])
        canal = privado.canal(clave)
        video = os.path.join(base, m["video"])
        g = json.load(open(os.path.join(base, m["guion"]), encoding="utf-8"))
        g["narracion"] = " ".join(e.get("voz") or e.get("texto", "") for e in g["escenas"])
        g["texto_pantalla"] = g["escenas"][0].get("texto", "")
        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, "voz.mp3")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vn", "-ac", "1", "-b:a", "96k", audio],
                           check=True)
            v = tribunal.juzgar(video, g, canal, privado.cuaderno("juez_guardia").para_el_prompt(),
                                os.path.join(tmp, "juicio"), audio=audio)
        v["intento"] = 1
        id_juicio = tribunal.guardar_juicio(clave, g, v, prueba=True)
        r = {"canal": privado.alias(clave), "titulo": g.get("titulo"), "veredicto": v["veredicto"], "nota": v.get("total"),
             "minimo": tribunal.minima(canal), "tribunal": v.get("tribunal"), "consejo": v.get("consejo"),
             "votos": v.get("votos"), "defensa": v.get("defensa"), "fiscalia": v.get("fiscalia"),
             "fallos_graves": v.get("fallos_graves"), "juicio": id_juicio, "fecha": privado.ahora()}
        resultados.append(r)
        print(privado.limpiar(f"== {r['canal']}: {r['veredicto']} {r['nota']}/100 (mínimo {r['minimo']}) · {r['tribunal']}"),
              flush=True)
        for x in v.get("votos") or []:
            print(privado.limpiar(f"   {x['juez']}: {x['nota']} ({x['voto']}) — {x.get('razon', '')}"), flush=True)
        print(privado.limpiar(f"   consejo: {r['consejo']}"), flush=True)
    privado.guardar_estado("juzgado/muestras.json", {"resultados": resultados})
    gemini.apuntar_portero()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
