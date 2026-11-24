"""El Archivo de casos (Policía): apunta cada fallo y cada arreglo, para que no se repita y para que el dueño lo lea.

Cada 3 horas (con la revisión de canales) junta lo que va mal en todas las ciudades:
- turnos de la fábrica que acabaron en error (estado/central/*.json, con el robot que falló);
- turnos automáticos de GitHub que no pasan o fallan (estado/maquinas.json, de la Jefa de máquinas);
- la IA gratis agotada (estado/gemini.json) y el cerebro de pago sin saldo o con la llave mala (estado/claude.json);
- redes que no dejan mirar al Ojeador desde hace más de 2 días (estado/influencers/ojeador/tendencias.json).
Un problema nuevo abre un caso; si deja de verse, el caso se cierra como «arreglado» con lo que lo arregló (el turno
siguiente salió bien, volvió el cupo…). Lo que solo puede arreglar el dueño queda «necesita_al_dueno». Todo va a
estado/casos.json; la ronda de Claude lo copia a casos/ de la app.

Uso:  python bots/policia/casos.py
"""
import datetime as dt
import glob
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import gemini, privado  # noqa: E402

ARCHIVO = "casos.json"                       # dentro de estado/
DIAS_CERRADOS = 30                           # los casos cerrados se guardan un mes
TIPOS = {
    "SinIA": "La IA gratis no contesta (sin cupo o saturada) y el turno no pudo escribir ni juzgar.",
    "TimeoutError": "Una conexión tardó demasiado y el turno se cortó.",
    "URLError": "No hubo conexión con un servicio y el turno se cortó.",
    "HttpError": "YouTube contestó con un error.",
}


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _fecha(texto):
    try:
        return dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None


def problemas():
    """Lo que va mal ahora mismo: {clave del caso: {robot, problema, detalle, dueno, se_arregla}}."""
    vistos = {}
    carpeta = privado.carpeta()
    cfg = privado.config()
    nombres = {k: c.get("nombre", k) for s in ("canales", "barrios") for k, c in (cfg.get(s) or {}).items()}
    for ruta in sorted(glob.glob(os.path.join(carpeta, "estado", "central", "*.json"))):
        d = privado.leer(os.path.relpath(ruta, carpeta), {}) or {}
        turnos = [t for t in d.get("turnos", []) if not t.get("prueba")]
        if not turnos:
            continue
        ultimo = turnos[-1]
        if ultimo.get("resultado") != "error":
            continue
        canal = d.get("canal") or ultimo.get("canal") or os.path.basename(ruta)[:-5]
        tipo = str(ultimo.get("error") or "error").split(":")[0].strip()[:40]
        error = str(ultimo.get("error") or "")
        if tipo == "SinIA" or ("faltan" in error and "dibujos" in error):
            # esperar a la IA o al servicio gratis de dibujos no es una avería del canal ni de su robot: la fábrica lo
            # reintenta sola (la app enseña la pausa) y de los dibujos caídos se ocupan los Mecánicos
            continue
        vistos[f"turno:{canal}:{tipo}"] = {
            "robot": ultimo.get("robot") or "fabrica", "canal": canal,
            "problema": f"{d.get('nombre') or nombres.get(canal) or canal}: {TIPOS.get(tipo, 'el turno falló.')}",
            "detalle": str(ultimo.get("error") or "")[:240], "dueno": False,
            "se_arregla": "El turno siguiente de ese canal salió bien."}
    for p in (privado.leer(os.path.join("estado", "maquinas.json"), {}) or {}).get("problemas", []):
        turno = str(p).split(":")[0]
        vistos[f"maquinas:{turno}"] = {"robot": "jefa_maquinas", "problema": f"Un turno automático no va bien: {p}",
                                       "detalle": str(p)[:240], "dueno": False,
                                       "se_arregla": "El turno volvió a pasar a su hora."}
    sin_cupo = set((privado.leer(os.path.join("estado", "gemini.json"), {}) or {}).get("sin_cupo") or [])
    if sin_cupo and set(gemini.BUENOS) <= sin_cupo:
        vistos["gemini:agotada"] = {"robot": "portero_gemini",
                                    "problema": "La IA gratis (Gemini) se ha gastado por hoy: hasta las 09:00 (hora de "
                                                "España) los robots que escriben y juzgan esperan.",
                                    "detalle": ", ".join(sorted(sin_cupo))[:240], "dueno": False,
                                    "se_arregla": "Volvió el cupo nuevo de la IA gratis."}
    aviso = ((privado.leer(os.path.join("estado", "claude.json"), {}) or {}).get("aviso") or "").strip()
    if aviso:
        vistos["claude:aviso"] = {"robot": "portero_gemini", "problema": f"El cerebro de pago (Claude): {aviso}.",
                                  "detalle": aviso[:240], "dueno": "llave" in aviso,
                                  "se_arregla": "Claude vuelve a contestar."}
    fuentes = (privado.leer(os.path.join("estado", "influencers", "ojeador", "tendencias.json"), {}) or {}).get("fuentes") or {}
    for fuente, f in fuentes.items():
        desde = _fecha(f.get("bloqueada_desde") or f.get("fecha"))
        if f.get("estado") == "bloqueada" and desde and (_ahora() - desde).total_seconds() > 48 * 3600:
            red = "Instagram" if fuente.startswith("instagram") else "TikTok"
            vistos[f"ojeador:{fuente}"] = {"robot": "ojeador_redes",
                                           "problema": f"{red} no deja mirar al Ojeador desde hace más de 2 días. Sigue "
                                                       "probando solo cada pocas horas; no se salta nada.",
                                           "detalle": str(f.get("motivo") or "")[:240], "dueno": False,
                                           "se_arregla": f"{red} volvió a dejar mirar."}
    return vistos


