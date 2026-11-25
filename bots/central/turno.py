"""Turno de un canal (o de un barrio de TikTok/Instagram) en la Ciudad Central.

El Reportero trae fuentes si el canal las necesita, el Escritor escribe, el Locutor pone la voz, el Dibujante dibuja, el
Montador monta y el Juez de guardia juzga. Después:
- canal de YouTube: el Subidor lo programa en su hueco (o lo deja en la cola si hoy no hay cupo);
- barrio: se deja en la bandeja «Para subir» con su texto para que lo suba el dueño.
Cada robot apunta en su cuaderno lo que ha hecho, y el estado queda en el repositorio privado para la app.

En los registros de GitHub (que son públicos) solo sale la clave del canal y el paso; títulos y nombres van solo al
repositorio privado.

Uso:  python bots/central/turno.py --canal terror [--hora 2026-12-01T20:00:00Z] [--prueba] [--salida carpeta]
      python bots/central/turno.py --peticion peticiones/prueba.json --prueba --salida privado/pruebas
"""
import argparse
import asyncio
import datetime as dt
import inspect
import json
import os
import shutil
import sys
import traceback

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from bots.central import clips, dibujante, escritor, fotografo, huecos, montador, parasubir, reportero, subidor, videoteca  # noqa: E402
from bots.comun import ia, privado  # noqa: E402
from bots.juzgado import juez_guardia, jurado, sala_ideas, tribunal  # noqa: E402
from bots.coliseo import coliseo  # noqa: E402
from bots.central import obras  # noqa: E402
from bots.estudio import estudio as estudio_animacion  # noqa: E402
import voz as locutor  # noqa: E402  (herramientas/voz.py)

ROBOTS = ("reportero_gta6", "escritor", "locutor", "dibujante", "montador", "juez_guardia", "subidor", "publicador")
# Cada canal tiene su especialista: el mismo motor, pero con su propio cuaderno (memoria) y su puesto en la app.
REPORTERO = {"gta": "reportero_gta6", "curios": "cazador_datos", "versus": "comparador"}
EN_BARRIO = {"escritor": "guionista", "montador": "editor_video"}       # en TikTok/Instagram trabajan el guionista y el editor
EN_MAPAS = {"dibujante": "dibujante_mapas", "escritor": "archivero_mapas"}


def puestos(clave, canal):
    """Qué robot hace cada paso en este canal o barrio (para su cuaderno y para la app)."""
    nombres = {r: r for r in ROBOTS}
    nombres["reportero_gta6"] = REPORTERO.get(clave, "cazador_datos" if canal["destino"] == "parasubir" else "reportero_gta6")
    if canal["destino"] == "parasubir":
        nombres.update(EN_BARRIO)
    if clave == "mapas":
        nombres.update(EN_MAPAS)
    return nombres
CON_FUENTES = ("noticias", "datos", "versus")


class _Hecho(Exception):
    """El turno ya está terminado (lo ha hecho el estudio de animación)."""


def _sin_juez(v, a, paso):
    """Si no ha habido quien juzgue (la IA no contesta), el turno espera: ni segundo intento, ni suspenso, ni se tira."""
    if v.get("veredicto") == "sin_juicio" and not a.prueba:
        paso("juez_guardia", "no hay juez ahora (la IA no contesta): el vídeo no se puede juzgar; espera a la siguiente ronda")
        raise ia.SinIA("no hay juez ahora: el vídeo se queda sin juzgar y espera a la siguiente ronda")


def _voz_de_pago(g, canal):
    """Apunta con qué voz ha salido el vídeo y, si es la de ElevenLabs en su plan gratis, la nombra en los textos (lo
    pide ese plan). Igual que hace el estudio de animación."""
    g["voz_motor"] = locutor.MOTOR.get("motor", "edge")
    if g["voz_motor"] == "elevenlabs" and canal.get("eleven_gratis", True):
        for campo in ("texto_tiktok", "texto_instagram", "descripcion"):
            if g.get(campo) and "elevenlabs.io" not in g[campo]:
                g[campo] = f"{g[campo].rstrip()}\n🎙️ Voz: elevenlabs.io"


def _ideas_con_fotos(propuestas, paso):
    """De las ideas de una cuenta de biografías, solo las de personas con fotos libres bastantes (se mira ANTES de
    gastar guion y voz). Devuelve (ideas que valen, personas sin fotos)."""
    valen, sin = [], []
    for idea in propuestas:
        persona = str(idea.get("persona") or "").strip()
        if persona and fotografo.hay_fotos(persona) >= fotografo.MIN_DISTINTAS:
            valen.append(idea)
        else:
            sin.append(persona or "?")
    paso("dibujante", f"fotos libres: {len(valen)} de {len(propuestas)} ideas tienen bastantes")
    return valen, sin


def de_fuera(error):
    """Fallos que no son del código: la IA sin cupo o saturada, o el servicio gratis de dibujos caído."""
    e = str(error or "")
    return e.startswith("SinIA") or ("faltan" in e and "dibujos" in e)


def _jurado_guion(clave, canal, g, paso, a, reescribir, alegatos=None, veces=2):
    """El Jurado popular lee el guion ANTES de gastar en voz, dibujos y montaje (lo barato filtra primero). Si lo
    rechaza (9 de 12 o más), el Escritor lo reescribe con lo que han dicho, hasta `veces` veces. Devuelve (guion, vale):
    vale=False si sigue sin convencerles (ese guion no se graba). Sin jurado hoy (tope o sin IA), el guion sigue."""
    donde = "YouTube Shorts" if canal.get("destino", "youtube") == "youtube" else "TikTok e Instagram"
    idioma = {"es": "español", "nl": "neerlandés", "en": "inglés"}.get((canal.get("idioma") or "es")[:2], "español")
    turno_id = f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')}-{privado.alias(clave)}"   # junta los intentos
    for vez in range(veces + 1):
        primera = (g.get("escenas") or [{}])[0]
        gancho = g.get("texto_pantalla") or (primera.get("texto") if isinstance(primera, dict) else str(primera)) or ""
        try:
            v = jurado.deliberar(g, canal, alegatos or {}, {"donde": donde, "idioma": idioma, "gancho": gancho,
                                                            "prueba": a.prueba, "turno": turno_id, "intento": vez + 1})
        except Exception as e:
            paso("jurado_popular", f"hoy no se ha podido reunir ({type(e).__name__}): el guion sigue")
            return g, True
        if not v:
            paso("jurado_popular", "hoy no se reúne (tope del día o sin IA): el guion sigue")
            return g, True
        g["jurado"] = v
        paso("jurado_popular", f"{v['inocente']} inocente y {v['culpable']} culpable"
             + (": lo rechaza" if v["rechaza"] else ": el guion sigue"))
        if not v["rechaza"]:
            return g, True
        if vez == veces:
            return g, False
        razones = "; ".join(x["porque"] for x in v["votos"] if x["voto"] == "culpable")[:500]
        paso("escritor", "el jurado popular lo ha rechazado: lo reescribe con lo que han dicho")
        anterior = v
        g = reescribir(f"\n- (El jurado popular ha rechazado el guion anterior, «{g.get('titulo', '')}», con "
                       f"{v['culpable']} votos en contra: {razones}. Escribe otro distinto que lo corrija.)")
        g.setdefault("jurado_anterior", anterior)
    return g, True


