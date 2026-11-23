"""Música de fondo propia, compuesta desde cero por el ordenador: gratis y sin derechos de nadie.

Cada ambiente es una pequeña pieza con acordes, piano, colchón de cuerdas, bajo y percusión, hecha nota a nota con
numpy y con reverberación. Si numpy no está, sale la versión sencilla de antes (ondas de ffmpeg).

Ambientes:
  inspira  → piano emotivo, cuerdas y percusión suave que entra a los pocos segundos (motivación, historias de famosos)
  calma    → piano y cuerdas, sin percusión (información, acertijos)
  energia  → arpegio con pulso a 100 pulsaciones, bajo y batería (GTA, mapas, datos, versus)
  tension  → zumbido grave, latidos y notas sueltas inquietantes (terror, supervivencia)
Uso:  python musica.py inspira 30 salida.m4a
"""
import os
import subprocess
import sys
import tempfile
import wave

SR = 44100
POR_TIPO = {"historias": "tension", "supervivencia": "tension", "noticias": "energia", "datos": "energia",
            "versus": "energia", "mapas": "energia", "clips": "energia", "motivacion": "inspira", "acertijos": "calma"}

# Piezas: pulsaciones, acordes (notas MIDI del colchón), bajo (MIDI) y qué instrumentos suenan.
PIEZAS = {
    "inspira": {"bpm": 84, "acordes": [(57, 60, 64), (57, 60, 65), (55, 60, 64), (55, 59, 62)], "bajo": [45, 41, 48, 43],
                "arpegio": "corcheas", "bateria": "suave", "entra_bateria": 2},
    "calma": {"bpm": 76, "acordes": [(57, 60, 64), (57, 60, 65), (55, 60, 64), (55, 59, 62)], "bajo": [45, 41, 48, 43],
              "arpegio": "lento", "bateria": None, "entra_bateria": 99},
    "energia": {"bpm": 100, "acordes": [(52, 55, 59), (52, 55, 60), (50, 55, 59), (50, 54, 57)], "bajo": [40, 36, 43, 38],
                "arpegio": "semicorcheas", "bateria": "fuerte", "entra_bateria": 1},
    "tension": {"bpm": 66, "acordes": [(50, 53, 57), (50, 53, 58), (49, 53, 57), (50, 53, 57)], "bajo": [38, 34, 37, 38],
                "arpegio": None, "bateria": "latido", "entra_bateria": 0},
}


def ambiente_de(canal):
    return canal.get("musica") or POR_TIPO.get(canal.get("tipo"), "calma")


