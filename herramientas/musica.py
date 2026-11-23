"""Música de fondo propia, compuesta desde cero por el ordenador: gratis y sin derechos de nadie.

Primero busca música de verdad de dominio público (la Discoteca, bots/central/discoteca.py, la deja en la carpeta
MUSICA_DIR con su biblioteca.json): elige una de las mejores de ese ambiente y corta un trozo. Si no hay, compone una
pieza nota a nota con numpy (acordes, piano, colchón, bajo y percusión). Si tampoco hay numpy, la versión sencilla de
antes (ondas de ffmpeg).

Ambientes:
  inspira  → piano emotivo, cuerdas y percusión suave que entra a los pocos segundos (motivación, historias de famosos)
  calma    → piano y cuerdas, sin percusión (información, acertijos)
  energia  → arpegio con pulso a 100 pulsaciones, bajo y batería (GTA, mapas, datos, versus)
  tension  → zumbido grave, latidos y notas sueltas inquietantes (terror, supervivencia)
Uso:  python musica.py inspira 30 salida.m4a
"""
import json
import os
import random
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


MELODIAS = {   # motivo de 4 compases (notas MIDI y duración en pulsos; None = silencio), encima de los acordes
    "inspira": [(76, 1), (74, 1), (72, 1), (71, 1), (72, 2), (69, 2), (72, 1), (74, 1), (76, 1), (79, 1), (74, 4)],
    "calma": [(76, 2), (72, 2), (72, 2), (69, 2), (72, 2), (76, 2), (74, 4)],
    "energia": [(71, 0.5), (74, 0.5), (76, 1), (74, 0.5), (71, 0.5), (72, 2), (None, 1), (71, 0.5), (74, 0.5), (79, 1),
                (78, 1), (74, 2), (None, 2)],
    "tension": [(None, 4), (77, 3), (None, 1), (None, 4), (76, 2), (75, 2)],
}