def _alegatos_idea(id_idea):
    """Los alegatos de la Sala de Ideas sobre la idea elegida (para que el jurado los lea)."""
    if not id_idea:
        return {}
    j = privado.leer(os.path.join("estado", "juzgado", "juicios", f"{id_idea}.json"), {}) or {}
    return {"defensa": j.get("defensa", ""), "fiscalia": j.get("fiscalia", "")}


def _coliseo(clave, canal, g, v, paso, a, resumen):
    """El vídeo aprobado (90 o más) pasa por el Coliseo: 8 gladiadores pelean por su título, texto y hashtags.
    Si algo falla, sale con su salida de siempre: el Coliseo nunca para un vídeo aprobado."""
    if v.get("veredicto") != "aprobado":
        return g
    try:
        nuevo = coliseo.luchar(clave, canal, g, v, paso=paso, prueba=a.prueba)
    except Exception as e:
        paso("coliseo", f"no ha podido hacer el torneo ({type(e).__name__}): sale con su salida de siempre")
        return g
    if nuevo.get("coliseo"):
        resumen.update(coliseo=nuevo["coliseo"], titulo=nuevo.get("titulo"))
    return nuevo


def _destino(clave, canal, video, g, v, segundos, id_guion, cuadernos, ajustes, paso, a, resumen):
    """Lo que pasa con un vídeo ya juzgado: prueba, suspendido, bandeja «Para subir» o subida a YouTube (o la cola)."""
    if a.prueba:
        paso("subidor", "es una prueba: no se sube nada")
        resumen["destino_resultado"] = "prueba"
        if os.environ.get("ALMACEN_PRUEBAS"):   # el vídeo de prueba va a la estantería «pruebas», no al historial
            resumen["video_prueba"] = parasubir.almacen.guardar("pruebas", video)
    elif v["veredicto"] != "aprobado":
        paso("subidor", f"no llega a la nota que pide el dueño ({v.get('total', '-')}/100): no se sube")
        resumen["destino_resultado"] = "suspendido"
    elif canal["destino"] == "parasubir":
        ids = parasubir.dejar(clave, canal, video, g, segundos, v)
        cuadernos["publicador"].apuntar("para_subir", {"barrio": clave, "documentos": ids, "guion": id_guion})
        privado.apuntar_titulo(clave, g["titulo"])
        paso("publicador", f"en la bandeja «Para subir»: {', '.join(ids)}", f"en la bandeja ({len(ids)} redes)")
        resumen.update(destino_resultado="para_subir", documentos=ids)
    else:
        hora = huecos.fecha(a.hora) if a.hora else None
        if not hora:
            registro_subidas = privado.leer(subidor.REGISTRO, []) or []
            revision = privado.leer(os.path.join("estado", "canales", f"{clave}.json"), {})
            cola = subidor.en_cola()
            hora = huecos.siguiente(canal["horas"], huecos.ocupados(revision, registro_subidas, cola, clave),
                                    dias_maximos=ajustes["dias_maximos"])
        if hora and subidor.hay_cupo(ajustes):
            r = subidor.subir(clave, canal, video, g, hora)
            paso("subidor", f"{r['resultado']}: {r['mensaje']}", f"{r['resultado']} (código {r['codigo']})")
            resumen.update(destino_resultado=r["resultado"], hora=r.get("hora"), url=r.get("url"))
            cuadernos["subidor"].apuntar("subida", {"canal": clave, "guion": id_guion, "codigo": r["codigo"],
                                                    "hora": r.get("hora"), "video": r.get("id")})
            if r["resultado"] != "subido":
                nombre = subidor.encolar(clave, video, g, r["mensaje"], v)
                paso("subidor", f"guardado en la cola: {nombre}", "guardado en la cola")
                resumen.update(destino_resultado="en_cola", motivo=r["mensaje"], codigo=r["codigo"])
        else:
            motivo = "no hay hueco en los próximos días" if not hora else "hoy no queda cupo de subidas"
            nombre = subidor.encolar(clave, video, g, motivo, v)
            paso("subidor", f"{motivo}: guardado en la cola ({nombre})", f"{motivo}: guardado en la cola")
            resumen.update(destino_resultado="en_cola", motivo=motivo)


def _toca_hipnotico(clave, canal):
    """El Animador hipnótico hace uno de cada `hipnotico_cada` vídeos del canal (prueba: el Cerebro dirá si funciona)."""
    cada = int(canal.get("hipnotico_cada") or 0)
    if cada < 2:
        return cada == 1
    anteriores = ((privado.leer(os.path.join("estado", "central", f"{clave}.json"), {}) or {}).get("turnos") or [])
    hechos = [t for t in anteriores if t.get("resultado") == "hecho"][-(cada - 1):]
    return len(hechos) >= cada - 1 and not any(t.get("formato") == "hipnotico" for t in hechos)


def _canal_hipnotico(canal):
    """El canal, con lo que necesita el estudio para el formato hipnótico (su voz y su música de siempre)."""
    return dict(canal, formato_estudio="hipnotico", voz_estudio=canal.get("voz_estudio") or canal.get("voz", "es-MX-JorgeNeural"),
                velocidad_estudio=canal.get("velocidad_estudio") or canal.get("velocidad", "+10%"),
                tono_estudio=canal.get("tono_estudio", "+0Hz"),
                musica_estudio=canal.get("musica_estudio") or montador.musica.ambiente_de(canal))


ARREGLOS = os.path.join("estado", "arreglos")      # el vídeo de cada cuenta que espera su versión corregida
NOTA_PARA_ARREGLAR = 72       # desde esta nota, un vídeo suspendido se rehace corrigiendo sus fallos (no se tira)
VERSIONES = 3                 # el vídeo y hasta 2 versiones corregidas; si ni así llega, tema nuevo
CADUCA_ARREGLO = 20           # horas que un arreglo pendiente espera su turno


def _ruta_arreglo(clave):
    return os.path.join(ARREGLOS, f"{privado.alias(clave)}.json")


