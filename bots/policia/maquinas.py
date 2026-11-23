"""La Jefa de máquinas: comprueba que cada turno automático de GitHub pasa a su hora y no falla.

Mira las últimas ejecuciones de cada turno del repositorio público con la API de GitHub (con la llave que GitHub da a
cada turno, solo para leer) y deja el parte en estado/maquinas.json del repositorio privado. Si un turno lleva demasiado
sin pasar o falla dos veces seguidas, lo apunta como problema para que el Comisario lo vea.

Uso:  python bots/policia/maquinas.py   (necesita GH_TOKEN y GITHUB_REPOSITORY)
"""
import datetime as dt
import json
import os
import sys
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import privado  # noqa: E402

# Cada cuántas horas debería pasar cada turno con horario (si no, algo va mal)
ESPERADO = {"fabrica.yml": 2, "revisar-canales.yml": 3}


def api(ruta):
    req = urllib.request.Request(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}{ruta}",
                                 headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                                          "Accept": "application/vnd.github+json", "User-Agent": "ciudades-bot"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    ahora = dt.datetime.now(dt.timezone.utc)
    runs = api("/actions/runs?per_page=100").get("workflow_runs", [])
    turnos, problemas = {}, []
    for r in runs:
        nombre = r["path"].split("/")[-1]
        t = turnos.setdefault(nombre, {"nombre": r["name"], "ultimas": []})
        if len(t["ultimas"]) < 5:
            t["ultimas"].append({"empezo": r["run_started_at"], "estado": r["status"], "resultado": r["conclusion"],
                                 "como": r["event"]})
    for nombre, horas in ESPERADO.items():
        t = turnos.get(nombre)
        hechas = [u for u in (t or {}).get("ultimas", []) if u["estado"] == "completed"]
        if not t or not hechas:
            problemas.append(f"{nombre}: todavía no ha pasado ninguna vez")
            continue
        ultima = dt.datetime.fromisoformat(t["ultimas"][0]["empezo"].replace("Z", "+00:00"))
        if (ahora - ultima).total_seconds() > (horas * 2 + 0.5) * 3600:
            problemas.append(f"{nombre}: lleva {round((ahora - ultima).total_seconds() / 3600, 1)} h sin pasar")
        fallidas = [u for u in hechas[:2] if u["resultado"] == "failure"]
        if len(fallidas) == 2:
            problemas.append(f"{nombre}: ha fallado las dos últimas veces")
    privado.guardar_estado("maquinas.json", {"turnos": turnos, "problemas": problemas})
    jefa = privado.cuaderno("jefa_maquinas")
    jefa.apuntar("revision", {"turnos": len(turnos), "problemas": problemas})
    jefa.guardar()
    print(f"jefa de máquinas: {len(turnos)} turnos mirados, {len(problemas)} problemas")
    for p in problemas:
        print(" -", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