def _componer(nombre, segundos, semilla=7):
    """Compone la pieza nota a nota: entrada suave, desarrollo y subida final, con dinámica y pequeñas imperfecciones
    humanas (cada nota con su fuerza y su tiempo), y la deja con hueco para la voz."""
    import numpy as np
    p = PIEZAS.get(nombre) or PIEZAS["calma"]
    rnd = np.random.RandomState(semilla)
    n = int(segundos * SR) + SR * 3
    pistas = {k: np.zeros(n) for k in ("piano", "melodia", "pad", "bajo", "bat")}
    beat = 60.0 / p["bpm"]
    compas = 4 * beat

    def seccion(t0):            # 0 = entrada, 1 = desarrollo, 2 = subida
        f = t0 / max(segundos, 1)
        return 0 if f < 0.2 else (1 if f < 0.52 else 2)

    def poner(pista, x, t0):
        i = int(max(0.0, t0 + rnd.uniform(-0.007, 0.007)) * SR)
        if i < n:
            x = x[: n - i]
            pistas[pista][i:i + len(x)] += x

    def tiempo(d):
        return np.arange(int(d * SR)) / SR

    def piano(f, d, vel):
        t = tiempo(d)
        y = np.zeros_like(t)
        for k, a in ((1, 1.0), (2, 0.36), (3, 0.16), (4, 0.07), (5, 0.03)):
            for det in (-0.0004, 0.0004):        # dos cuerdas un pelín desafinadas: calidez
                y += a * np.sin(2 * np.pi * f * k * (1 + det) * t + k) * np.exp(-t * (1.0 + 0.75 * k))
        y *= np.minimum(1, t / 0.006) * 0.5
        y[-600:] *= np.linspace(1, 0, min(600, len(y)))
        return vel * y

    def teclas(f, d, vel):      # piano eléctrico suave (FM): la melodía
        t = tiempo(d)
        mod = 0.9 * np.exp(-t * 2.5) * np.sin(2 * np.pi * f * t)
        y = np.sin(2 * np.pi * f * t + mod) * np.exp(-t * 1.3) + 0.2 * np.sin(4 * np.pi * f * t) * np.exp(-t * 3)
        y *= np.minimum(1, t / 0.01) * np.minimum(1, (d - t) / 0.08).clip(0)
        return vel * y

    def pluck(f, d, vel):
        t = tiempo(d)
        y = sum((1 / k) * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (7 + 4 * k)) for k in range(1, 6))
        return vel * y * np.minimum(1, t / 0.003)

    def pad(notas, d):
        t = tiempo(d)
        y = np.zeros_like(t)
        for m in notas:
            for det in (-0.003, 0.0, 0.003):
                f = _hz(m) * (1 + det)
                for k in range(1, 5):
                    y += (1 / k) * np.exp(-0.6 * k) * np.sin(2 * np.pi * f * k * t + 7 * k * det * 1000)
        a = min(1.4, d / 3)
        return y * np.minimum(1, t / a) * np.minimum(1, (d - t) / a).clip(0) / (len(notas) * 3)

    def bajo(m, d, pulso=None):
        t = tiempo(d)
        f = _hz(m)
        y = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.15 * np.sin(6 * np.pi * f * t)
        env = np.minimum(1, t / 0.02) * np.minimum(1, (d - t) / 0.2).clip(0)
        if pulso:
            env *= 0.55 + 0.45 * np.exp(-(t % pulso) * 5)
        return y * env

    def bombo(fuerza=1.0):
        t = tiempo(0.5)
        f = 42 + 70 * np.exp(-t * 22)
        return fuerza * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)

    def palmada(fuerza=1.0):
        t = tiempo(0.25)
        r = np.diff(rnd.randn(len(t) + 1))
        return fuerza * (0.32 * r * np.exp(-t * 30) + 0.3 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 32))

    def charles(fuerza=1.0):
        t = tiempo(0.05)
        r = np.diff(np.diff(rnd.randn(len(t) + 2)))
        return fuerza * 0.08 * r * np.exp(-t * 110)

    def tic(fuerza=1.0):
        t = tiempo(0.04)
        return fuerza * 0.4 * np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 160)

    c = 0
    while c * compas < segundos + compas:
        t0 = c * compas
        sec = seccion(t0)
        i = c % len(p["acordes"])
        acorde, raiz = p["acordes"][i], p["bajo"][i]
        tonos = [acorde[0], acorde[1], acorde[2], acorde[0] + 12]
        if nombre == "tension":
            poner("pad", pad((raiz + 12, raiz + 19), compas + 0.8), t0)
            if sec >= 1:
                poner("bat", bombo(0.9), t0)
                poner("bat", bombo(0.55), t0 + 0.3)
            if sec == 2:
                for b in range(4):
                    poner("bat", tic(0.6), t0 + b * beat)
                if c % 2 == 0:
                    poner("piano", piano(_hz(raiz + 24 + rnd.choice([1, 6, 11])), 3.0, 0.5), t0 + 1.5 * beat)
        else:
            poner("pad", pad(acorde, compas + 0.7), t0)
            if sec >= 1 or nombre == "energia":
                poner("bajo", bajo(raiz, compas, pulso=beat / 2 if nombre == "energia" else None), t0)
            if p["arpegio"] == "corcheas":
                for k, idx in enumerate((0, 1, 2, 3, 2, 1, 2, 3)):
                    vel = (0.8 if k % 4 == 0 else 0.55 if k % 2 else 0.65) * rnd.uniform(0.82, 1.0) * (0.75 + 0.15 * sec)
                    poner("piano", piano(_hz(tonos[idx] + 12), 1.8, vel), t0 + k * beat / 2)
            elif p["arpegio"] == "lento":
                for k, idx in enumerate((0, 2, 1, 3)):
                    poner("piano", piano(_hz(tonos[idx] + 12), 2.6, 0.7 * rnd.uniform(0.8, 1.0)), t0 + k * beat)
            elif p["arpegio"] == "semicorcheas":
                for k in range(16):
                    vel = (0.75 if k % 4 == 0 else 0.45) * rnd.uniform(0.8, 1.0)
                    poner("piano", pluck(_hz(tonos[(0, 1, 2, 1, 3, 1, 2, 1)[k % 8]] + 12), 0.35, vel), t0 + k * beat / 4)
            bateria = p["bateria"] and (sec >= 1 or nombre == "energia")
            if bateria:
                for b in range(4):
                    tb = t0 + b * beat
                    if b == 0 or (b == 2 and (sec == 2 or p["bateria"] == "fuerte")):
                        poner("bat", bombo(0.9 if p["bateria"] == "fuerte" else 0.7), tb)
                    if b in (1, 3) and (sec == 2 or p["bateria"] == "fuerte"):
                        poner("bat", palmada(0.55 if p["bateria"] == "fuerte" else 0.35), tb)
                    if sec == 2 or p["bateria"] == "fuerte":
                        for h in range(2):
                            poner("bat", charles(0.9 if h == 0 else 0.6), tb + h * beat / 2)
        if sec == 2 and (c % 4) == 0:       # la melodía entra en la subida, 4 compases cada vez
            tm = t0
            for nota, dur in MELODIAS.get(nombre, []):
                if nota:
                    hacer = teclas if nombre != "energia" else pluck
                    poner("melodia", hacer(_hz(nota), dur * beat + 0.6, 0.7 * rnd.uniform(0.85, 1.0)), tm)
                tm += dur * beat
        c += 1

    def filtro(x, bajo=None, alto=None):
        X = np.fft.rfft(x)
        F = np.fft.rfftfreq(len(x), 1 / SR)
        if alto:
            X /= np.sqrt(1 + (F / alto) ** 4)
        if bajo:
            X *= 1 / np.sqrt(1 + (bajo / (F + 1e-3)) ** 4)
        return np.fft.irfft(X, len(x))

    def reverb(x, seg, semilla, predelay=0.025):
        r = np.random.RandomState(semilla)
        m = int(seg * SR)
        t = np.arange(m) / SR
        ir = r.randn(m) * np.exp(-t * 6.9 / seg)
        ir = filtro(ir, alto=3000)
        ir[: int(predelay * SR)] = 0
        ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
        N = 1 << int(np.ceil(np.log2(len(x) + m)))
        return np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(ir, N), N)[: len(x)]

    def rms(x):
        return np.sqrt(np.mean(x ** 2)) + 1e-9

    pesos = {"piano": 0.3, "melodia": 0.22, "pad": 0.2, "bajo": 0.3, "bat": 0.26}
    if nombre == "tension":
        pesos.update(pad=0.34, piano=0.16, bat=0.3)
    if nombre == "energia":
        pesos.update(bajo=0.36, bat=0.32)
    pistas["piano"] = filtro(pistas["piano"], alto=3200)
    pistas["melodia"] = filtro(pistas["melodia"], alto=4000)
    pistas["pad"] = filtro(pistas["pad"], alto=1900)
    pistas["bajo"] = filtro(pistas["bajo"], alto=420)
    pistas["bat"] = filtro(pistas["bat"], alto=9000)
    seco = {k: (v / rms(v) * pesos[k] if np.any(v) else v) for k, v in pistas.items()}
    if np.any(pistas["bat"]) and nombre != "tension":        # bajo y colchón «respiran» con el bombo
        golpe = np.convolve(np.abs(filtro(pistas["bat"], alto=150)), np.ones(2000) / 2000, mode="same")
        hueco = 1 - 0.3 * golpe / (golpe.max() + 1e-9)
        seco["bajo"] *= hueco
        seco["pad"] *= hueco
    envio = 0.35 * seco["piano"] + 0.45 * seco["melodia"] + 0.25 * seco["pad"]
    suma = sum(seco.values())
    estereo = np.stack([suma + 0.6 * reverb(envio, 2.2, 11), suma + 0.6 * reverb(envio, 2.2, 23)], axis=1)
    # hueco para la voz (2-4 kHz un poco más bajos), sin agudos que piquen ni graves que retumben
    for k in range(2):
        x = estereo[:, k]
        X = np.fft.rfft(x)
        F = np.fft.rfftfreq(len(x), 1 / SR)
        g = 1 - 0.3 * np.exp(-((np.log(F + 1) - np.log(2900)) ** 2) / 0.12)
        g *= 1 / np.sqrt(1 + (F / 7500) ** 2)
        g *= 1 / np.sqrt(1 + (38 / (F + 1e-3)) ** 4)
        estereo[:, k] = np.fft.irfft(X * g, len(x))
    # dinámica: la entrada más suave, el desarrollo medio y la subida entera
    t = np.arange(len(estereo)) / SR
    curva = np.interp(t, [0, 0.18 * segundos, 0.24 * segundos, 0.5 * segundos, 0.56 * segundos, segundos + 3],
                      [0.62, 0.66, 0.82, 0.86, 1.0, 1.0])
    estereo *= curva[:, None]
    estereo = estereo[: int(segundos * SR)]
    estereo /= np.abs(estereo).max() + 1e-9
    return np.tanh(1.3 * estereo) / np.tanh(1.3) * 0.9


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


