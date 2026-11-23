"""Segunda parte de la prueba del Ojeador: con los vídeos de TikTok que vio el navegador, ¿se pueden leer sus datos
(visitas, me gusta, texto, duración) y bajar uno pequeño para que la IA lo «vea»? Con yt-dlp normal: sin cuenta, sin
cookies y sin disfrazarse. El detalle va al repositorio privado; en el registro público, solo sí o no.

    python pruebas/probar_redes_ytdlp.py privado/pruebas/redes
"""
import json
import os
import subprocess
import sys


def main(carpeta):
    informe = json.load(open(os.path.join(carpeta, "informe.json"), encoding="utf-8"))
    urls = [u for r in informe for u in (r.get("videos") or []) if "tiktok.com/" in u and "/video/" in u][:3]
    resultado = {"probados": len(urls), "datos": [], "descarga": None}
    if not urls:
        print("yt-dlp: el navegador no vio ningún vídeo de TikTok que probar")
    for u in urls:
        r = subprocess.run(["yt-dlp", "-j", "--skip-download", "--no-warnings", u], capture_output=True, text=True,
                           timeout=120)
        if r.returncode == 0 and r.stdout.strip():
            d = json.loads(r.stdout.splitlines()[0])
            resultado["datos"].append({k: d.get(k) for k in ("webpage_url", "title", "description", "duration",
                                                              "view_count", "like_count", "comment_count",
                                                              "repost_count", "upload_date", "uploader", "track")})
        else:
            resultado["datos"].append({"url": u, "error": (r.stderr or "")[-300:]})
    buenos = [d for d in resultado["datos"] if "error" not in d]
    print(f"yt-dlp: datos de {len(buenos)} de {len(urls)} vídeos" +
          (f" (con visitas: {'sí' if any(d.get('view_count') for d in buenos) else 'no'})" if buenos else ""))
    if buenos:
        destino = os.path.join(carpeta, "muestra.mp4")
        r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "-f", "b[height<=720]/b", "-o", destino,
                            buenos[0]["webpage_url"]], capture_output=True, text=True, timeout=180)
        ok = r.returncode == 0 and os.path.exists(destino)
        resultado["descarga"] = {"ok": ok, "mb": round(os.path.getsize(destino) / 1e6, 1) if ok else None,
                                 "error": None if ok else (r.stderr or "")[-300:]}
        print(f"yt-dlp: bajar un vídeo para que la IA lo vea: {'sí' if ok else 'no'}")
    json.dump(resultado, open(os.path.join(carpeta, "ytdlp.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "privado/pruebas/redes")
