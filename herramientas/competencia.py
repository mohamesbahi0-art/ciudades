"""Espía de la competencia, gratis y sin gastar cuota de la API: qué publica un canal, cada cuánto y qué le funciona.

Uso:
  python competencia.py "https://www.youtube.com/@canal" --salida canal.json [--ultimos 15]
  python competencia.py --buscar "gta 6 curiosidades" --salida busqueda.json   (los Shorts de un tema, por visitas/hora)
Da: vídeos por semana, duración media, los mejores por visitas por hora y las palabras que más repiten en los títulos.
Solo lee datos públicos: no descarga ni vuelve a subir nada.
"""
import argparse, datetime as dt, json, re, statistics
from collections import Counter

import yt_dlp

VACIAS = set("de la el en y a los las un una que es por con del se no lo mi tu su al o más mas para como esto este esta".split())


def detalle(ydl, url):
    try:
        return ydl.extract_info(url, download=False)
    except Exception:
        return None


def visitas_hora(v):
    ts = v.get("timestamp") or (dt.datetime.strptime(v["upload_date"], "%Y%m%d").replace(tzinfo=dt.timezone.utc).timestamp()
                                if v.get("upload_date") else None)
    if not ts or not v.get("view_count"):
        return None, None
    horas = max(1.0, (dt.datetime.now(dt.timezone.utc).timestamp() - ts) / 3600)
    return round(v["view_count"] / horas, 1), ts


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("canal", nargs="?")
    p.add_argument("--buscar")
    p.add_argument("--ultimos", type=int, default=15)
    p.add_argument("--salida", required=True)
    a = p.parse_args()
    if not (a.canal or a.buscar):
        raise SystemExit("Dame un canal o --buscar «tema».")
    origen = f"ytsearch{a.ultimos}:{a.buscar} shorts" if a.buscar else a.canal.rstrip("/") + "/shorts"
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as ydl:
        lista = (ydl.extract_info(origen, download=False) or {}).get("entries") or []
    vids = []
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        for e in lista[:a.ultimos]:
            url = e.get("url") or f"https://www.youtube.com/shorts/{e.get('id')}"
            v = detalle(ydl, url)
            if not v:
                continue
            vh, ts = visitas_hora(v)
            vids.append({"titulo": v.get("title"), "url": v.get("webpage_url"), "canal": v.get("channel"),
                         "visitas": v.get("view_count"), "duracion": v.get("duration"), "visitas_por_hora": vh,
                         "publicado": dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M") if ts else None,
                         "_ts": ts})
    fechas = sorted(v["_ts"] for v in vids if v["_ts"])
    semanas = max(1 / 7, (fechas[-1] - fechas[0]) / 604800) if len(fechas) > 1 else None
    palabras = Counter(w for v in vids for w in re.findall(r"[a-záéíóúñü0-9]+", (v["titulo"] or "").lower())
                       if w not in VACIAS and len(w) > 2)
    informe = {
        "origen": a.buscar or a.canal, "analizados": len(vids),
        "videos_por_semana": round(len(fechas) / semanas, 1) if semanas else None,
        "duracion_media": round(statistics.mean([v["duracion"] for v in vids if v["duracion"]]), 1) if vids else None,
        "mejores": sorted([{k: v[k] for k in v if k != "_ts"} for v in vids if v["visitas_por_hora"]],
                          key=lambda x: -x["visitas_por_hora"])[:5],
        "palabras_en_titulos": palabras.most_common(15),
    }
    json.dump(informe, open(a.salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: informe[k] for k in ("origen", "analizados", "videos_por_semana", "duracion_media")}, ensure_ascii=False))
    for m in informe["mejores"]:
        print(f"  {m['visitas_por_hora']:>8} visitas/h · {m['titulo']}")


if __name__ == "__main__":
    main()