def _biblioteca(ambiente):
    """Las piezas de dominio público de ese ambiente que hay en MUSICA_DIR, las mejor puntuadas primero."""
    carpeta = os.environ.get("MUSICA_DIR")
    if not carpeta:
        return []
    try:
        with open(os.path.join(carpeta, "biblioteca.json"), encoding="utf-8") as f:
            pistas = json.load(f).get("pistas", [])
    except (OSError, ValueError):
        return []
    buenas = [p for p in pistas if ambiente in (p.get("ambientes") or [p.get("ambiente")])
              and os.path.exists(os.path.join(carpeta, p.get("nombre", "")))]
    return sorted(buenas, key=lambda p: -(p.get("nota") or 0))


def _de_biblioteca(pistas, seg, salida, fades, semilla):
    azar = random.Random(semilla)
    p = azar.choice(pistas[:6])
    ruta = os.path.join(os.environ["MUSICA_DIR"], p["nombre"])
    dur = float(p.get("segundos") or 0)
    if dur >= seg + 4:
        inicio = min(azar.choice([0.0, 0.0, dur * 0.2, dur * 0.4]), max(0.0, dur - seg - 2))
        entrada = ["-ss", f"{inicio:.2f}", "-t", f"{seg:.2f}", "-i", ruta]
    else:
        entrada = ["-stream_loop", "-1", "-t", f"{seg:.2f}", "-i", ruta]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entrada, "-af", fades, "-ac", "2", "-c:a", "aac",
                    "-b:a", "160k", salida], check=True)
    with open(salida + ".json", "w", encoding="utf-8") as f:    # qué pieza ha sonado (por si alguien pregunta)
        json.dump({"titulo": p.get("titulo"), "fuente": p.get("fuente"), "licencia": "CC0 (dominio público)"}, f,
                  ensure_ascii=False)
    return salida


def crear(ambiente, segundos, salida, semilla=None, libre=True):
    """Escribe la pista (con entrada y salida suaves) y devuelve su ruta, o None si el ambiente es «ninguna»."""
    if ambiente in (None, "ninguna", ""):
        return None
    seg = max(3.0, float(segundos))
    fades = f"afade=t=in:d=1.0,afade=t=out:st={max(0.0, seg - 1.8):.2f}:d=1.8,loudnorm=I=-24:TP=-3"
    pistas = _biblioteca(ambiente) if libre else []
    if pistas:
        try:
            return _de_biblioteca(pistas, seg, salida, fades, semilla)
        except (subprocess.CalledProcessError, OSError):
            pass                                  # si la pieza falla, se compone una
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