def arreglo_pendiente(clave):
    """El vídeo de esta cuenta que se quedó cerca de la nota en el turno anterior y espera su versión corregida
    (None si no hay o si ya es viejo). Lo usa también la fábrica al planear: los arreglos van antes que lo nuevo."""
    d = privado.leer(_ruta_arreglo(clave), {}) or {}
    if not d.get("guion") or d.get("clave") not in (None, clave):     # el alias puede pasar a otra cuenta: se comprueba
        return None
    try:
        hecho = dt.datetime.strptime(d.get("fecha", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None
    if (dt.datetime.now(dt.timezone.utc) - hecho).total_seconds() > CADUCA_ARREGLO * 3600:
        return None
    return d


def _guardar_arreglo(clave, arreglar):
    """Deja apuntado (o borra, con None) el vídeo que hay que rehacer en el siguiente turno de la cuenta."""
    if arreglar:
        antes = privado.leer(_ruta_arreglo(clave), {}) or {}
        misma = antes.get("guion") and antes.get("titulo") == arreglar.get("titulo") and antes.get("version") == arreglar.get("version")
        privado.escribir(_ruta_arreglo(clave), dict(arreglar, clave=clave,
                                                    fecha=antes.get("fecha") if misma else privado.ahora()))
    elif os.path.exists(os.path.join(privado.carpeta(), _ruta_arreglo(clave))):
        privado.escribir(_ruta_arreglo(clave), {"guion": None, "fecha": privado.ahora()})   # ya no hay nada pendiente


def _apuntar_arreglo(clave, arreglar, a, acepta):
    if a.prueba or not acepta:
        return
    try:
        _guardar_arreglo(clave, arreglar)
    except Exception:
        pass


def _para_arreglar(g, v, version, minimo):
    """Lo que necesita el guionista para rehacer el mismo vídeo: el guion que se grabó y lo que le vieron los jueces."""
    veredicto = {k: v.get(k) for k in ("total", "consejo", "fallos_graves", "fiscalia", "defensa", "medidas", "publico")}
    veredicto["votos"] = [{k: x.get(k) for k in ("juez", "nota", "razon")} for x in v.get("votos") or []]
    return {"guion": estudio_animacion.guion_escrito(g), "veredicto": veredicto, "version": version, "minimo": minimo,
            "titulo": g.get("titulo"), "jurado": g.get("jurado")}


def _turno_estudio(clave, canal, cuadernos, nombres, trabajo, paso, resumen, a, lecciones=None, ajustes=None):
    """Turno de una cuenta animada: el estudio hace el vídeo y el Juzgado lo juzga. Si lo suspende por poco, el
    guionista rehace ESE vídeo corrigiendo uno por uno los fallos que le han visto (hasta VERSIONES versiones); si se
    queda lejos, se tira y se hace otro distinto. Lo que no da tiempo a arreglar en este turno queda apuntado y es lo
    primero del siguiente. Devuelve el resumen igual que el turno normal (el «finally» de main lo guarda)."""
    lecciones = lecciones or cuadernos["escritor"].para_el_prompt()
    ajustes = ajustes or privado.ajustes()
    consejo = ""
    intentos = int(canal.get("intentos_estudio", 3))
    umbral = int(canal.get("nota_para_arreglar", ajustes.get("nota_para_arreglar", NOTA_PARA_ARREGLAR)))
    versiones = int(ajustes.get("versiones_por_video", VERSIONES))
    minimo = tribunal.minima(canal)
    _, formato = estudio_animacion.formato_de(canal)
    try:                                           # ¿este formato sabe rehacer un vídeo con sus fallos?
        acepta_arreglo = "arreglar" in inspect.signature(formato.guionizar).parameters
    except (TypeError, ValueError):
        acepta_arreglo = False
    arreglar = None if a.prueba or not acepta_arreglo else arreglo_pendiente(clave)   # lo que quedó del turno anterior
    if arreglar and int(arreglar.get("version") or 2) > versiones:
        arreglar = None
    video, sin_juez = None, False
    for intento in range(1, intentos + 1):
        version = int(arreglar.get("version") or 2) if arreglar else 1
        if arreglar:                               # el mismo vídeo, corregido con lo que han dicho los jueces
            nota_antes = (arreglar.get("veredicto") or {}).get("total", "-")
            paso("escritor", f"versión {version} de «{arreglar.get('titulo', '')}» (se quedó en {nota_antes}/100): "
                 "corrige uno por uno los fallos que le vieron los jueces",
                 f"versión {version} del vídeo que se quedó en {nota_antes}/100: corrige sus fallos")
            g0 = formato.guionizar(canal, lecciones, arreglar=arreglar)
            g0.update(cerebro=ia.quien().get("motor", "gemini"), version=version, arreglo_de=arreglar.get("titulo"))
            if arreglar.get("jurado"):             # el Jurado ya votó ese guion: no se reúne otra vez por un arreglo
                g0["jurado"] = arreglar["jurado"]
        else:
            paso("escritor", "escribiendo el guion del estudio")
            g0 = formato.guionizar(canal, lecciones + consejo)
            g0["cerebro"] = ia.quien().get("motor", "gemini")
            g0, vale = _jurado_guion(clave, canal, g0, paso, a,
                                     reescribir=lambda extra: dict(formato.guionizar(canal, lecciones + consejo + extra),
                                                                   cerebro=ia.quien().get("motor", "gemini")))
            if not vale:
                paso("subidor", "el jurado popular no se convence con el guion: no se graba (se ahorran voz y dibujos)")
                resumen.update(titulo=g0.get("titulo"), destino_resultado="suspendido", intento=intento,
                               motivo="el jurado popular rechazó el guion")
                consejo = ("\n- (El jurado popular ha rechazado varias versiones de «" + str(g0.get("titulo", "")) +
                           "»: cambia de tema o de enfoque.)")
                continue
        video, g = estudio_animacion.hacer(canal, lecciones + consejo,
                                           carpeta=os.path.join(trabajo, f"estudio{intento}"),
                                           avisar=lambda t: paso("montador", t), guion=g0)
        for campo in ("version", "arreglo_de"):
            if g0.get(campo) is not None:
                g[campo] = g0[campo]
        g["narracion"] = " ".join(e.get("voz") or e.get("texto", "") for e in g["escenas"])
        g["texto_pantalla"] = g["escenas"][0].get("texto", "")
        id_guion = cuadernos["escritor"].apuntar("guion", {"canal": clave, "titulo": g.get("titulo"),
                                                           "formato": g.get("formato"), "prueba": a.prueba,
                                                           "version": version})
        segundos = montador.duracion(video)
        cuadernos["montador"].apuntar("montaje", {"canal": clave, "guion": id_guion, "segundos": round(segundos, 1),
                                                  "estudio": g.get("formato")})
        audio = os.path.join(trabajo, f"estudio{intento}", "voz.mp3")
        v = tribunal.juzgar(video, g, canal, cuadernos["juez_guardia"].para_el_prompt(),
                            os.path.join(trabajo, f"juicio{intento}"), audio=audio if os.path.exists(audio) else None, prueba=a.prueba)
        if v.get("veredicto") == "sin_juicio" and not a.prueba:
            # no hay juez ahora (ni la IA gratis ni la de pago): nada sale sin juicio y no cuenta como suspenso
            paso("juez_guardia", "no hay juez ahora (la IA no contesta): el vídeo no se puede juzgar; la cuenta espera")
            sin_juez = True
            break
        v["intento"] = intento                  # la app enseña «Intento 2» a partir del segundo
        v["version"] = version                  # y «versión corregida» cuando es el mismo vídeo arreglado
        id_tribunal = tribunal.guardar_juicio(clave, g, v, prueba=a.prueba)
        id_juicio = cuadernos["juez_guardia"].apuntar("juicio", {"canal": clave, "guion": id_guion,
                                                                 "veredicto": v["veredicto"], "total": v.get("total")})
        cuadernos["escritor"].nota(id_guion, v.get("total"), "nota del Juzgado", v.get("consejo", ""))
        paso("juez_guardia", f"{v['veredicto']} ({v.get('total', '-')}/100) {v.get('consejo', '')}",
             f"{v['veredicto']} ({v.get('total', '-')}/100)")
        resumen.update(titulo=g.get("titulo"), veredicto=v["veredicto"], nota=v.get("total"), consejo=v.get("consejo"),
                       juicio=id_juicio, juicio_app=id_tribunal, segundos=round(segundos, 1), intento=intento,
                       formato=g.get("formato"), version=version)
        if v["veredicto"] == "aprobado" or a.prueba:
            arreglar = None
            _apuntar_arreglo(clave, arreglar, a, acepta_arreglo)
            break
        nota = v.get("total")
        anterior = ((arreglar or {}).get("veredicto") or {}).get("total")
        if acepta_arreglo and isinstance(nota, (int, float)) and nota >= umbral and version < versiones:
            if arreglar and isinstance(anterior, (int, float)) and nota < anterior:
                # el arreglo ha salido peor: se vuelve a partir de la versión buena, sabiendo qué no repetir
                arreglar = dict(arreglar, version=version + 1,
                                no_repetir=(arreglar.get("no_repetir") or []) + [str(v.get("consejo") or "")[:300]])
            else:
                arreglar = _para_arreglar(g, v, version + 1, minimo)
            _apuntar_arreglo(clave, arreglar, a, acepta_arreglo)
            if intento < intentos:
                paso("juez_guardia", f"se queda en {nota}/100: no se tira, se rehace corrigiendo lo que han visto los "
                     f"jueces (versión {version + 1})")
            continue
        arreglar = None
        _apuntar_arreglo(clave, arreglar, a, acepta_arreglo)
        consejo = (f"\n- (El Juzgado ha suspendido el intento anterior, «{g.get('titulo', '')}», con "
                   f"{v.get('total', '-')}/100: {v.get('consejo', '')} "
                   + " ".join(f"{x.get('juez')}: {str(x.get('razon'))[:200]}" for x in (v.get("votos") or [])[:3])
                   + " Haz otro vídeo distinto que no tenga esos fallos.)")
        if intento < intentos:
            paso("juez_guardia", "suspendido y lejos de la nota: se tira y se hace otro distinto con lo aprendido")
    if not a.prueba and acepta_arreglo:        # lo que quede por arreglar es lo primero del siguiente turno de la cuenta
        try:
            _guardar_arreglo(clave, arreglar)
            if arreglar:
                resumen["arreglo_pendiente"] = {"version": arreglar.get("version"), "titulo": arreglar.get("titulo")}
        except Exception as e:
            paso("escritor", f"no he podido apuntar el arreglo pendiente ({type(e).__name__})")
    if sin_juez:
        resumen.pop("destino_resultado", None)          # no es un suspenso: es una espera
        raise ia.SinIA("no hay juez ahora: el vídeo se queda sin juzgar y la cuenta espera a la siguiente ronda")
    if video is None:          # el jurado popular rechazó todos los guiones: no se ha grabado nada
        paso("subidor", "el jurado popular rechazó todos los guiones: hoy no se graba nada (se ahorran voz y dibujos)")
        resumen.update(destino_resultado="suspendido", resultado="hecho")
        return resumen
    g = _coliseo(clave, canal, g, v, paso, a, resumen)
    if a.prueba:
        paso("subidor", "es una prueba: no se sube nada")
        resumen["destino_resultado"] = "prueba"
        if os.environ.get("ALMACEN_PRUEBAS"):
            resumen["video_prueba"] = parasubir.almacen.guardar("pruebas", video, f"{os.path.basename(trabajo)}.mp4")
    elif v["veredicto"] != "aprobado":
        if arreglar:
            paso("subidor", f"se queda en {v.get('total', '-')}/100: su versión corregida es lo primero del siguiente "
                 "turno")
        else:
            paso("subidor", f"no llega a la nota que pide el dueño ({v.get('total', '-')}/100): se tira, no se sube")
        resumen["destino_resultado"] = "suspendido"
    elif canal.get("destino") != "parasubir":        # un canal de YouTube con un formato del estudio (p. ej. hipnótico)
        _destino(clave, canal, video, g, v, segundos, id_guion, cuadernos, ajustes, paso, a, resumen)
        estudio_animacion.apuntar(clave, g)
    else:
        ids = parasubir.dejar(clave, canal, video, g, segundos, v)
        cuadernos["publicador"].apuntar("para_subir", {"barrio": clave, "documentos": ids, "guion": id_guion})
        privado.apuntar_titulo(clave, g.get("titulo", ""))
        estudio_animacion.apuntar(clave, g)
        paso("publicador", f"en la bandeja «Para subir»: {', '.join(ids)}", f"en la bandeja ({len(ids)} redes)")
        resumen.update(destino_resultado="para_subir", documentos=ids)
    resumen["resultado"] = "hecho"
    return resumen


def _lecciones_escritor(clave, cuadernos):
    """Lo que ha aprendido el Escritor y la receta de los Influencers (Radar, Ojeador y Entrenador) para este canal."""
    receta = (privado.leer(os.path.join("estado", "influencers", "recetas.json"), {}) or {}).get("canales", {}).get(clave)
    lecciones = cuadernos["escritor"].para_el_prompt()
    if receta:
        lecciones += "\n- (Receta de los Influencers, de lo que funciona ahora) " + json.dumps(
            {k: v for k, v in receta.items() if k not in ("fecha", "basada_en")}, ensure_ascii=False)
    try:                       # lo que el dueño ha descartado manda más que la nota del Juzgado
        tirados = privado.descartes(clave)
        if tirados:
            lecciones += ("\n- (EL DUEÑO HA DESCARTADO estos vídeos de esta cuenta aunque tuvieran buena nota; no hagas "
                          "más con ese tema, ese enfoque ni ese estilo, y busca algo claramente distinto)\n" + tirados)
        funciona = privado.exitos(clave)
        if funciona:
            lecciones += "\n- (Lo que más visitas le ha dado de verdad a esta cuenta; haz más como lo de arriba)\n" + funciona
    except Exception:
        pass
    return lecciones


def _turno_clip(clave, canal, m, cuadernos, ajustes, trabajo, paso, resumen, a, lecciones):
    """Turno con un clip con licencia libre (CC BY) que el dueño ha grabado y subido en la app. El Portero de clips mira
    que solo salga el juego (recorta o descarta), el Escritor lo narra mirando unas fotos, el Jurado popular vota la
    narración, el Locutor pone la voz y el Montador de clips monta el Short. Después, como todos: Juzgado, Coliseo y
    subida, con el crédito del creador en la descripción."""
    resumen.update(clip=m.get("codigo"), formato="clip")
    paso("montador", f"clip {m.get('codigo')} grabado por el dueño: lo bajo del buzón", "bajando el clip grabado")
    ruta = clips.bajar(m, os.path.join(trabajo, "clip"))
    if m.get("en_videoteca"):            # el Archivero ya lo pasó por el Portero y lo guardó limpio
        toma = next((t for t in videoteca.tomas() if t["id"] == m.get("codigo")), {})
        rev = {"vale": True, "bandas": None, "recorte": None, "sonido": bool(toma.get("sonido")), "problemas": [],
               "fotos": clips.fotos(ruta, os.path.join(trabajo, "clip", "fotos"), cuantas=5)}
        paso("portero_clips", "ya estaba limpio en la videoteca")
    else:
        paso("portero_clips", "mirando que solo salga el juego")
        rev = clips.revisar(ruta, os.path.join(trabajo, "clip", "portero"), m)
        cuadernos["portero_clips"].apuntar("revision", {"canal": clave, "clip": m.get("codigo"), "vale": rev["vale"],
                                                        "recorte": bool(rev["recorte"]), "bandas": bool(rev["bandas"]),
                                                        "sonido": rev["sonido"], "problemas": rev["problemas"]})
    if not rev["vale"]:
        motivo = "sale algo del creador y no se puede quitar: " + (", ".join(rev["problemas"]) or "sin detalle")
        paso("portero_clips", motivo, "el clip no vale: sale algo del creador")
        if not a.prueba:
            clips.descartar(m, motivo[:300])
        resumen.update(destino_resultado="suspendido", motivo="el Portero de clips lo ha descartado", resultado="hecho")
        return
    if not m.get("en_videoteca"):
        paso("portero_clips", ("recorto lo que no es juego; " if rev["recorte"] else "")
             + ("quito las bandas negras; " if rev["bandas"] else "")
             + ("dejo el sonido del juego bajito" if rev["sonido"] else "quito el sonido del clip y pongo música propia"))
    largo = clips._segundos(ruta)
    vistas = rev["fotos"][::2] or rev["fotos"]        # 3 de las 5 fotos (principio, medio y final), ya recortadas
    reglas_juez = cuadernos["juez_guardia"].para_el_prompt() + "\n- " + clips.REGLA
    hoy = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d-%H%M")
    aviso_juez, v, video, segundos, id_guion = "", {}, None, 0.0, None
    for intento in (1, 2):
        if intento == 2:
            paso("escritor", "segunda oportunidad: lo reescribe con el consejo del Juez")
        paso("escritor", "escribiendo la narración del clip")
        g = dict(clips.guionizar(canal, m, lecciones + aviso_juez, segundos=largo, imagenes=vistas),
                 cerebro=ia.quien().get("motor", "gemini"))
        g, vale = _jurado_guion(clave, canal, g, paso, a, reescribir=lambda extra: dict(
            clips.guionizar(canal, m, lecciones + aviso_juez + extra, segundos=largo, imagenes=vistas),
            cerebro=ia.quien().get("motor", "gemini")))
        if not vale:
            paso("subidor", "el jurado popular no se convence con la narración: no se graba (se ahorra la voz)")
            resumen.update(titulo=g.get("titulo"), destino_resultado="suspendido",
                           motivo="el jurado popular rechazó el guion", resultado="hecho")
            if not a.prueba:
                clips.tras_juicio(m, False)
            return
        clips.guardar_guion(trabajo, g)
        id_guion = cuadernos["escritor"].apuntar("guion", {"canal": clave, "titulo": g["titulo"], "clip": m.get("codigo"),
                                                           "prueba": a.prueba})
        paso("escritor", f"«{g['titulo']}»", "narración lista")

        paso("locutor", f"grabando la voz ({canal.get('voz')})", "grabando la voz")
        asyncio.run(locutor.generar(g["narracion"], canal.get("voz", "es-MX-JorgeNeural"), canal.get("velocidad", "+10%"),
                                    "+0Hz", trabajo))
        quitado = locutor.apretar(trabajo)
        _voz_de_pago(g, canal)
        cuadernos["locutor"].apuntar("voz", {"canal": clave, "guion": id_guion, "silencio_quitado": quitado})
        paso("locutor", f"voz lista ({quitado} s de silencios quitados)")

        paso("montador", "montando el Short con el clip")
        video = clips.montar(ruta, g, os.path.join(trabajo, "voz.mp3"), os.path.join(trabajo, "palabras.json"),
                             os.path.join(trabajo, f"{hoy}-{clave}.mp4"), revision=rev,
                             ambiente=montador.musica.ambiente_de(canal))
        segundos = montador.duracion(video)
        cuadernos["montador"].apuntar("montaje", {"canal": clave, "guion": id_guion, "segundos": round(segundos, 1),
                                                  "clip": m.get("codigo")})
        paso("montador", f"vídeo de {segundos:.1f} s")

        paso("juez_guardia", "juzgando el vídeo")
        v = tribunal.juzgar(video, g, canal, reglas_juez, os.path.join(trabajo, f"juicio{intento}"),
                            audio=os.path.join(trabajo, "voz.mp3"), prueba=a.prueba)
        _sin_juez(v, a, paso)
        v["intento"] = intento
        id_tribunal = tribunal.guardar_juicio(clave, g, v, prueba=a.prueba)
        id_juicio = cuadernos["juez_guardia"].apuntar("juicio", {"canal": clave, "guion": id_guion, "clip": m.get("codigo"),
                                                                 "veredicto": v["veredicto"], "total": v.get("total")})
        cuadernos["escritor"].nota(id_guion, v.get("total"), "nota del Juez de guardia", v.get("consejo", ""))
        paso("juez_guardia", f"{v['veredicto']} ({v.get('total', '-')}/100) {v.get('consejo', '')}",
             f"{v['veredicto']} ({v.get('total', '-')}/100)")
        resumen.update(titulo=g["titulo"], veredicto=v["veredicto"], nota=v.get("total"), consejo=v.get("consejo"),
                       juicio=id_juicio, segundos=round(segundos, 1), intento=intento, fallos=v.get("fallos_graves"),
                       tribunal=v.get("tribunal"), juicio_app=id_tribunal)
        if v["veredicto"] == "aprobado" or a.prueba or not ajustes.get("segunda_oportunidad", True):
            break
        aviso_juez = (f"\n- (Juez de guardia, sobre la versión anterior, suspendida con {v.get('total', '-')}/100) "
                      f"{v.get('consejo', '')} Fallos: {', '.join(v.get('fallos_graves') or []) or 'ninguno grave'}. "
                      "Escribe una narración distinta que lo corrija.)")
    g = _coliseo(clave, canal, g, v, paso, a, resumen)
    _destino(clave, canal, video, g, v, segundos, id_guion, cuadernos, ajustes, paso, a, resumen)
    if not a.prueba:
        clips.tras_juicio(m, v.get("veredicto") == "aprobado", nota=v.get("total"), titulo=g.get("titulo"),
                          destino=resumen.get("destino_resultado"))
    resumen["resultado"] = "hecho"


def _turno_tomas(clave, canal, cuadernos, ajustes, trabajo, paso, resumen, a, lecciones, fuentes, lista):
    """Turno de un canal de GTA con la Videoteca: el Escritor escribe a partir de las tomas de juego de verdad (cada
    escena enseña lo que dice la voz) y el Montador las corta en planos de 2-3 s; en GTA 5 contra GTA 6, pantalla
    partida por rondas. Después, como todos: Jurado popular, voz, Juzgado, Coliseo y subida."""
    disponibles = videoteca.disponibles(canal)
    resumen.update(formato="versus_clips" if canal.get("tipo") == "versus" else "clips", tomas=len(disponibles))
    paso("escritor", f"esta vez con clips de verdad: {len(disponibles)} tomas en la videoteca")
    catalogo = "TOMAS DE JUEGO DISPONIBLES (el vídeo solo puede enseñar esto):\n" + videoteca.catalogo(disponibles)
    idea, id_idea = None, None
    if ajustes.get("sala_ideas", True):
        try:
            propuestas = escritor.ideas(canal, lecciones, privado.titulos_recientes(clave),
                                        f"{fuentes}\n\n{catalogo}" if fuentes else catalogo)
            idea, id_idea = sala_ideas.elegir(clave, canal, propuestas, tribunal._pruebas(clave, canal))
            paso("escritor", f"la Sala de Ideas eligió «{(idea or {}).get('titulo')}» de {len(propuestas)}",
                 f"la Sala de Ideas eligió 1 de {len(propuestas)}")
        except Exception as e:
            paso("escritor", f"sin Sala de Ideas hoy ({type(e).__name__})")
    reglas_juez = cuadernos["juez_guardia"].para_el_prompt() + "\n- " + clips.REGLA
    hoy = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d-%H%M")
    aviso_juez, v, video, segundos, id_guion, g = "", {}, None, 0.0, None, {}
    for intento in (1, 2):
        if intento == 2:
            paso("escritor", "segunda oportunidad: lo reescribe con el consejo del Juez")
        paso("escritor", "escribiendo el guion con las tomas")
        g = videoteca.guionizar(canal, disponibles, lecciones + aviso_juez, privado.titulos_recientes(clave), fuentes, idea)
        g, vale = _jurado_guion(clave, canal, g, paso, a, alegatos=_alegatos_idea(id_idea),
                                reescribir=lambda extra: videoteca.guionizar(
                                    canal, disponibles, lecciones + aviso_juez + extra, privado.titulos_recientes(clave),
                                    fuentes, idea))
        if not vale:
            paso("subidor", "el jurado popular no se convence con el guion: no se graba (se ahorra la voz)")
            resumen.update(titulo=g.get("titulo"), destino_resultado="suspendido",
                           motivo="el jurado popular rechazó el guion", resultado="hecho")
            return
        if lista:
            reportero.apuntar_usadas(clave, lista, g.get("fuentes_usadas"))
        json.dump(g, open(os.path.join(trabajo, "guion.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        id_guion = cuadernos["escritor"].apuntar("guion", {"canal": clave, "titulo": g["titulo"], "idea": g.get("idea"),
                                                           "formato": g["formato"], "tomas": g["tomas_usadas"],
                                                           "prueba": a.prueba})
        paso("escritor", f"«{g['titulo']}» ({len(g['escenas'])} escenas con {len(g['tomas_usadas'])} tomas)",
             f"guion listo ({len(g['escenas'])} escenas con {len(g['tomas_usadas'])} tomas)")

        paso("locutor", f"grabando la voz ({canal.get('voz')})", "grabando la voz")
        asyncio.run(locutor.generar(g["narracion"], canal.get("voz", "es-MX-JorgeNeural"), canal.get("velocidad", "+10%"),
                                    "+0Hz", trabajo))
        quitado = locutor.apretar(trabajo)
        _voz_de_pago(g, canal)
        cuadernos["locutor"].apuntar("voz", {"canal": clave, "guion": id_guion, "silencio_quitado": quitado})
        paso("locutor", f"voz lista ({quitado} s de silencios quitados)")

        paso("montador", f"bajando {len(g['tomas_usadas'])} tomas de la videoteca y montando")
        rutas = videoteca.bajar(g["tomas_usadas"], os.path.join(trabajo, "tomas"))
        video = videoteca.montar(g, rutas, os.path.join(trabajo, "voz.mp3"), os.path.join(trabajo, "palabras.json"),
                                 os.path.join(trabajo, f"{hoy}-{clave}.mp4"), ambiente=montador.musica.ambiente_de(canal))
        segundos = montador.duracion(video)
        cuadernos["montador"].apuntar("montaje", {"canal": clave, "guion": id_guion, "segundos": round(segundos, 1),
                                                  "formato": g["formato"], "tomas": g["tomas_usadas"]})
        paso("montador", f"vídeo de {segundos:.1f} s con clips de verdad")

        paso("juez_guardia", "juzgando el vídeo")
        v = tribunal.juzgar(video, g, canal, reglas_juez, os.path.join(trabajo, f"juicio{intento}"),
                            audio=os.path.join(trabajo, "voz.mp3"), prueba=a.prueba)
        _sin_juez(v, a, paso)
        v["intento"] = intento
        id_tribunal = tribunal.guardar_juicio(clave, g, v, prueba=a.prueba)
        id_juicio = cuadernos["juez_guardia"].apuntar("juicio", {"canal": clave, "guion": id_guion,
                                                                 "veredicto": v["veredicto"], "total": v.get("total")})
        cuadernos["escritor"].nota(id_guion, v.get("total"), "nota del Juez de guardia", v.get("consejo", ""))
        paso("juez_guardia", f"{v['veredicto']} ({v.get('total', '-')}/100) {v.get('consejo', '')}",
             f"{v['veredicto']} ({v.get('total', '-')}/100)")
        resumen.update(titulo=g["titulo"], veredicto=v["veredicto"], nota=v.get("total"), consejo=v.get("consejo"),
                       juicio=id_juicio, segundos=round(segundos, 1), intento=intento, fallos=v.get("fallos_graves"),
                       tribunal=v.get("tribunal"), juicio_app=id_tribunal, juicio_idea=id_idea)
        if v["veredicto"] == "aprobado" or a.prueba or not ajustes.get("segunda_oportunidad", True):
            break
        aviso_juez = (f"\n- (Juez de guardia, sobre la versión anterior, suspendida con {v.get('total', '-')}/100) "
                      f"{v.get('consejo', '')} Fallos: {', '.join(v.get('fallos_graves') or []) or 'ninguno grave'}. "
                      "Escribe un guion distinto que lo corrija.)")
    g = _coliseo(clave, canal, g, v, paso, a, resumen)
    _destino(clave, canal, video, g, v, segundos, id_guion, cuadernos, ajustes, paso, a, resumen)
    if v.get("veredicto") == "aprobado" and not a.prueba:
        videoteca.apuntar_usos(g.get("tomas_usadas") or [])
    resumen["resultado"] = "hecho"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--canal")
    p.add_argument("--peticion")
    p.add_argument("--hora", help="hueco donde programarlo (ISO); si no se da, lo calcula")
    p.add_argument("--prueba", action="store_true", help="hace el vídeo pero no lo sube ni lo deja para subir")
    p.add_argument("--salida", default="trabajo")
    a = p.parse_args(argv)
    clave = privado.resolver(a.canal or json.load(open(a.peticion, encoding="utf-8"))["canal"])
    canal = privado.canal(clave)
    ajustes = privado.ajustes()
    hoy = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d-%H%M")
    trabajo = os.path.join(a.salida, f"{hoy}-{privado.alias(clave)}")
    os.makedirs(trabajo, exist_ok=True)
    nombres = puestos(clave, canal)
    cuadernos = {r: privado.cuaderno(nombres[r]) for r in ROBOTS}
    registro = []

    en_curso = {"robot": "escritor"}

    id_obra = ((None if a.prueba else obras.retomar(clave)) or     # sigue en la ficha que se quedó esperando
               f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')}-{privado.alias(clave)}".replace(".", "-"))

    def paso(robot, texto, publico=None):
        if robot in cuadernos:
            en_curso["robot"] = robot
        hora = dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%S')
        registro.append(f"[{hora}] {robot}: {texto}")
        print(privado.limpiar(f"[{hora}] {clave} · {robot}: {publico if publico is not None else texto}"), flush=True)
        if not a.prueba and robot != "turno":  # «Ahora en la fábrica» (la app): qué robot lo tiene y qué hace
            obras.apuntar(id_obra, clave, robot=nombres.get(robot, robot),
                          paso=obras.PASOS.get(nombres.get(robot, robot)) or obras.PASOS.get(robot),
                          detalle=publico if publico is not None else texto, titulo=resumen.get("titulo"))

    resumen = {"canal": clave, "nombre": canal["nombre"], "destino": canal["destino"], "prueba": a.prueba,
               "empezado": privado.ahora()}
    ia.SOLO_CLAUDE = canal.get("guionista") == "claude"      # la Élite puede pedir que esta cuenta solo la escriba Claude
    try:
        clip = None if canal.get("estudio") == "animacion" else clips.listo_para(clave)
        if clip:                    # el dueño ha grabado un clip para este canal: va antes que nada
            cuadernos["portero_clips"] = privado.cuaderno("portero_clips")
            nombres["portero_clips"] = "portero_clips"
            _turno_clip(clave, canal, clip, cuadernos, ajustes, trabajo, paso, resumen, a,
                        _lecciones_escritor(clave, cuadernos))
            raise _Hecho()
        fuentes, lista = None, []
        if canal.get("tipo") in CON_FUENTES and canal.get("fuentes"):
            paso("reportero_gta6", "buscando fuentes")
            fuentes, lista = reportero.fuentes(clave, canal, registro=lambda t: paso("reportero_gta6", t))
            if not fuentes:
                raise RuntimeError("el Reportero no ha encontrado ninguna fuente hoy")
            cuadernos["reportero_gta6"].apuntar("fuentes", {"canal": clave, "cuantas": len(lista)})
            paso("reportero_gta6", f"{len(lista)} fuentes")

        lecciones_escritor = _lecciones_escritor(clave, cuadernos)   # con la receta de los Influencers
        if canal.get("estudio") == "animacion":     # cuentas de vídeos animados (las del dueño): el estudio de animación
            _turno_estudio(clave, canal, cuadernos, nombres, trabajo, paso, resumen, a, lecciones_escritor)
            raise _Hecho()
        if canal.get("destino") == "youtube" and _toca_hipnotico(clave, canal):   # el Animador hipnótico (uno de cada N)
            paso("escritor", "esta vez, formato hipnótico: bolas de neón con la historia narrada")
            _turno_estudio(clave, _canal_hipnotico(canal), cuadernos, nombres, trabajo, paso, resumen, a,
                           lecciones_escritor, ajustes)
            resumen["formato"] = "hipnotico"
            raise _Hecho()
        if videoteca.suficientes(canal):           # canales de GTA con tomas de juego de verdad: nada de dibujos
            _turno_tomas(clave, canal, cuadernos, ajustes, trabajo, paso, resumen, a, lecciones_escritor, fuentes, lista)
            raise _Hecho()
        idea, id_idea = None, None
        sin_fotos = []
        con_fotos = canal.get("fotos") == "commons"
        if ajustes.get("sala_ideas", True) or con_fotos:     # la Sala de Ideas elige la mejor de 3 antes de gastar
            paso("escritor", "proponiendo ideas a la Sala de Ideas")
            try:
                propuestas = escritor.ideas(canal, lecciones_escritor, privado.titulos_recientes(clave), fuentes)
                if con_fotos:                    # solo valen las personas de las que hay fotos libres bastantes
                    propuestas, sin_fotos = _ideas_con_fotos(propuestas, paso)
                    if not propuestas:           # otra tanda de ideas, sabiendo de quién no hay
                        propuestas = escritor.ideas(canal, lecciones_escritor + "\n- (De estas personas NO hay fotos "
                                                    "libres: " + "; ".join(sin_fotos) + ". Propón otras.)",
                                                    privado.titulos_recientes(clave), fuentes)
                        propuestas, mas = _ideas_con_fotos(propuestas, paso)
                        sin_fotos += mas
                    if not propuestas:
                        paso("subidor", "no hay fotos libres de ninguna de las personas propuestas: hoy no se graba")
                        resumen.update(destino_resultado="suspendido", resultado="hecho",
                                       motivo="no hay fotos libres de las personas propuestas")
                        raise _Hecho()
                if ajustes.get("sala_ideas", True):
                    idea, id_idea = sala_ideas.elegir(clave, canal, propuestas, tribunal._pruebas(clave, canal))
                else:
                    idea = propuestas[0] if propuestas else None
                paso("escritor", f"la Sala de Ideas eligió «{(idea or {}).get('titulo')}» de {len(propuestas)}",
                     f"la Sala de Ideas eligió 1 de {len(propuestas)}")
            except _Hecho:
                raise
            except ia.SinIA:
                if con_fotos:           # sin ideas no se sabe de quién hay fotos: mejor esperar que escribir a ciegas
                    raise
                paso("escritor", "sin Sala de Ideas hoy (SinIA)")
            except Exception as e:      # sin Sala de Ideas, el Escritor sigue solo
                paso("escritor", f"sin Sala de Ideas hoy ({type(e).__name__})")
        aviso_juez = ""
        for intento in (1, 2):           # si el Juez lo suspende, una segunda oportunidad con su consejo
            if intento == 2:
                paso("escritor", "segunda oportunidad: lo reescribe con el consejo del Juez")
            paso("escritor", "escribiendo el guion")
            g = escritor.escribir(canal, lecciones_escritor + aviso_juez,
                                 privado.titulos_recientes(clave), fuentes, idea=idea)
            g, vale = _jurado_guion(clave, canal, g, paso, a, alegatos=_alegatos_idea(id_idea),
                                    reescribir=lambda extra: escritor.escribir(
                                        canal, lecciones_escritor + aviso_juez + extra, privado.titulos_recientes(clave),
                                        fuentes, idea=idea))
            if not vale:
                paso("subidor", "el jurado popular no se convence con el guion: no se graba (se ahorran voz y dibujos)")
                resumen.update(titulo=g.get("titulo"), destino_resultado="suspendido",
                               motivo="el jurado popular rechazó el guion", resultado="hecho")
                raise _Hecho()
            if lista:
                reportero.apuntar_usadas(clave, lista, g.get("fuentes_usadas"))
            json.dump(g, open(os.path.join(trabajo, "guion.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            id_guion = cuadernos["escritor"].apuntar("guion", {"canal": clave, "titulo": g["titulo"], "idea": g.get("idea"),
                                                               "prueba": a.prueba})
            paso("escritor", f"«{g['titulo']}» ({len(g['escenas'])} escenas)", f"guion listo ({len(g['escenas'])} escenas)")

            imagenes = None
            if canal.get("fotos") == "commons":       # biografías: fotos libres de verdad, antes de gastar en la voz
                paso("dibujante", f"buscando {len(g['escenas'])} fotos libres en Wikimedia Commons")
                imagenes, origen = fotografo.fotografiar(g["escenas"], os.path.join(trabajo, f"dibujos{intento}"),
                                                         persona=str(g.get("persona") or (idea or {}).get("persona") or ""))
                g["fotos_de"] = origen             # de dónde sale cada foto queda apuntado, pero no se pone en el vídeo
                faltan = imagenes.count(None)
                cuadernos["dibujante"].apuntar("fotos", {"canal": clave, "pedidas": len(imagenes), "faltan": faltan,
                                                         "distintas": len(origen)})
                if faltan > max(1, len(imagenes) // 3):
                    paso("dibujante", f"solo hay fotos libres para {len(imagenes) - faltan} de {len(imagenes)} escenas: "
                         "esa persona no vale")
                    sin_fotos.append(str(g.get("persona") or g.get("titulo") or "?"))
                    aviso_juez = ("\n- (De estas personas NO hay fotos libres bastantes: " + "; ".join(sin_fotos) +
                                  ". Elige OTRA persona de la que sí haya, como dicen las reglas.)")
                    idea = None
                    if intento == 2:
                        paso("subidor", "sin fotos libres de dos personas seguidas: hoy no se graba (cuenta como intento)")
                        resumen.update(titulo=g.get("titulo"), destino_resultado="suspendido", resultado="hecho",
                                       motivo="no hay fotos libres bastantes de esa persona")
                        raise _Hecho()
                    continue
                paso("dibujante", f"{len(imagenes) - faltan}/{len(imagenes)} escenas con foto libre ({len(origen)} fotos distintas)")

            paso("locutor", f"grabando la voz ({canal.get('voz')})", "grabando la voz")
            asyncio.run(locutor.generar(g["narracion"], canal.get("voz", "es-MX-JorgeNeural"), canal.get("velocidad", "+10%"),
                                        "+0Hz", trabajo))
            quitado = locutor.apretar(trabajo)
            _voz_de_pago(g, canal)
            cuadernos["locutor"].apuntar("voz", {"canal": clave, "guion": id_guion, "silencio_quitado": quitado})
            paso("locutor", f"voz lista ({quitado} s de silencios quitados)")

            if imagenes is None:
                t0 = dt.datetime.now(dt.timezone.utc)
                paso("dibujante", f"pidiendo {len(g['escenas'])} dibujos a AI Horde ({canal.get('dibujos')})")
                imagenes = dibujante.dibujar(g["escenas"], canal.get("dibujos", "AlbedoBase XL (SDXL)"),
                                             os.path.join(trabajo, "dibujos"))
                faltan = imagenes.count(None)
                minutos = round((dt.datetime.now(dt.timezone.utc) - t0).total_seconds() / 60, 1)
                cuadernos["dibujante"].apuntar("dibujos", {"canal": clave, "pedidos": len(imagenes), "faltan": faltan,
                                                           "minutos": minutos})
                if faltan > max(1, len(imagenes) // 3):
                    raise RuntimeError(f"faltan {faltan} dibujos de {len(imagenes)}")
                paso("dibujante", f"{len(imagenes) - faltan}/{len(imagenes)} dibujos hechos en {minutos} min")

            paso("montador", "montando el vídeo")
            video = montador.montar(g, imagenes, os.path.join(trabajo, "voz.mp3"), os.path.join(trabajo, "palabras.json"),
                                    os.path.join(trabajo, f"{hoy}-{clave}.mp4"),  # nombre único: el registro lo usa
                                    ambiente=None if juez_guardia.sin_musica(canal)     # el dueño pone su música
                                    else montador.musica.ambiente_de(canal))
            segundos = montador.duracion(video)
            cuadernos["montador"].apuntar("montaje", {"canal": clave, "guion": id_guion, "segundos": round(segundos, 1)})
            paso("montador", f"vídeo de {segundos:.1f} s")

            paso("juez_guardia", "juzgando el vídeo")
            v = tribunal.juzgar(video, g, canal, cuadernos["juez_guardia"].para_el_prompt(),
                                os.path.join(trabajo, f"juicio{intento}"), audio=os.path.join(trabajo, "voz.mp3"), prueba=a.prueba)
            _sin_juez(v, a, paso)
            v["intento"] = intento                  # la app enseña «Intento 2» a partir del segundo
            id_tribunal = tribunal.guardar_juicio(clave, g, v, prueba=a.prueba)
            id_juicio = cuadernos["juez_guardia"].apuntar("juicio", {"canal": clave, "guion": id_guion,
                                                                     "veredicto": v["veredicto"], "total": v.get("total")})
            cuadernos["escritor"].nota(id_guion, v.get("total"), "nota del Juez de guardia", v.get("consejo", ""))
            paso("juez_guardia", f"{v['veredicto']} ({v.get('total', '-')}/100) {v.get('consejo', '')}",
                 f"{v['veredicto']} ({v.get('total', '-')}/100)")
            resumen.update(titulo=g["titulo"], veredicto=v["veredicto"], nota=v.get("total"), consejo=v.get("consejo"),
                           juicio=id_juicio, segundos=round(segundos, 1), intento=intento,
                           fallos=v.get("fallos_graves"), tribunal=v.get("tribunal"), juicio_app=id_tribunal,
                           juicio_idea=id_idea)
            if v["veredicto"] == "aprobado" or a.prueba or not ajustes.get("segunda_oportunidad", True):
                break
            aviso_juez = (f"\n- (Juzgado, sobre la versión anterior, suspendida con {v.get('total', '-')}/100) "
                          f"{v.get('consejo', '')} Fallos: {', '.join(v.get('fallos_graves') or []) or 'ninguno grave'}. "
                          + " ".join(f"{x.get('juez')} ({x.get('nota')}): {str(x.get('razon'))[:220]}"
                                     for x in (v.get("votos") or [])[:3])
                          + " Escribe un guion que corrija justo eso.)")

        g = _coliseo(clave, canal, g, v, paso, a, resumen)
        _destino(clave, canal, video, g, v, segundos, id_guion, cuadernos, ajustes, paso, a, resumen)
        resumen["resultado"] = "hecho"
    except _Hecho:
        pass
    except Exception as e:  # el turno nunca se queda a medias sin contarlo
        resumen.update(resultado="error", error=f"{type(e).__name__}: {e}", robot=nombres[en_curso["robot"]])
        if de_fuera(resumen["error"]):         # la IA sin cupo o el servicio de dibujos caído: el robot espera, no falla
            cuadernos[en_curso["robot"]].apuntar("espera_ia", {"canal": clave, "motivo": str(e)[:200]})
        else:
            cuadernos[en_curso["robot"]].apuntar("error", {"canal": clave, "error": f"{type(e).__name__}: {str(e)[:300]}"})
        paso("turno", f"ERROR {type(e).__name__}: {e}", f"ERROR {type(e).__name__}")
        detalle = traceback.format_exc()
        with open(os.path.join(trabajo, "fallo.txt"), "w", encoding="utf-8") as f:
            f.write(detalle)
        resumen["traza"] = detalle[-2000:]
        print(privado.limpiar("\n".join(detalle.strip().splitlines()[-12:])), flush=True)
    finally:
        ia.SOLO_CLAUDE = False
        resumen["terminado"] = privado.ahora()
        if not a.prueba:                       # «Ahora en la fábrica»: cómo ha acabado
            fin = resumen.get("destino_resultado") or resumen.get("resultado")
            if resumen.get("resultado") == "error":
                # se queda en el paso donde se paró (no en «sale»): esperando si es cosa de fuera (la IA sin cupo o el
                # servicio de dibujos caído), atasco si es una avería que tienen que mirar los Mecánicos
                robot = nombres[en_curso["robot"]]
                fuera = de_fuera(resumen.get("error"))
                obras.apuntar(id_obra, clave, titulo=resumen.get("titulo"), robot=robot,
                              paso=obras.PASOS.get(robot) or obras.PASOS.get(en_curso["robot"], "guion"),
                              estado="esperando" if fuera else "atasco",
                              detalle=(("la IA no contesta ahora" if str(resumen.get("error")).startswith("SinIA")
                                        else "el servicio gratis de dibujos no contesta ahora")
                                       + ": lo vuelve a intentar en la siguiente ronda") if fuera else
                              "se ha atascado aquí: lo miran los Mecánicos")
            else:
                pendiente = resumen.get("arreglo_pendiente")
                obras.apuntar(id_obra, clave, titulo=resumen.get("titulo"),
                              estado="descartado" if fin == "suspendido" else "terminado",
                              paso={"para_subir": "para_subir", "subido": "subido", "programado": "programado",
                                    "cola": "programado", "suspendido": "juzgado"}.get(fin, "sale"),
                              robot="juez_guardia" if fin == "suspendido" else None,
                              detalle=(f"se queda en {resumen.get('nota', '-')}/100: su versión corregida "
                                       f"(la {pendiente.get('version')}) es lo primero del siguiente turno"
                                       if fin == "suspendido" and pendiente else
                                       f"no llega a la nota ({resumen.get('nota', '-')}/100): se tira"
                                       if fin == "suspendido" else "terminado"))
        with open(os.path.join(trabajo, "registro.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(registro) + "\n")
        json.dump(resumen, open(os.path.join(trabajo, "resumen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        for c in cuadernos.values():
            c.guardar()
        historial = (privado.leer(os.path.join("estado", "central", f"{clave}.json"), {}) or {}).get("turnos", [])
        historial = (historial + [resumen])[-20:]
        privado.guardar_estado(f"central/{clave}.json", {"canal": clave, "ultimo_turno": resumen, "turnos": historial})
        shutil.rmtree(os.path.join(trabajo, "dibujos", "tmp"), ignore_errors=True)
    return 0 if resumen.get("resultado") == "hecho" else 1


if __name__ == "__main__":
    sys.exit(main())
