"""El Inspector de imagen: mide, sin IA, los descuidos de maquetación de un vídeo del estudio antes de que los vea un juez.

Abre el mismo HTML del formato con el guion ya con tiempos (guion_estudio.json, como render.js), se para en varios
momentos de cada escena (al entrar, a la mitad y casi al final) y en los fotogramas que miran los jueces (0,3 s, 1,2 s,
2,5 s, al 30 %, 55 % y 80 % y el final), y mide lo que hay dibujado. Lo hace inspector.js con el navegador.

    from bots.estudio import inspector
    defectos = inspector.inspeccionar("carpeta/guion_estudio.json")
    # [{"escena": 3, "segundo": 4.12, "tipo": "pegados", "textos": ["tot15.303"], "detalle": "...", "momento": "corte", "veces": 1}]

Tipos: fuera_de_marco, recortado, fuera_de_recuadro, frase_sin_terminar, frase_colgando, pisados, pegados, repetido,
tapado, dibujo_fuera, letra_pequena, poco_contraste, arranque_quieto y error_al_dibujar.
Uso suelto:  python bots/estudio/inspector.py guion_estudio.json [--capturas carpeta]
"""
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


def inspeccionar(ruta_guion, capturas=None, pixeles=True):
    """Lista de defectos medidos en el vídeo de ese guion (vacía si sale limpio). `capturas`: carpeta donde dejar una
    foto de cada momento mirado. `pixeles=False` se salta el contraste y el arranque (más rápido)."""
    orden = ["node", os.path.join(AQUI, "inspector.js"), ruta_guion]
    if capturas:
        orden += ["--capturas", capturas]
    if not pixeles:
        orden.append("--sin-pixeles")
    r = subprocess.run(orden, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"el Inspector no pudo mirar el vídeo: {r.stderr.strip()[-400:]}")
    return json.loads(r.stdout)


def frases(defectos, maximo=12):
    """Los defectos en frases cortas para el guionista («escena 3 (4,1 s): …»), sin repetir."""
    salida = []
    for d in defectos:
        f = f"escena {d['escena']} ({str(d['segundo']).replace('.', ',')} s): {d['detalle']}"
        if f not in salida:
            salida.append(f)
    return salida[:maximo]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    hallados = inspeccionar(sys.argv[1], capturas=sys.argv[sys.argv.index("--capturas") + 1] if "--capturas" in sys.argv else None)
    print("\n".join(frases(hallados, 200)) or "limpio: el Inspector no ve nada raro")
    sys.exit(1 if hallados else 0)
