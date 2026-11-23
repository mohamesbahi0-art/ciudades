"""Recorta un trozo de un vídeo horizontal y lo deja en vertical para Shorts, TikTok y Reels (1080x1920),
gratis con ffmpeg. Es la parte de «cortar y encuadrar» de los recortadores de pago tipo Opus Clip.

Uso:
  python recortar.py video.mp4 --desde 83.4 --hasta 109.9 --salida clip.mp4
  Opciones: --modo difuminado (vídeo entero en el centro y el mismo vídeo borroso de fondo; no corta nada)
            --modo recorte (llena la pantalla cortando los lados; mejor si lo importante está en el centro)
            --centro 0.5 (en modo recorte, dónde está lo importante: 0 izquierda, 1 derecha)
            --subs subs.ass (quema los subtítulos de subtitulos.py)  --titulo "TEXTO" (gancho arriba los 3 primeros segundos)
Con --ajustar palabras.json (de transcribir.py) el corte se mueve a palabras enteras: no empieza ni acaba
a media palabra. Los subtítulos de un clip se hacen con subtitulos.py --desde/--hasta (los mismos segundos).
"""
import argparse, json, os, shutil, subprocess, tempfile

FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video")
    p.add_argument("--desde", type=float, required=True)
    p.add_argument("--hasta", type=float, required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--modo", choices=["difuminado", "recorte"], default="difuminado")
    p.add_argument("--centro", type=float, default=0.5)
    p.add_argument("--subs")
    p.add_argument("--titulo")
    p.add_argument("--ajustar", help="palabras.json para no cortar a media palabra")
    a = p.parse_args()
    if a.ajustar:
        palabras = json.load(open(a.ajustar, encoding="utf-8"))
        ini = [float(w.get("inicio", w.get("start"))) for w in palabras]
        fin = [float(w.get("fin", w.get("end"))) for w in palabras]
        antes = [t for t in ini if t <= a.desde + 0.15]
        a.desde = max(0.0, (max(antes) if antes else min(ini)) - 0.08)
        despues = [t for t in fin if t >= a.hasta - 0.15]
        a.hasta = (min(despues) if despues else max(fin)) + 0.12
        print(f"Corte ajustado a palabras enteras: {a.desde:.2f} → {a.hasta:.2f}")
    if a.hasta <= a.desde:
        raise SystemExit("--hasta tiene que ser mayor que --desde")
    if a.modo == "recorte":
        c = min(max(a.centro, 0.0), 1.0)
        vf = f"scale=-2:1920,crop=1080:1920:(iw-1080)*{c}:0,setsar=1"
    else:
        vf = ("split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,"
              "eq=brightness=-0.08[fondo];[b]scale=1080:-2[frente];[fondo][frente]overlay=(W-w)/2:(H-h)/2,setsar=1")
    tmp = tempfile.mkdtemp()
    try:
        if a.titulo:
            open(os.path.join(tmp, "t.txt"), "w", encoding="utf-8").write(a.titulo.upper())
            fuente = FUENTE if os.path.exists(FUENTE) else ""
            vf += (",drawtext=textfile=t.txt" + (f":fontfile={fuente}" if fuente else "") +
                   ":fontsize=78:fontcolor=white:borderw=6:bordercolor=black:x=(w-text_w)/2:y=h*0.16"
                   ":enable='lt(t,3)'")
        if a.subs:
            shutil.copy(a.subs, os.path.join(tmp, "s.ass"))
            vf += ",ass=s.ass"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a.desde:.3f}", "-to", f"{a.hasta:.3f}",
               "-i", os.path.abspath(a.video), "-filter_complex" if a.modo == "difuminado" else "-vf", vf,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", os.path.abspath(a.salida)]
        subprocess.run(cmd, cwd=tmp, check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"OK clip vertical de {a.hasta - a.desde:.1f} s: {a.salida}")


if __name__ == "__main__":
    main()