def _hz(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def _componer(nombre, segundos, semilla=7):
    import numpy as np
    p = PIEZAS.get(nombre) or PIEZAS["calma"]
    rnd = np.random.RandomState(semilla)
    n = int(segundos * SR) + SR * 3
    musica = {"piano": np.zeros(n), "pad": np.zeros(n), "bajo": np.zeros(n), "bat": np.zeros(n)}
    beat = 60.0 / p["bpm"]
    compas = 4 * beat

    def poner(pista, x, t0):
        i = int(t0 * SR)
        if i >= n:
            return
        x = x[: n - i]
        musica[pista][i:i + len(x)] += x

    def tiempo(d):
        return np.arange(int(d * SR)) / SR

    def piano(f, d, vel):
        t = tiempo(d)
        y = np.zeros_like(t)
        for k, a in ((1, 1.0), (2, 0.45), (3, 0.24), (4, 0.12), (5, 0.07), (6, 0.04)):
            fk = f * k * np.sqrt(1 + 0.0004 * k * k)
            if fk < 11000:
                y += a * np.sin(2 * np.pi * fk * t + k) * np.exp(-t * (1.3 + 0.9 * k))
        y *= np.minimum(1, t / 0.004)
        y[-400:] *= np.linspace(1, 0, min(400, len(y)))
        return vel * y

    def pluck(f, d, vel):
        t = tiempo(d)
        y = np.zeros_like(t)
        for k in range(1, 9):
            y += (1 / k) * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (6 + 3 * k))
        return vel * y * np.minimum(1, t / 0.002)

    def pad(notas, d):
        t = tiempo(d)
        y = np.zeros_like(t)
        for m in notas:
            for det in (-0.0035, 0.0, 0.0035):
                f = _hz(m) * (1 + det)
                for k in range(1, 7):
                    y += (1 / k) * np.exp(-0.45 * k) * np.sin(2 * np.pi * f * k * t + 3 * k * det * 1000)
        a = min(1.2, d / 3)
        env = np.minimum(1, t / a) * np.minimum(1, (d - t) / a)
        lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.2 * t)
        return y * env * lfo / (len(notas) * 3)

    def bajo(m, d):
        t = tiempo(d)
        f = _hz(m)
        y = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)
        return y * np.minimum(1, t / 0.03) * np.minimum(1, (d - t) / 0.25)

    def bombo(fuerza=1.0):
        t = tiempo(0.5)
        f = 44 + 80 * np.exp(-t * 20)
        y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6.5)
        return fuerza * (y + 0.05 * rnd.randn(len(t)) * np.exp(-t * 300))

    def palmada(fuerza=1.0):
        t = tiempo(0.35)
        r = np.diff(rnd.randn(len(t) + 1))
        return fuerza * (0.4 * r * np.exp(-t * 26) + 0.3 * np.sin(2 * np.pi * 185 * t) * np.exp(-t * 30))

    def charles(fuerza=1.0):
        t = tiempo(0.07)
        r = np.diff(np.diff(rnd.randn(len(t) + 2)))
        return fuerza * 0.12 * r * np.exp(-t * 90)

    def inquietante(d):
        t = tiempo(d)
        f = _hz(rnd.choice([74, 75, 77, 80, 81]))
        y = np.sin(2 * np.pi * f * t + 2.5 * np.sin(2 * np.pi * 5.5 * t))
        return y * np.minimum(1, t / 0.8) * np.minimum(1, (d - t) / 0.8)

    c = 0
    while c * compas < segundos + compas:
        t0 = c * compas
        i = c % len(p["acordes"])
        acorde, raiz = p["acordes"][i], p["bajo"][i]
        poner("pad", pad(acorde, compas + 0.6), t0)
        poner("bajo", bajo(raiz, compas), t0)
        tonos = [acorde[0] + 12, acorde[1] + 12, acorde[2] + 12, acorde[0] + 24]
        if p["arpegio"] == "corcheas":
            for k, idx in enumerate((0, 1, 2, 3, 2, 1, 2, 3)):
                poner("piano", piano(_hz(tonos[idx]), 1.6, (0.55 if k % 2 else 0.75) * (0.9 + 0.2 * rnd.rand())), t0 + k * beat / 2)
        elif p["arpegio"] == "lento":
            for k, idx in enumerate((0, 2, 1, 3)):
                poner("piano", piano(_hz(tonos[idx]), 2.2, 0.7 * (0.9 + 0.2 * rnd.rand())), t0 + k * beat)
        elif p["arpegio"] == "semicorcheas":
            for k in range(16):
                poner("piano", pluck(_hz(tonos[(0, 1, 2, 1, 3, 1, 2, 1)[k % 8]]), 0.4, 0.5 if k % 4 else 0.75), t0 + k * beat / 4)
        elif nombre == "tension" and c % 2 == 1:
            poner("piano", 0.35 * inquietante(compas * 1.2), t0 + beat)
        if p["bateria"] and c >= p["entra_bateria"]:
            for b in range(4):
                tb = t0 + b * beat
                if p["bateria"] == "latido":
                    if b == 0:
                        poner("bat", bombo(0.9), tb)
                        poner("bat", bombo(0.6), tb + 0.28)
                    continue
                if b in (0, 2):
                    poner("bat", bombo(1.0 if p["bateria"] == "fuerte" else 0.75), tb)
                if b in (1, 3):
                    poner("bat", palmada(0.7 if p["bateria"] == "fuerte" else 0.4), tb)
                for h in range(2 if p["bateria"] == "suave" else 4):
                    poner("bat", charles(0.8 if p["bateria"] == "fuerte" else 0.5), tb + h * beat / (2 if p["bateria"] == "suave" else 4))
        c += 1

    def reverb(x, seg, semilla):
        r = np.random.RandomState(semilla)
        m = int(seg * SR)
        t = np.arange(m) / SR
        ir = r.randn(m) * np.exp(-t * 6.9 / seg)
        F = np.fft.rfftfreq(m, 1 / SR)
        ir = np.fft.irfft(np.fft.rfft(ir) / np.sqrt(1 + (F / 3500) ** 2), m)
        ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
        N = 1 << int(np.ceil(np.log2(len(x) + m)))
        return np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(ir, N), N)[: len(x)]

    def paso_bajo(x, fc):
        X = np.fft.rfft(x)
        F = np.fft.rfftfreq(len(x), 1 / SR)
        return np.fft.irfft(X / np.sqrt(1 + (F / fc) ** 4), len(x))

    def rms(x):
        return np.sqrt(np.mean(x ** 2)) + 1e-9

    pesos = {"piano": 0.34, "pad": 0.2, "bajo": 0.26, "bat": 0.3} if nombre != "tension" else \
            {"piano": 0.22, "pad": 0.3, "bajo": 0.3, "bat": 0.34}
    seco = {k: v / rms(v) * pesos[k] if np.any(v) else v for k, v in musica.items()}
    seco["pad"] = paso_bajo(seco["pad"], 2200)
    seco["bajo"] = paso_bajo(seco["bajo"], 400)
    # el bajo y el colchón «respiran» con el bombo, como en las producciones de verdad
    if np.any(musica["bat"]) and nombre != "tension":
        golpe = np.abs(paso_bajo(musica["bat"], 150))
        golpe = np.convolve(golpe, np.ones(2000) / 2000, mode="same")
        hueco = 1 - 0.35 * golpe / (golpe.max() + 1e-9)
        seco["bajo"] *= hueco
        seco["pad"] *= hueco
    suma = seco["piano"] + seco["pad"] + seco["bajo"] + seco["bat"]
    humedo = seco["piano"] + seco["pad"]          # la batería va seca: con eco sonaría a ruido
    izq = suma + 0.55 * reverb(humedo, 2.4, 11)
    der = suma + 0.55 * reverb(humedo, 2.4, 23)
    estereo = np.stack([izq, der], axis=1)[: int(segundos * SR)]
    estereo = np.tanh(1.2 * estereo / (np.abs(estereo).max() + 1e-9)) * 0.9
    return estereo


