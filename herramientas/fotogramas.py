"""Saca de un vídeo lo que necesita un juez para predecir si va a ser viral, sin gastar nada:
7 fotogramas en los momentos clave y datos técnicos medidos con ffmpeg.

Uso:  python fotogramas.py video.mp4 --salida carpeta/
Deja: f1.jpg … f7.jpg (segundos 0,3 · 1,2 · 2,5 y al 30 %, 55 %, 80 % y el final) y datos.json con:
duracion, cortes (cambios de plano), cortes_por_minuto, primer_corte, pantallas_negras, silencios,
volumen_inicio_db (los 2 primeros segundos) y volumen_medio_db.
"""
import argparse, json, os, re, subprocess


def ffmpeg_log(args):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + args + ["-f", "null", "-"],
                       capture_output=True, text=True)
    return r.stderr


def duracion(v):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", v],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def tiene_audio(v):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", v], capture_output=True, text=True)
    return bool(r.stdout.strip())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video")
    p.add_argument("--salida", required=True)
    p.add_argument("--ancho", type=int, default=540, help="ancho de los fotogramas (más pequeño gasta menos)")
    a = p.parse_args()
    os.makedirs(a.salida, exist_ok=True)
    d = duracion(a.video)
    momentos = [0.3, 1.2, 2.5, d * 0.30, d * 0.55, d * 0.80, max(0.0, d - 0.2)]
    fotos = []
    for n, t in enumerate(momentos, 1):
        t = min(max(0.0, t), max(0.0, d - 0.05))
        ruta = os.path.join(a.salida, f"f{n}.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", a.video, "-frames:v", "1",
                        "-vf", f"scale={a.ancho}:-2", "-q:v", "4", ruta], check=True)
        fotos.append({"archivo": os.path.basename(ruta), "segundo": round(t, 2)})

    log = ffmpeg_log(["-i", a.video, "-vf", "select='gt(scene,0.25)',showinfo", "-an"])
    cortes = [float(x) for x in re.findall(r"pts_time:([\d.]+)", log)]
    log = ffmpeg_log(["-i", a.video, "-vf", "blackdetect=d=0.3:pix_th=0.10", "-an"])
    negros = [{"desde": float(x), "hasta": float(y)} for x, y in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)]

    datos = {"duracion": round(d, 2), "cortes": len(cortes),
             "cortes_por_minuto": round(len(cortes) / d * 60, 1) if d else 0,
             "primer_corte": round(cortes[0], 2) if cortes else None,
             "pantallas_negras": negros, "fotogramas": fotos}
    if tiene_audio(a.video):
        log = ffmpeg_log(["-i", a.video, "-af", "silencedetect=n=-40dB:d=0.6", "-vn"])
        ini = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
        fin = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
        datos["silencios"] = [{"desde": round(i, 2), "hasta": round(f, 2)} for i, f in zip(ini, fin + [d] * (len(ini) - len(fin)))]
        m = re.search(r"mean_volume: (-?[\d.]+) dB", ffmpeg_log(["-t", "2", "-i", a.video, "-af", "volumedetect", "-vn"]))
        datos["volumen_inicio_db"] = float(m.group(1)) if m else None
        m = re.search(r"mean_volume: (-?[\d.]+) dB", ffmpeg_log(["-i", a.video, "-af", "volumedetect", "-vn"]))
        datos["volumen_medio_db"] = float(m.group(1)) if m else None
    else:
        datos["silencios"] = [{"desde": 0, "hasta": round(d, 2)}]
        datos["sin_audio"] = True
    with open(os.path.join(a.salida, "datos.json"), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in datos.items() if k != "fotogramas"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
