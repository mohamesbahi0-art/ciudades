"""Prueba de voces de ElevenLabs para las cuentas de TikTok: busca voces de hombre en español (de España primero), dice
la misma frase con 4 de ellas y deja los audios en la release «pruebas» del repositorio privado para que el dueño
elija. Gasta unos 400 créditos de ElevenLabs. Solo imprime nombres de voces y su id (nada privado).

    ELEVENLABS_API_KEY=... python pruebas/probar_eleven.py
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))

FRASE = ("Con quince años ya jugaba en el Barça. Y muchos dicen que es pura suerte. "
         "Pero casi nueve años entrenando sin que nadie mirara no son suerte.")
API = "https://api.elevenlabs.io/v1"


def pedir(ruta, cuerpo=None, metodo=None):
    req = urllib.request.Request(API + ruta, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 method=metodo or ("POST" if cuerpo is not None else "GET"),
                                 headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def main():
    if not os.environ.get("ELEVENLABS_API_KEY"):
        print("Falta el secreto ELEVENLABS_API_KEY: el dueño tiene que ponerlo en GitHub (Settings → Secrets).")
        return 0
    elegidas = []
    try:     # voces de la biblioteca pública en español, de España primero
        q = urllib.parse.urlencode({"page_size": 60, "language": "es", "gender": "male"})
        for v in pedir(f"/shared-voices?{q}").get("voices", []):
            acento = (v.get("accent") or "").lower()
            if any(k in acento for k in ("spain", "castil", "peninsular", "madrid", "european")) and len(elegidas) < 2:
                try:
                    pedir(f"/voices/add/{v['public_owner_id']}/{v['voice_id']}", {"new_name": v.get("name", "voz")[:40]})
                    elegidas.append((v["voice_id"], v.get("name"), acento))
                except urllib.error.HTTPError as e:
                    print(f"no se ha podido añadir {v.get('name')}: {e.code}")
    except urllib.error.HTTPError as e:
        print(f"biblioteca pública: {e.code}")
    for v in pedir("/voices").get("voices", []):      # y las de serie que mejor narran
        if len(elegidas) >= 4:
            break
        if v.get("category") == "premade" and (v.get("labels") or {}).get("gender") == "male" and \
                any(k in json.dumps(v.get("labels"), ensure_ascii=False).lower() for k in ("narrat", "deep", "story", "social")):
            elegidas.append((v["voice_id"], v.get("name"), (v.get("labels") or {}).get("accent", "")))
    import asyncio
    import voz
    from bots.comun import almacen
    with tempfile.TemporaryDirectory() as tmp:
        for n, (vid, nombre, acento) in enumerate(elegidas, 1):
            d = os.path.join(tmp, str(n))
            asyncio.run(voz.generar(FRASE, f"eleven:{vid}", "-4%", "+0Hz", d))
            if voz.MOTOR.get("motor") != "elevenlabs":
                print(f"{n}. {nombre}: falló ({voz.MOTOR.get('aviso')})")
                continue
            archivo = f"voz-eleven-{n}-{''.join(c for c in (nombre or 'voz').lower() if c.isalnum())[:20]}.mp3"
            os.replace(os.path.join(d, "voz.mp3"), os.path.join(tmp, archivo))
            if os.environ.get("GH_SECRETOS"):
                almacen.guardar("pruebas", os.path.join(tmp, archivo), archivo)
            print(f"{n}. {nombre} ({acento or 'acento sin indicar'}) · id {vid} · {archivo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
