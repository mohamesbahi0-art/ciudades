"""La Analista de cuentas: repasa cómo van TODAS las cuentas y sus vídeos, y dice qué funciona y qué no.

- YouTube: usa lo que dejan los Jefes de canal en cada revisión (suscriptores, visitas, los últimos vídeos con sus
  visitas y me gusta) y la foto de cada revisión (estado/historial/), así que no gasta cuota.
- Instagram y TikTok: hasta que se conecten esas cuentas, no se pueden leer las cifras con programas (está bloqueado y
  no está permitido). Usa lo que el dueño marca en «Para subir» y las cifras que apunta él (estado/redes/cifras.json).
- Con Gemini escribe un informe corto y sencillo y, cuando hay pruebas suficientes, apunta lecciones para el Escritor.

Deja estado/analisis/informe.json para la app y apunta en su cuaderno (memoria/analista_cuentas.json).
Uso:  python bots/influencers/analista.py
"""
import datetime as dt
import json
import os
import statistics
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.central import huecos, parasubir  # noqa: E402
from bots.comun import gemini, privado  # noqa: E402

PLANTILLA = """Eres la Analista de cuentas de una fábrica de vídeos cortos. El dueño no sabe de técnica: háblale en español
de España, claro y sin palabras raras. Estos son los datos de hoy (JSON):
{datos}

Lo que ya sabías (tus lecciones):
{lecciones}

Escribe SOLO un JSON:
{{"titular": "una frase con lo más importante de hoy",
  "puntos": ["de 3 a 6 frases cortas: qué cuenta crece, cuál se ha parado, qué vídeo va mejor y por qué crees que funciona"],
  "consejos": ["de 1 a 3 cosas concretas que cambiar en los próximos vídeos"],
  "lecciones": [{{"texto": "lección para el Escritor, con el canal", "pruebas": "en qué datos te basas", "confianza": 0.5}}]}}
Solo pon lecciones si hay al menos 5 vídeos con más de 48 horas que las respalden; si no, deja la lista vacía.
No te inventes cifras: usa solo las de los datos."""


def _f(texto):
    return huecos.fecha(texto)


def youtube(cfg, ahora):
    salida = {}
    for clave, c in cfg.get("canales", {}).items():
        r = privado.leer(os.path.join("estado", "canales", f"{clave}.json"), {}) or {}
        if not r or r.get("error"):
            salida[clave] = {"nombre": c.get("nombre"), "sin_datos": r.get("error") or "todavía sin revisar"}
            continue
        fotos = privado.leer(os.path.join("estado", "historial", f"{clave}.json"), []) or []

        def hace(horas):
            antes = [x for x in fotos if _f(x["fecha"]) <= ahora - dt.timedelta(hours=horas)]
            return antes[-1] if antes else None
        dia, semana = hace(24), hace(24 * 7)
        recientes = r.get("recientes", [])
        maduros = [v for v in recientes if _f(v["publicado"]) <= ahora - dt.timedelta(hours=48)][:15]
        ultimos7 = [v for v in recientes if _f(v["publicado"]) > ahora - dt.timedelta(days=7)]
        mejor = max(ultimos7, key=lambda v: v["visitas"], default=None)
        salida[clave] = {
            "nombre": c.get("nombre"), "suscriptores": r.get("suscriptores"),
            "suscriptores_24h": (r.get("suscriptores") or 0) - (dia or {}).get("suscriptores", r.get("suscriptores") or 0),
            "suscriptores_7d": (r.get("suscriptores") or 0) - (semana or {}).get("suscriptores", r.get("suscriptores") or 0),
            "visitas_24h": (r.get("visitas_totales") or 0) - (dia or {}).get("visitas", r.get("visitas_totales") or 0),
            "publicados_7_dias": r.get("publicados_7_dias"), "programados": len(r.get("programados", [])),
            "hasta": r.get("hasta"),
            "media_visitas_48h": round(statistics.mean(v["visitas"] for v in maduros)) if maduros else None,
            "mediana_visitas_48h": round(statistics.median(v["visitas"] for v in maduros)) if maduros else None,
            "mejor_7_dias": {k: mejor[k] for k in ("titulo", "visitas", "megusta", "url")} if mejor else None,
            "ultimos": [{"titulo": v["titulo"], "visitas": v["visitas"], "megusta": v.get("megusta"),
                         "horas": round((ahora - _f(v["publicado"])).total_seconds() / 3600)} for v in recientes[:8]],
        }
    return salida


def redes(cfg):
    docs = parasubir.documentos()
    cifras = privado.leer(os.path.join("estado", "redes", "cifras.json"), {}) or {}
    salida = {}
    for clave, b in cfg.get("barrios", {}).items():
        mios = [d for d in docs if d.get("barrio") == clave]
        subidos = sorted((d for d in mios if d.get("estado") == "subido"), key=lambda d: d.get("subidoEl", ""))
        salida[clave] = {"nombre": b.get("nombre", clave), "estado": b.get("estado"), "redes": b.get("redes"),
                         "pendientes": sum(1 for d in mios if d.get("estado") == "pendiente"),
                         "subidos": len(subidos), "descartados": sum(1 for d in mios if d.get("estado") == "descartado"),
                         "ultimo_subido": subidos[-1].get("subidoEl") if subidos else None,
                         "cifras": cifras.get(clave) or "sin cifras: el dueño todavía no las ha apuntado"}
    return salida


def main():
    ahora = dt.datetime.now(dt.timezone.utc)
    cfg = privado.config()
    datos = {"fecha": privado.ahora(), "youtube": youtube(cfg, ahora), "instagram_tiktok": redes(cfg)}
    cuaderno = privado.cuaderno("analista_cuentas")
    informe = None
    try:
        informe = gemini.preguntar(PLANTILLA.format(datos=json.dumps(datos, ensure_ascii=False)[:30000],
                                                    lecciones=cuaderno.para_el_prompt()), temperatura=0.4)
        if isinstance(informe, list):
            informe = informe[0] if informe else None
    except gemini.SinIA as e:
        print(f"analista: sin IA hoy ({e}); dejo solo las cifras", flush=True)
    nuevas = []
    if isinstance(informe, dict):
        maduros = sum(len([v for v in c.get("ultimos", []) if v["horas"] >= 48]) for c in datos["youtube"].values())
        for l in informe.get("lecciones", [])[:3]:
            if maduros >= 5 and isinstance(l, dict) and l.get("texto"):
                conf = max(0.2, min(0.7, float(l.get("confianza", 0.5))))
                cuaderno.aprender(l["texto"], pruebas=[l.get("pruebas", "")], confianza=conf)
                nuevas.append(l["texto"])
        if nuevas:
            escritor = privado.cuaderno("escritor")
            for texto in nuevas:
                escritor.aprender(f"(de la Analista) {texto}", pruebas=["informe de la Analista"], confianza=0.4)
            escritor.guardar()
    id_informe = cuaderno.apuntar("informe", {"titular": (informe or {}).get("titular"), "lecciones": nuevas})
    cuaderno.guardar()
    privado.guardar_estado("analisis/informe.json", dict(datos, informe=informe, id=id_informe))
    print(f"analista: informe hecho ({len(datos['youtube'])} canales, {len(datos['instagram_tiktok'])} barrios, "
          f"{len(nuevas)} lecciones nuevas)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
