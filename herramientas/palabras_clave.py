"""Palabras clave gratis: lo que la gente escribe de verdad en el buscador de YouTube.

Usa las sugerencias del buscador de YouTube (las que salen al escribir). No gasta cuota de la API ni necesita clave.

Uso:
  python palabras_clave.py "gta 6"                 → sugerencias directas
  python palabras_clave.py "gta 6" --expandir      → también «gta 6 a», «gta 6 b»… y preguntas («cómo gta 6»…)
  Opciones: --idioma es  --pais ES (o MX, AR, CO…)  --salida palabras.json
Las que más se repiten al expandir son las más buscadas.
"""
import argparse, json, string, time, urllib.parse, urllib.request
from collections import Counter

URL = "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&hl={hl}&gl={gl}&q={q}"
PREGUNTAS = ["cómo", "por qué", "cuándo", "qué", "dónde", "cuánto", "mejor", "nuevo"]


def sugerencias(consulta, hl, gl):
    url = URL.format(hl=hl, gl=gl, q=urllib.parse.quote(consulta))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        texto = r.read().decode("utf-8", "replace")
    return leer_respuesta(texto)


def leer_respuesta(texto):
    """La respuesta es ["consulta", ["sugerencia 1", ...]] (o la misma lista envuelta en una función)."""
    inicio, fin = texto.find("["), texto.rfind("]")
    datos = json.loads(texto[inicio:fin + 1])
    lista = datos[1] if len(datos) > 1 else []
    return [x if isinstance(x, str) else x[0] for x in lista]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("semilla")
    p.add_argument("--expandir", action="store_true")
    p.add_argument("--idioma", default="es")
    p.add_argument("--pais", default="ES")
    p.add_argument("--salida")
    a = p.parse_args()
    consultas = [a.semilla]
    if a.expandir:
        consultas += [f"{a.semilla} {l}" for l in string.ascii_lowercase] + [f"{q} {a.semilla}" for q in PREGUNTAS]
    cuenta = Counter()
    for q in consultas:
        try:
            for s in sugerencias(q, a.idioma, a.pais):
                cuenta[s.strip().lower()] += 1
        except Exception as e:
            print(f"(no pude consultar «{q}»: {type(e).__name__})")
        time.sleep(0.25)
    lista = [{"palabras": k, "veces": v} for k, v in cuenta.most_common()]
    if a.salida:
        json.dump(lista, open(a.salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for x in lista[:40]:
        print(f"{x['veces']:3}  {x['palabras']}")


if __name__ == "__main__":
    main()
