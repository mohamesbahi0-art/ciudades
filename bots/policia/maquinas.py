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
ESPERADO = {"fabrica.yml": 2, "revisar-canales.yml": 3, "ojeador.yml": 3, "radar.yml": 24, "estudio.yml": 24,
            "derechos.yml": 24,
            "buscar-clips.yml": 168, "latido.yml": 168}


def api(ruta):
    req = urllib.request.Request(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}{ruta}",
                                 headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                                          "Accept": "application/vnd.github+json", "User-Agent": "ciudades-bot"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    ahora = dt.datetime.now(dt.timezone.utc)
    runs = api("/actions/runs?per_page=100").get("workflow_runs", [])
    for nombre in ESPERADO:          # los que pasan poco (una vez al día o a la semana) no siempre salen entre los 100 últimos
        try:
            runs += api(f"/actions/workflows/{nombre}/runs?per_page=5").get("workflow_runs", [])
        except Exception:
            pass
    turnos, problemas, vistos = {}, [], set()
    for r in sorted(runs, key=lambda x: x.get("run_started_at") or "", reverse=True):
        if r["id"] in vistos:
            continue
        vistos.add(r["id"])
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
    simulacro = turnos.get("simulacro.yml", {}).get("ultimas", [])
    if simulacro and simulacro[0]["estado"] == "completed" and simulacro[0]["resultado"] == "failure":
        problemas.append("simulacro.yml: el último cambio del código rompe la ronda de mentira (mirar antes de la de verdad)")
    # ¿Hay más trabajo que manos? Si en 4 de las 6 últimas rondas se quedan canales sin turno, hace falta más fábrica
    # (más vídeos por ronda o turnos a la vez). Si no pasa, duplicar robots solo gastaría antes la IA gratis.
    rondas = ((privado.leer(os.path.join("estado", "fabrica.json"), {}) or {}).get("rondas") or [])[-6:]
    apretadas = [r for r in rondas if r.get("sin_sitio")]
    if len(rondas) >= 6 and len(apretadas) >= 4:
        faltan = sorted({privado.alias(k) for r in apretadas for k in r["sin_sitio"]})
        problemas.append(f"fabrica.yml: hay más trabajo que manos ({len(apretadas)} de las 6 últimas rondas dejan sin "
                         f"turno a {', '.join(faltan)}): subir videos_por_ronda o hacer turnos a la vez")
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
