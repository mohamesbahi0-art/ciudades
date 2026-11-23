"""Desmonta un vídeo viral de YouTube (o TikTok) para aprender de él, gratis y sin gastar cuota de la API:
datos con yt-dlp (visitas, fecha, duración…), visitas por hora, subtítulos automáticos, y fotogramas y medidas
del predictor (fotogramas.py). No vuelve a subir nada: solo se analiza.

Uso:  python analizar.py URL --salida carpeta/ [--guardar-video]
Deja: meta.json (con visitas_por_hora), subtitulos.*.vtt si los hay, y la carpeta juicio/ de fotogramas.py.
Después, rellena la ficha de análisis de la skill analista-virales mirando los fotogramas y los subtítulos.
"""
import argparse, datetime as dt, glob, json, os, subprocess, sys

import yt_dlp

AQUI = os.path.dirname(os.path.abspath(__file__))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    p.add_argument("--salida", required=True)
    p.add_argument("--guardar-video", action="store_true")
    a = p.parse_args()
    os.makedirs(a.salida, exist_ok=True)
    opciones = {"quiet": True, "no_warnings": True, "format": "best[height<=480][ext=mp4]/worst[ext=mp4]/worst",
                "outtmpl": os.path.join(a.salida, "video.%(ext)s"), "writeautomaticsub": True, "writesubtitles": True,
                "subtitleslangs": ["es", "es-.*"], "subtitlesformat": "vtt"}
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(a.url, download=True)
    ts = info.get("timestamp") or (dt.datetime.strptime(info["upload_date"], "%Y%m%d").replace(
        tzinfo=dt.timezone.utc).timestamp() if info.get("upload_date") else None)
    horas = max(1.0, (dt.datetime.now(dt.timezone.utc).timestamp() - ts) / 3600) if ts else None
    meta = {k: info.get(k) for k in ("id", "title", "uploader", "channel_id", "channel_follower_count", "view_count",
                                     "like_count", "comment_count", "duration", "upload_date", "tags", "webpage_url")}
    meta["horas_publicado"] = round(horas, 1) if horas else None
    meta["visitas_por_hora"] = round(meta["view_count"] / horas, 1) if horas and meta.get("view_count") else None
    meta["descripcion"] = (info.get("description") or "")[:600]
    json.dump(meta, open(os.path.join(a.salida, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    videos = [v for v in glob.glob(os.path.join(a.salida, "video.*")) if not v.endswith(".vtt")]
    if videos:
        medidor = os.path.join(AQUI, "fotogramas.py")          # copia del de la skill predictor-viral
        subprocess.run([sys.executable, medidor, videos[0], "--salida", os.path.join(a.salida, "juicio")], check=False)
        if not a.guardar_video:
            os.remove(videos[0])
    print(f"OK {meta['title']!r}: {meta['view_count']} visitas, {meta['visitas_por_hora']} por hora → {a.salida}")


if __name__ == "__main__":
    main()