def _escribir_wav(ruta, estereo):
    import numpy as np
    datos = (np.clip(estereo, -1, 1) * 32767).astype("<i2")
    with wave.open(ruta, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(datos.tobytes())


ANTIGUOS = {
    "tension": ("0.32*sin(2*PI*55*t)*(0.65+0.35*sin(2*PI*0.09*t))+0.55*sin(2*PI*46*t)*exp(-28*mod(t,1.05))",
                "lowpass=f=900,aecho=0.8:0.7:120:0.25"),
    "energia": ("0.45*sin(2*PI*55*t)*exp(-7*mod(t,0.5454))+0.12*sin(2*PI*220*t)*(0.5+0.5*sin(2*PI*0.25*t))",
                "lowpass=f=4000,aecho=0.8:0.6:90:0.2"),
    "calma": ("0.20*sin(2*PI*261.6*t)*(0.6+0.4*sin(2*PI*0.07*t))+0.16*sin(2*PI*329.6*t)+0.14*sin(2*PI*392.0*t)",
              "lowpass=f=2500,aecho=0.8:0.8:200:0.35"),
}


def crear(ambiente, segundos, salida, semilla=None):
    """Escribe la pista (con entrada y salida suaves) y devuelve su ruta, o None si el ambiente es «ninguna»."""
    if ambiente in (None, "ninguna", ""):
        return None
    seg = max(3.0, float(segundos))
    fades = f"afade=t=in:d=1.0,afade=t=out:st={max(0.0, seg - 1.8):.2f}:d=1.8,loudnorm=I=-24:TP=-3"
    try:
        estereo = _componer(ambiente if ambiente in PIEZAS else "calma", seg,
                            semilla if semilla is not None else int(seg * 1000) % 97)
        with tempfile.TemporaryDirectory() as tmp:
            crudo = os.path.join(tmp, "musica.wav")
            _escribir_wav(crudo, estereo)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", crudo, "-af", fades, "-ac", "2",
                            "-c:a", "aac", "-b:a", "160k", salida], check=True)
        return salida
    except ImportError:
        expr, filtros = ANTIGUOS.get(ambiente, ANTIGUOS["calma"])
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={seg:.2f}",
                        "-af", f"{filtros},{fades}", "-ac", "2", "-c:a", "aac", "-b:a", "128k", salida], check=True)
        return salida


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    print(crear(sys.argv[1], float(sys.argv[2]), sys.argv[3]))
