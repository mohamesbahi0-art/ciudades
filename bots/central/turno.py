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
import json
import os
import shutil
import sys
import traceback

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from bots.central import dibujante, escritor, huecos, montador, parasubir, reportero, subidor  # noqa: E402
from bots.comun import ia, privado  # noqa: E402
from bots.juzgado import jurado, sala_ideas, tribunal  # noqa: E402
from bots.coliseo import coliseo  # noqa: E402
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


def _turno_estudio(clave, canal, cuadernos, nombres, trabajo, paso, resumen, a, lecciones=None):
    """Turno de una cuenta animada: el estudio hace el vídeo, el Juzgado lo juzga (con segunda oportunidad) y va a
    «Para subir». Devuelve el resumen igual que el turno normal (el «finally» de main lo guarda)."""
    lecciones = lecciones or cuadernos["escritor"].para_el_prompt()
    consejo = ""
    intentos = int(canal.get("intentos_estudio", 3))
    _, formato = estudio_animacion.formato_de(canal)
    video = None
    for intento in range(1, intentos + 1):     # si el Juzgado lo suspende, se tira y se hace otro con su consejo
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
        g["narracion"] = " ".join(e.get("voz") or e.get("texto", "") for e in g["escenas"])
        g["texto_pantalla"] = g["escenas"][0].get("texto", "")
        id_guion = cuadernos["escritor"].apuntar("guion", {"canal": clave, "titulo": g.get("titulo"),
                                                           "formato": g.get("formato"), "prueba": a.prueba})
        segundos = montador.duracion(video)
        cuadernos["montador"].apuntar("montaje", {"canal": clave, "guion": id_guion, "segundos": round(segundos, 1),
                                                  "estudio": g.get("formato")})
        audio = os.path.join(trabajo, f"estudio{intento}", "voz.mp3")
        v = tribunal.juzgar(video, g, canal, cuadernos["juez_guardia"].para_el_prompt(),
                            os.path.join(trabajo, f"juicio{intento}"), audio=audio if os.path.exists(audio) else None)
        v["intento"] = intento                  # la app enseña «Intento 2» a partir del segundo
        id_tribunal = tribunal.guardar_juicio(clave, g, v, prueba=a.prueba)
        id_juicio = cuadernos["juez_guardia"].apuntar("juicio", {"canal": clave, "guion": id_guion,
                                                                 "veredicto": v["veredicto"], "total": v.get("total")})
        paso("juez_guardia", f"{v['veredicto']} ({v.get('total', '-')}/100) {v.get('consejo', '')}",
             f"{v['veredicto']} ({v.get('total', '-')}/100)")
        resumen.update(titulo=g.get("titulo"), veredicto=v["veredicto"], nota=v.get("total"), consejo=v.get("consejo"),
                       juicio=id_juicio, juicio_app=id_tribunal, segundos=round(segundos, 1), intento=intento,
                       formato=g.get("formato"))
        if v["veredicto"] == "aprobado" or a.prueba:
            break
        consejo = (f"\n- (El Juzgado ha suspendido el intento anterior, «{g.get('titulo', '')}»: {v.get('consejo', '')}. "
                   "Haz otro vídeo distinto que no tenga ese fallo.)")
        if intento < intentos:
            paso("juez_guardia", "suspendido: se tira y se hace otro con el consejo del Juzgado")
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
        paso("subidor", f"no llega a la nota que pide el dueño ({v.get('total', '-')}/100): se tira, no se sube")
        resumen["destino_resultado"] = "suspendido"
    else:
        ids = parasubir.dejar(clave, canal, video, g, segundos, v)
        cuadernos["publicador"].apuntar("para_subir", {"barrio": clave, "documentos": ids, "guion": id_guion})
        privado.apuntar_titulo(clave, g.get("titulo", ""))
        estudio_animacion.apuntar(clave, g)
        paso("publicador", f"en la bandeja «Para subir»: {', '.join(ids)}", f"en la bandeja ({len(ids)} redes)")
        resumen.update(destino_resultado="para_subir", documentos=ids)
    resumen["resultado"] = "hecho"
    return resumen


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

    def paso(robot, texto, publico=None):
        if robot in cuadernos:
            en_curso["robot"] = robot
        hora = dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%S')
        registro.append(f"[{hora}] {robot}: {texto}")
        print(privado.limpiar(f"[{hora}] {clave} · {robot}: {publico if publico is not None else texto}"), flush=True)

    resumen = {"canal": clave, "nombre": canal["nombre"], "destino": canal["destino"], "prueba": a.prueba,
               "empezado": privado.ahora()}
    try:
        fuentes, lista = None, []
        if canal.get("tipo") in CON_FUENTES and canal.get("fuentes"):
            paso("reportero_gta6", "buscando fuentes")
            fuentes, lista = reportero.fuentes(clave, canal, registro=lambda t: paso("reportero_gta6", t))
            if not fuentes:
                raise RuntimeError("el Reportero no ha encontrado ninguna fuente hoy")
            cuadernos["reportero_gta6"].apuntar("fuentes", {"canal": clave, "cuantas": len(lista)})
            paso("reportero_gta6", f"{len(lista)} fuentes")

        receta = (privado.leer(os.path.join("estado", "influencers", "recetas.json"), {}) or {}).get("canales", {}).get(clave)
        lecciones_escritor = cuadernos["escritor"].para_el_prompt()
        if receta:                               # la receta de los Influencers (y del Radar de nichos) para este canal
            lecciones_escritor += "\n- (Receta de los Influencers, de lo que funciona ahora) " + json.dumps(
                {k: v for k, v in receta.items() if k not in ("fecha", "basada_en")}, ensure_ascii=False)
        if canal.get("estudio") == "animacion":     # cuentas de vídeos animados (las del dueño): el estudio de animación
            _turno_estudio(clave, canal, cuadernos, nombres, trabajo, paso, resumen, a, lecciones_escritor)
            raise _Hecho()
        idea, id_idea = None, None
        if ajustes.get("sala_ideas", True):     # la Sala de Ideas elige la mejor de 3 antes de gastar dibujos
            paso("escritor", "proponiendo ideas a la Sala de Ideas")
            try:
                propuestas = escritor.ideas(canal, lecciones_escritor, privado.titulos_recientes(clave), fuentes)
                idea, id_idea = sala_ideas.elegir(clave, canal, propuestas, tribunal._pruebas(clave, canal))
                paso("escritor", f"la Sala de Ideas eligió «{(idea or {}).get('titulo')}» de {len(propuestas)}",
                     f"la Sala de Ideas eligió 1 de {len(propuestas)}")
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

            paso("locutor", f"grabando la voz ({canal.get('voz')})")
            asyncio.run(locutor.generar(g["narracion"], canal.get("voz", "es-MX-JorgeNeural"), canal.get("velocidad", "+10%"),
                                        "+0Hz", trabajo))
            quitado = locutor.apretar(trabajo)
            cuadernos["locutor"].apuntar("voz", {"canal": clave, "guion": id_guion, "silencio_quitado": quitado})
            paso("locutor", f"voz lista ({quitado} s de silencios quitados)")

            paso("dibujante", f"pidiendo {len(g['escenas'])} dibujos a AI Horde ({canal.get('dibujos')})")
            t0 = dt.datetime.now(dt.timezone.utc)
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
                                    ambiente=montador.musica.ambiente_de(canal))
            segundos = montador.duracion(video)
            cuadernos["montador"].apuntar("montaje", {"canal": clave, "guion": id_guion, "segundos": round(segundos, 1)})
            paso("montador", f"vídeo de {segundos:.1f} s")

            paso("juez_guardia", "juzgando el vídeo")
            v = tribunal.juzgar(video, g, canal, cuadernos["juez_guardia"].para_el_prompt(),
                                os.path.join(trabajo, f"juicio{intento}"), audio=os.path.join(trabajo, "voz.mp3"))
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
            aviso_juez = (f"\n- (Juez de guardia, sobre la versión anterior, suspendida con {v.get('total', '-')}/100) "
                          f"{v.get('consejo', '')} Fallos: {', '.join(v.get('fallos_graves') or []) or 'ninguno grave'}. "
                          "Escribe un guion distinto que lo corrija.")

        g = _coliseo(clave, canal, g, v, paso, a, resumen)
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
        resumen["resultado"] = "hecho"
    except _Hecho:
        pass
    except Exception as e:  # el turno nunca se queda a medias sin contarlo
        resumen.update(resultado="error", error=f"{type(e).__name__}: {e}", robot=nombres[en_curso["robot"]])
        cuadernos[en_curso["robot"]].apuntar("error", {"canal": clave, "error": f"{type(e).__name__}: {str(e)[:300]}"})
        paso("turno", f"ERROR {type(e).__name__}: {e}", f"ERROR {type(e).__name__}")
        detalle = traceback.format_exc()
        with open(os.path.join(trabajo, "fallo.txt"), "w", encoding="utf-8") as f:
            f.write(detalle)
        resumen["traza"] = detalle[-2000:]
        print(privado.limpiar("\n".join(detalle.strip().splitlines()[-12:])), flush=True)
    finally:
        resumen["terminado"] = privado.ahora()
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