def main():
    ahora = privado.ahora()
    archivo = privado.leer(os.path.join("estado", ARCHIVO), {}) or {}
    casos = {c["clave"]: c for c in archivo.get("casos", []) if c.get("clave")}
    ahora_mal = problemas()
    abiertos, cerrados = 0, 0
    for clave, p in ahora_mal.items():
        c = casos.get(clave)
        if c and c.get("estado") != "arreglado":
            c.update(ultima=ahora, veces=int(c.get("veces", 1)) + 1, detalle=p["detalle"])
            continue
        abiertos += 1
        casos[clave] = {"clave": clave, "id": f"{ahora[:16].replace(':', '').replace('-', '')}-{clave}"
                        .replace(":", "-").replace(".", "-")[:120], "fecha": ahora, "ultima": ahora, "veces": 1,
                        "robot": p["robot"], "problema": p["problema"], "detalle": p["detalle"],
                        "estado": "necesita_al_dueno" if p["dueno"] else "abierto", "se_arregla": p["se_arregla"]}
    for clave, c in casos.items():
        if c.get("estado") != "arreglado" and clave not in ahora_mal:
            c.update(estado="arreglado", arreglo=c.pop("se_arregla", "Ya no se ve el fallo."), cerrado=ahora)
            cerrados += 1
    limite = (_ahora() - dt.timedelta(days=DIAS_CERRADOS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    lista = sorted((c for c in casos.values() if c.get("estado") != "arreglado" or (c.get("cerrado") or "") >= limite),
                   key=lambda c: c["fecha"], reverse=True)
    privado.guardar_estado(ARCHIVO, {"casos": lista, "abiertos": sum(1 for c in lista if c["estado"] != "arreglado")})
    cuaderno = privado.cuaderno("archivo_casos")
    cuaderno.apuntar("revision", {"abiertos_nuevos": abiertos, "cerrados": cerrados,
                                  "abiertos": sum(1 for c in lista if c["estado"] != "arreglado")})
    cuaderno.guardar()
    print(f"archivo de casos: {abiertos} abiertos ahora, {cerrados} cerrados, "
          f"{sum(1 for c in lista if c['estado'] != 'arreglado')} siguen abiertos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
