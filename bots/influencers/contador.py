"""El Contador de redes: los números para los gráficos de la app (lo pidió el dueño: «gráficos de barras para ver qué
pasa en mis cuentas»).

1. Cuentas de TikTok e Instagram del dueño: lee sus cifras PÚBLICAS (seguidores, «me gusta», publicaciones y, en TikTok,
   las visitas de cada vídeo) de su página pública, como la ve cualquiera sin entrar: sin cuenta, sin contraseña y sin
   cookies. Si una red dice que no, se la deja en paz 12 horas: nunca se salta un bloqueo.
2. Canales de YouTube: con lo que ya apunta la revisión de canales (estado/historial/<canal>.json) saca las visitas de
   hoy y de la semana y el último vídeo.
3. Un resumen por día (suscriptores, visitas y seguidores, con lo nuevo de cada día) para «Cómo van subiendo».

Todo queda en el repositorio privado: estado/redes/contador.json (lo suyo) y estado/app/cifras.json (listo para que la
ronda de Claude lo copie a la app). En los registros públicos solo salen alias (barrio-1…), nunca el nombre de la cuenta.

Uso:  python bots/influencers/contador.py [--sin-redes]
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import privado  # noqa: E402

ARCHIVO = os.path.join("estado", "redes", "contador.json")
PARA_APP = os.path.join("estado", "app", "cifras.json")
NAVEGADOR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
DESCANSO_HORAS = 12           # si una red no deja mirar, no se le vuelve a preguntar en este tiempo
CADA_HORAS = 5                # las cifras de una cuenta no se leen más a menudo que esto
DIAS = 90                     # días de historia que se guardan
VIDEOS = 30                   # vídeos por cuenta que se guardan con sus visitas


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _fecha(texto):
    try:
        return dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _pagina(url):
    """El HTML de una página pública (o None si no la da)."""
    req = urllib.request.Request(url, headers={"User-Agent": NAVEGADOR, "Accept-Language": "es-ES,es;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def _numero(texto):
    """«1,234», «12.5K», «1.2M» o «3 mil» → número entero."""
    t = str(texto).strip().lower().replace("\xa0", " ")
    m = re.match(r"([\d.,]+)\s*(mill|mil|k|m)?", t)      # lo largo primero: «3 mil» no es «3 m»
    if not m:
        return None
    cifra, sufijo = m.group(1), m.group(2) or ""
    if sufijo:
        try:
            valor = float(cifra.replace(",", "."))
        except ValueError:
            return None
        return int(valor * (1_000_000 if sufijo in ("m", "mill") else 1_000))
    try:
        return int(re.sub(r"[.,]", "", cifra))
    except ValueError:
        return None


def tiktok(cuenta):
    """Las cifras públicas de un perfil de TikTok: {"seguidores", "meGusta", "publicaciones"} o None si no las enseña."""
    cuerpo = _pagina(f"https://www.tiktok.com/@{cuenta}")
    if not cuerpo:
        return None
    cifras = {}
    for campo, nombre in (("followerCount", "seguidores"), ("heartCount", "meGusta"), ("videoCount", "publicaciones")):
        m = re.search(rf'"{campo}":(\d+)', cuerpo)
        if m:
            cifras[nombre] = int(m.group(1))
    return cifras if "seguidores" in cifras else None


def videos_tiktok(cuenta):
    """Los vídeos públicos de la cuenta con sus cifras (yt-dlp, sin bajar nada). [] si no los da."""
    try:
        r = subprocess.run(["yt-dlp", "--flat-playlist", "-J", "--no-warnings", f"https://www.tiktok.com/@{cuenta}"],
                           capture_output=True, text=True, timeout=180)
        if r.returncode != 0 or not r.stdout.strip():
            return []
        entradas = json.loads(r.stdout).get("entries") or []
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return []
    salida = []
    for e in entradas:
        subido = dt.datetime.fromtimestamp(int(e["timestamp"]), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") \
            if e.get("timestamp") else None
        salida.append({"titulo": str(e.get("title") or e.get("description") or "").split("\n")[0][:100],
                       "visitas": e.get("view_count") or 0, "meGusta": e.get("like_count") or 0,
                       "comentarios": e.get("comment_count") or 0, "guardados": e.get("save_count") or 0,
                       "compartidos": e.get("repost_count") or 0, "subido": subido, "segundos": e.get("duration"),
                       "url": e.get("url")})
    return salida


def instagram(cuenta):
    """Lo que enseña la página pública de Instagram sin entrar («N seguidores, N seguidos, N publicaciones») o None."""
    cuerpo = _pagina(f"https://www.instagram.com/{cuenta}/")
    if not cuerpo:
        return None
    m = re.search(r'<meta[^>]+(?:property="og:description"|name="description")[^>]+content="([^"]+)"', cuerpo)
    if not m:
        return None
    texto = html.unescape(m.group(1))
    seg = re.search(r"([\d.,]+\s*(?:[KkMm]|mil|mill)?)\s*(?:Followers|seguidores)", texto)
    pub = re.search(r"([\d.,]+\s*(?:[KkMm]|mil|mill)?)\s*(?:Posts|publicaciones)", texto)
    if not seg:
        return None
    cifras = {"seguidores": _numero(seg.group(1))}
    if pub:
        cifras["publicaciones"] = _numero(pub.group(1))
    return cifras if cifras["seguidores"] is not None else None


def contar(paso=print):
    """Lee las cifras públicas de las cuentas encendidas y las junta con las de los días anteriores."""
    ahora = _ahora()
    iso = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")
    d = privado.leer(ARCHIVO, {}) or {}
    cuentas, fuentes, dias, videos = (d.setdefault(k, {}) for k in ("cuentas", "fuentes", "dias", "videos"))
    cfg = privado.config()
    for clave, b in (cfg.get("barrios") or {}).items():
        if b.get("estado") != "activo" or not b.get("cuenta"):
            continue
        for red, leer in (("tiktok", tiktok), ("instagram", instagram)):
            if red not in (b.get("redes") or []):
                continue
            fuente = fuentes.setdefault(red, {})
            hasta = _fecha(fuente.get("hasta"))
            if hasta and hasta > ahora:                         # la red dijo que no hace poco: se la deja en paz
                continue
            antes = (cuentas.get(clave) or {}).get(red) or {}
            leida = _fecha(antes.get("fecha"))
            if leida and (ahora - leida).total_seconds() < CADA_HORAS * 3600:
                continue
            cifras = leer(b["cuenta"])
            if not cifras:
                fuente.update(estado="no_deja", fecha=iso,
                              hasta=(ahora + dt.timedelta(hours=DESCANSO_HORAS)).strftime("%Y-%m-%dT%H:%M:%SZ"))
                paso(f"contador: {red} no enseña las cifras de {privado.alias(clave)}: se la deja en paz "
                     f"{DESCANSO_HORAS} h")
                continue
            fuente.update(estado="bien", fecha=iso, hasta=None)
            if red == "tiktok":
                lista = videos_tiktok(b["cuenta"])
                if lista:
                    cifras["visitas"] = sum(v["visitas"] for v in lista)
                    videos[clave] = sorted(lista, key=lambda v: v.get("subido") or "", reverse=True)[:VIDEOS]
            cuentas.setdefault(clave, {})[red] = dict(cifras, fecha=iso)
            dias.setdefault(iso[:10], {}).setdefault(clave, {})[red] = {k: v for k, v in cifras.items()}
            paso(f"contador: {red} de {privado.alias(clave)}: {len(cifras)} cifras leídas")
    limite = (ahora - dt.timedelta(days=DIAS)).strftime("%Y-%m-%d")
    for dia in [k for k in dias if k < limite]:
        dias.pop(dia)
    d["actualizado"] = iso
    privado.escribir(ARCHIVO, d)
    return d


def _lecturas(clave):
    """Las lecturas de un canal de YouTube ([{fecha, suscriptores, visitas, videos}], de la revisión de canales)."""
    lista = privado.leer(os.path.join("estado", "historial", f"{clave}.json"), []) or []
    return sorted((x for x in lista if isinstance(x, dict) and x.get("fecha")), key=lambda x: x["fecha"])


def _hace(lecturas, horas, ahora):
    """La lectura más cercana a hace `horas` horas (la última anterior a ese momento, o la primera que haya)."""
    limite = (ahora - dt.timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")
    antes = [x for x in lecturas if x["fecha"] <= limite]
    return antes[-1] if antes else (lecturas[0] if lecturas else None)


def para_app(contado=None):
    """Junta los números que la app dibuja: por canal, por cuenta y por día."""
    ahora = _ahora()
    contado = contado if contado is not None else (privado.leer(ARCHIVO, {}) or {})
    cfg = privado.config()
    canales, por_dia = {}, {}
    for clave in (cfg.get("canales") or {}):
        lecturas = _lecturas(clave)
        if not lecturas:
            continue
        ultima = lecturas[-1]
        ayer, semana = _hace(lecturas, 24, ahora), _hace(lecturas, 24 * 7, ahora)
        rev = privado.leer(os.path.join("estado", "canales", f"{clave}.json"), {}) or {}
        u = rev.get("ultimo_publicado") or {}
        dias_semana = round(((_fecha(ultima["fecha"]) - _fecha(semana["fecha"])).total_seconds()) / 86400, 1)
        canales[clave] = {
            "suscriptores": ultima.get("suscriptores"), "visitasTotales": ultima.get("visitas"),
            "visitas": {"hoy": max(0, (ultima.get("visitas") or 0) - (ayer.get("visitas") or 0)),
                        "semana": max(0, (ultima.get("visitas") or 0) - (semana.get("visitas") or 0)),
                        "diasMedidos": dias_semana},
            "suscriptoresNuevos": {"hoy": (ultima.get("suscriptores") or 0) - (ayer.get("suscriptores") or 0),
                                   "semana": (ultima.get("suscriptores") or 0) - (semana.get("suscriptores") or 0)},
            "ultimoVideo": {k: u.get(k) for k in ("titulo", "url", "publicado", "visitas", "megusta", "comentarios")
                            if u.get(k) is not None} or None,
            "videos": [{k: v.get(k) for k in ("titulo", "url", "publicado", "visitas", "megusta")}
                       for v in (rev.get("recientes") or [])[:12]],
            "fecha": ultima["fecha"]}
        for x in lecturas:                                   # la última lectura de cada día
            por_dia.setdefault(x["fecha"][:10], {}).setdefault("canales", {})[clave] = {
                "suscriptores": x.get("suscriptores"), "visitas": x.get("visitas")}
    barrios = {}
    for clave, redes in (contado.get("cuentas") or {}).items():
        barrios[clave] = {"cifrasPorRed": {red: dict(c, auto=True) for red, c in redes.items()},
                          "videos": (contado.get("videos") or {}).get(clave, [])[:12]}
    ultima = {}                      # la última cifra conocida de cada red de cada cuenta: se arrastra si un día falta
    for dia, cuentas in sorted((contado.get("dias") or {}).items()):
        for clave, redes in cuentas.items():
            ultima.setdefault(clave, {}).update({red: c for red, c in redes.items() if c.get("seguidores") is not None})
        for clave, redes in ultima.items():
            seguidores = sum((c.get("seguidores") or 0) for c in redes.values())
            por_dia.setdefault(dia, {}).setdefault("barrios", {})[clave] = {
                "seguidores": seguidores, "porRed": {red: c.get("seguidores") for red, c in redes.items()},
                "visitas": (redes.get("tiktok") or {}).get("visitas")}
    historial, anterior = {}, {}
    for dia in sorted(por_dia)[-DIAS:]:                       # lo nuevo de cada día, comparando con el día anterior
        hoy = {"fecha": dia, "canales": por_dia[dia].get("canales", {}), "barrios": por_dia[dia].get("barrios", {})}
        for clave, c in hoy["canales"].items():
            a = (anterior.get("canales") or {}).get(clave)
            if a:
                c["suscriptoresNuevos"] = (c.get("suscriptores") or 0) - (a.get("suscriptores") or 0)
                c["visitasNuevas"] = max(0, (c.get("visitas") or 0) - (a.get("visitas") or 0))
        for clave, b in hoy["barrios"].items():
            a = (anterior.get("barrios") or {}).get(clave)
            if a:
                b["seguidoresNuevos"] = (b.get("seguidores") or 0) - (a.get("seguidores") or 0)
                if b.get("visitas") is not None and a.get("visitas") is not None:
                    b["visitasNuevas"] = max(0, b["visitas"] - a["visitas"])
        historial[dia] = hoy
        anterior = {"canales": dict(anterior.get("canales") or {}, **hoy["canales"]),
                    "barrios": dict(anterior.get("barrios") or {}, **hoy["barrios"])}
    salida = {"canales": canales, "barrios": barrios, "historial": historial,
              "fuentes": contado.get("fuentes") or {}, "actualizado": ahora.strftime("%Y-%m-%dT%H:%M:%SZ")}
    privado.escribir(PARA_APP, salida)
    return salida


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-redes", action="store_true", help="no mira TikTok ni Instagram: solo junta lo que ya hay")
    a = p.parse_args(argv)
    limpio = lambda t: print(privado.limpiar(t), flush=True)   # noqa: E731
    contado = None
    if not a.sin_redes:
        try:
            contado = contar(paso=limpio)
        except Exception as e:
            print(f"contador: no ha podido mirar las redes ({type(e).__name__})", flush=True)
    salida = para_app(contado)
    cuaderno = privado.cuaderno("contador_redes")
    cuaderno.apuntar("cuenta", {"canales": len(salida["canales"]), "cuentas": len(salida["barrios"]),
                                "dias": len(salida["historial"])})
    cuaderno.guardar()
    print(f"contador: {len(salida['canales'])} canales, {len(salida['barrios'])} cuentas y {len(salida['historial'])} "
          "días listos para la app", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
