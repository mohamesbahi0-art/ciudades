"""Música de fondo propia, hecha desde cero con ffmpeg (ondas y ruido): gratis y sin derechos de nadie.

Ambientes:
  tension  → zumbido grave que respira, latido y ruido oscuro (terror, supervivencia)
  energia  → bajo con pulso a 110 pulsaciones y chasquidos suaves (GTA, mapas, datos)
  calma    → acorde suave que sube y baja (motivación, información)
Uso:  python musica.py tension 30 salida.m4a
"""
import subprocess
import sys

AMBIENTES = {
    "tension": ("0.32*sin(2*PI*55*t)*(0.65+0.35*sin(2*PI*0.09*t))"
                "+0.18*sin(2*PI*58.3*t)*(0.5+0.5*sin(2*PI*0.05*t))"
                "+0.55*sin(2*PI*46*t)*exp(-28*mod(t,1.05))"
                "+0.35*sin(2*PI*46*t)*exp(-28*mod(t-0.28,1.05))*gte(mod(t,1.05),0.28)",
                "lowpass=f=900,aecho=0.8:0.7:120:0.25"),
    "energia": ("0.45*sin(2*PI*55*t)*exp(-7*mod(t,0.5454))"
                "+0.25*sin(2*PI*110*t)*exp(-9*mod(t-0.2727,0.5454))*gte(mod(t,0.5454),0.2727)"
                "+0.12*sin(2*PI*220*t)*(0.5+0.5*sin(2*PI*0.25*t))"
                "+0.06*(random(0)*2-1)*exp(-60*mod(t-0.2727,0.5454))*gte(mod(t,0.5454),0.2727)",
                "lowpass=f=4000,aecho=0.8:0.6:90:0.2"),
    "calma": ("0.20*sin(2*PI*261.6*t)*(0.6+0.4*sin(2*PI*0.07*t))"
              "+0.16*sin(2*PI*329.6*t)*(0.6+0.4*sin(2*PI*0.06*t+1))"
              "+0.14*sin(2*PI*392.0*t)*(0.6+0.4*sin(2*PI*0.05*t+2))"
              "+0.10*sin(2*PI*130.8*t)",
              "lowpass=f=2500,aecho=0.8:0.8:200:0.35"),
}
POR_TIPO = {"historias": "tension", "supervivencia": "tension", "noticias": "energia", "datos": "energia",
            "versus": "energia", "mapas": "energia", "clips": "energia", "motivacion": "calma", "acertijos": "calma"}


def ambiente_de(canal):
    return canal.get("musica") or POR_TIPO.get(canal.get("tipo"), "calma")


def crear(ambiente, segundos, salida):
    """Escribe la pista (con entrada y salida suaves) y devuelve su ruta, o None si el ambiente es «ninguna»."""
    if ambiente in (None, "ninguna", ""):
        return None
    expr, filtros = AMBIENTES.get(ambiente, AMBIENTES["calma"])
    seg = max(3.0, float(segundos))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"aevalsrc='{expr}':s=44100:d={seg:.2f}",
                    "-af", f"{filtros},afade=t=in:d=1.2,afade=t=out:st={max(0.0, seg - 1.5):.2f}:d=1.5,"
                           "loudnorm=I=-24:TP=-3",
                    "-ac", "2", "-c:a", "aac", "-b:a", "128k", salida], check=True)
    return salida


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    print(crear(sys.argv[1], float(sys.argv[2]), sys.argv[3]))
