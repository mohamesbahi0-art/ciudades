"""Simulacro del Comisario automático (sin red ni secretos): una copia de pruebas/privado_ejemplo con un «origin» de
mentira (un repositorio git en una carpeta), las entradas que deja el portero de la app de cada tipo, las que no están
permitidas, la foto con sus colecciones y campos, lo del dueño que manda y el viaje charla → buzón → respuesta.

    python pruebas/simulacro_comisario.py
"""
import contextlib
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="simulacro-comisario-")
PRIV = os.path.join(TMP, "privado")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIV, ignore=shutil.ignore_patterns("trabajo"))
os.environ["PRIVADO"] = PRIV
os.environ["MEMORIA_DIR"] = os.path.join(PRIV, "memoria")
SALIDA = os.path.join(TMP, "github_output")
os.environ["GITHUB_OUTPUT"] = SALIDA

from bots.app import comisario  # noqa: E402
from bots.comun import privado  # noqa: E402

AHORA = dt.datetime.now(dt.timezone.utc)
iso = lambda horas=0: (AHORA - dt.timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
BARRIO, NOMBRE = "barrio.prueba", "Barrio de prueba"       # en la config de ejemplo: alias barrio-1
REGISTRO = []


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


def poner(rel, datos):
    privado.escribir(rel, datos)


def git(*args, donde=PRIV, entrada=None):
    return subprocess.run(["git", "-C", donde, *args], capture_output=True, text=True, input=entrada)


def pasada():
    """Una pasada del Comisario; lo que imprime (lo que saldría en el registro público) se guarda para mirarlo."""
    if os.path.exists(SALIDA):
        os.remove(SALIDA)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        comisario.main([])
    REGISTRO.append(buf.getvalue())
    return privado.leer(comisario.TODO, {})["colecciones"]


n_entrada = [0]


def entrada(coleccion, id_, campos, crear=False, horas=0):
    n_entrada[0] += 1
    nombre = (AHORA - dt.timedelta(hours=horas)).strftime("%Y%m%d%H%M%S") + f"-{n_entrada[0]:04d}.json"
    poner(os.path.join("entrada", nombre), {"coleccion": coleccion, "id": id_, "campos": campos, "crear": crear,
                                             "fecha": iso(horas)})
    return nombre


# ---------------------------------------------------------------- el privado de mentira, con su «origin»
ORIGEN = os.path.join(TMP, "origen.git")
subprocess.run(["git", "init", "-q", "--bare", ORIGEN], check=True)
git("init", "-q", "-b", "main")
git("config", "user.name", "prueba")
git("config", "user.email", "prueba@example.invalid")
git("remote", "add", "origin", ORIGEN)

poner("manifiesto.json", {
    "ciudades": [{"id": "central", "nombre": "Ciudad Central", "numero": 1}, {"id": "coliseo", "nombre": "El Coliseo", "numero": 6}],
    "canales": [{"clave": "gta", "nombre": "Canal de noticias de prueba", "red": "youtube", "id": "UCxxxxxxxxxxxxxxxxxxxxxx"}],
    "barrios": [{"cuenta": BARRIO, "red": "instagram", "redes": ["instagram", "tiktok"], "nombre": NOMBRE}],
    "bots": [{"id": "escritor", "nombre": "Escritor", "ciudad": "central", "reconstruido": True},
             {"id": "subidor", "nombre": "Subidor", "ciudad": "central", "reconstruido": True},
             {"id": "jefe_taller", "nombre": "Jefe del taller", "ciudad": "taller"},
             {"id": "nuevo_sin_cuaderno", "nombre": "Nuevo", "ciudad": "central"}],
    "skills": [{"id": "ciudades", "nombre": "ciudades", "estado": "instalada"}],
    "plugins_recomendados": [{"nombre": "GitHub", "estado": "por_instalar"}]})
poner("app/base/fichas.json", {"escritor": {"color": "#fff", "frase": "¡Escribo!"}})
poner("app/base/robots.json", {"escritor": {"nombre": "Escritor", "estado": "parado", "detalle": "viejo", "orden": 1}})
poner("app/base/ayuda.json", {"viaje": {"pasos": [{"paso": 1, "que": "algo"}]}, "claude": {"viejo": True}})
poner("app/base/avisos.json", {"mision-1": {"tipo": "mision", "titulo": "Haz algo", "hecho": False, "fecha": iso(50)}})
poner("app/base/skills.json", {"ciudades": {"nombre": "ciudades", "estado": "instalada"}})
poner("config/fabrica.json", dict(privado.leer("config/fabrica.json", {}) or {},
                                  claude={"mes_usd": 100, "dia_max_usd": 10, "renueva_dia": 5}))
poner("estado/claude.json", {"resumen": {"mes_usd": 12.5, "hoy_usd": 1.2, "tope_hoy_usd": 3.4}, "actualizado": iso(1)})
poner("estado/central/gta.json", {"turnos": [
    {"empezado": iso(30), "titulo": "Un vídeo viejo", "resultado": "hecho", "destino_resultado": "subido", "nota": 91},
    {"empezado": iso(2), "terminado": iso(1.9), "titulo": "Un vídeo nuevo", "resultado": "hecho",
     "destino_resultado": "subido", "nota": 93},
    {"empezado": iso(1), "titulo": "Una prueba", "resultado": "error", "prueba": True}]})
poner(f"estado/central/{BARRIO}.json", {"turnos": [
    {"empezado": iso(3), "titulo": "Vídeo de la cuenta", "resultado": "hecho", "destino_resultado": "para_subir", "nota": 90}]})
poner("estado/canales/gta.json", {"suscriptores": 10, "programados24h": 1, "hasta": iso(-48),
                                  "programados": [{"titulo": "Lo que sale mañana", "sale": iso(-20), "id": "abc"}],
                                  "ultimo_publicado": {"titulo": "Ayer", "url": "https://youtu.be/x", "publicado": iso(20)}})
poner("estado/permisos.json", {"permisos": {"gta": "al_dia"}})
poner("estado/fabrica.json", {"esperan": {}})
poner("estado/mecanicos/taller.json", {"ultimo": iso(0.2), "arreglos": [{"fecha": iso(0.2), "robot": "jefe_taller",
                                       "que": "repite un turno", "detalle": "el turno de barrio-1 falló al empezar"}],
                                       "partes": [{"fecha": iso(5), "canal": "barrio-1", "causa": "falla el guion de barrio-1",
                                                   "estado": "para_claude", "para_claude": "mirar el escritor de barrio-1",
                                                   "para_el_dueno": "No tienes que hacer nada."}]})
poner("estado/coliseo/torneos/20261127-101010-barrio-1.json", {
    "canal": "barrio-1", "clave": BARRIO, "fecha": iso(4), "video": "Vídeo de la cuenta", "nota_juzgado": 92,
    "gladiadores": [{"nombre": "Máximo", "carta": "Historia", "salida": {"titulo": "Título campeón"}}],
    "combates": [{"ronda": "final", "a": "Máximo", "b": "Otro", "critica_a_b": "x", "critica_b_a": "y", "ganador": "Máximo"}],
    "campeon": {"nombre": "Máximo", "carta": "Historia", "salida": {"titulo": "Título campeón"}}})
poner("estado/coliseo/resumen.json", {"hoy": {"torneos": 1}, "por_cuenta": {"barrio-1": {"Historia": 1}}, "actualizado": iso(4)})
poner("estado/juzgado/juicios/nuevo-gta.json", {"canal": "gta", "tipo": "video", "titulo": "Un vídeo nuevo", "nota": 93,
                                                "fecha": iso(2), "sentencia": "sube", "arreglo_de": None, "version": 1})
poner("estado/juzgado/juicios/viejo-gta.json", {"canal": "gta", "tipo": "video", "titulo": "Viejo", "fecha": iso(24 * 40)})
poner("estado/juzgado/liga.json", {"jueces": {"gancho": {"nombre": "Jueza", "aciertos": 0.7, "comparaciones": 12},
                                              "reloj": {"nombre": "Juez", "aciertos": 0.5, "comparaciones": 12}}})
poner("estado/clips/para_grabar.json", {"momentos": [
    {"codigo": "C-001", "estado": "por_grabar", "video": "zzz", "nota": 95, "titulo_original": "clip"},
    {"codigo": "C-002", "estado": "por_grabar", "video": "yyy", "nota": 92}]})
poner(f"parasubir/2026-11-27-{BARRIO}-un-video-tt.json", {"barrio": BARRIO, "red": "tiktok", "titulo": "Vídeo de la cuenta",
                                                          "estado": "pendiente", "creado": iso(3),
                                                          "video": "https://example.invalid/releases/download/para-subir/v.mp4"})
poner("estado/derechos/sos.json", {"mensajes": [{"id": "sos-1", "robot": "escritor", "estado": "necesita_dueno",
                                                 "pregunta": "¿Lo cambio?", "fecha": iso(2)}]})
poner("estado/app/cifras.json", {"barrios": {BARRIO: {"cifrasPorRed": {"tiktok": {"seguidores": 100, "fecha": iso(30)}}}},
                                 "historial": {"2026-11-26": {"canales": {}}}, "actualizado": iso(1)})
poner("estado/cerebro/chat.json", {"conversacion": []})
poner("ordenes/vieja.json", {"texto": "una orden antigua", "fecha": iso(100), "estado": "hecha", "respuesta": "Hecho."})
with open(os.path.join(PRIV, "memoria", "escritor.json"), "w", encoding="utf-8") as f:
    json.dump({"robot": "escritor", "lecciones": [{"id": "a", "texto": "Lección mía", "confianza": 0.6},
                                                  {"id": "b", "texto": "Lo dijo el dueño", "confianza": 1, "del_dueno": True}],
               "diario": [{"id": "1", "fecha": iso(0.5), "accion": "guion", "detalle": {"canal": "barrio-1"}}]}, f)
git("add", "-A")
git("commit", "-q", "-m", "inicio")
git("push", "-q", "origin", "main")
git("branch", "-q", "--set-upstream-to=origin/main", "main")


# ---------------------------------------------------------------- la estantería «buzon-app» de mentira
ESTANTE = os.path.join(TMP, "buzon-app")
os.makedirs(ESTANTE)


def video(nombre, segundos):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:s=64x64:d={segundos}:r=5",
                    "-c:v", "libx264", "-preset", "ultrafast", os.path.join(ESTANTE, nombre)], check=True)


comisario.almacen.lista = lambda etiqueta: sorted(os.listdir(ESTANTE)) if etiqueta == "buzon-app" else []
comisario.almacen.bajar = lambda etiqueta, nombre, carpeta: shutil.copy(os.path.join(ESTANTE, nombre), carpeta) and \
    os.path.join(carpeta, nombre)
comisario.almacen.borrar = lambda etiqueta, nombre: os.remove(os.path.join(ESTANTE, nombre))
video("clips-C-001.mov", 5)                    # bueno
video("clips-C-002.mp4", 70)                   # demasiado largo para un clip
video("propios-P-003.mp4", 4)                  # bueno; su entrada llega después
with open(os.path.join(ESTANTE, "propios-P-004.mp4"), "w") as f:
    f.write("esto no es un vídeo")                 # no es vídeo


def rama(rama_):
    """Los ficheros de una rama del «origin» de mentira ({} si no existe)."""
    if git("fetch", "-q", "origin", f"refs/heads/{rama_}").returncode != 0:
        return {}
    return {n: (git("show", f"FETCH_HEAD:{n}").stdout if n.endswith(".json") else "vídeo")
            for n in git("ls-tree", "--name-only", "FETCH_HEAD").stdout.split()}

# ---------------------------------------------------------------- las entradas del dueño (y las que no valen)
entrada("charla", "cabc123", {"de": "dueno", "texto": f"Hola Cerebro, ¿cómo va {NOMBRE}?", "fecha": iso(0.1),
                              "estado": "enviado"}, crear=True)
entrada("ordenes", "o1", {"texto": "Haz los vídeos más cortos", "fecha": iso(0.1), "estado": "nueva"}, crear=True)
entrada("ordenes", "o2", {"texto": "Otra orden", "fecha": iso(0.1), "estado": "nueva"}, crear=True)
entrada("ordenes", "o2", {"estado": "cancelada"})
entrada("propios", "P-001", {"estado": "subido", "cuenta": "barrio-1", "titulo": "Mi vídeo \"con comillas\"",
                             "texto": "", "subido": iso(0.1), "archivo": {"asset_id": "propios:P-001", "url": "/api/subido/propios:P-001"}},
        crear=True)
entrada("propios", "P-002", {"estado": "subido", "cuenta": "gta", "subido": iso(0.1)}, crear=True)   # aún sin rama
entrada("clips", "C-001", {"estado": "grabado", "grabadoEl": iso(0.1),
                           "archivo": {"asset_id": "clips:C-001", "recorte": {"desde": 2, "hasta": 9}}})
entrada("clips", "C-002", {"estado": "grabado", "grabadoEl": iso(0.1), "archivo": {"asset_id": "clips:C-002"}})
entrada("propios", "P-004", {"estado": "subido", "cuenta": "gta", "subido": iso(0.1)}, crear=True)
entrada("parasubir", f"2026-11-27-{BARRIO}-un-video-tt", {"estado": "subido", "subidoEl": iso(0.1)})
entrada("barrios", BARRIO, {"cifrasPorRed": {"instagram": {"seguidores": 55, "fecha": iso(0.1)},
                                             "tiktok": {"seguidores": 120, "fecha": iso(0.1)}}})
entrada("sos", "sos-1", {"decisionDueno": "si", "decididoEl": iso(0.1)})
entrada("avisos", "mision-1", {"hecho": True, "hechoEn": iso(0.1)})
entrada("errores", "e1", {"fecha": iso(0.1), "donde": "inicio", "msg": "TypeError: x"}, crear=True)
malas = [entrada("robots", "escritor", {"estado": "trabaja"}),                       # colección no permitida
         entrada("parasubir", "x", {"estado": "subido", "video": "otro"}),            # campo no permitido
         entrada("charla", "c2", {"de": "dueno", "texto": "hola"}, crear=False),      # charla sin crear
         entrada("sos", "sos-1", {"decisionDueno": "quizas"}),                        # valor no permitido
         entrada("parasubir", "../config/canales", {"estado": "subido"}),             # id raro
         entrada("ordenes", "o3", {"texto": "x" * 700, "estado": "nueva"}, crear=True),  # demasiado largo
         entrada("charla", "c3", {"texto": "hola", "de": "otro"}, crear=True)]        # no es el dueño
with open(os.path.join(PRIV, "entrada", "99999999999999-roto.json"), "w") as f:
    f.write("{no es json")

col = pasada()

# ---------------------------------------------------------------- lo que ha aplicado
hechas = {f: privado.leer(os.path.join("entrada", "hechas", f)) for f in os.listdir(os.path.join(PRIV, "entrada", "hechas"))}
quedan = [f for f in os.listdir(os.path.join(PRIV, "entrada")) if f.endswith(".json")]
comprobar(all(hechas[m]["resultado"] == "rechazada" for m in malas) and
          hechas["99999999999999-roto.json"]["resultado"] == "rechazada", "las entradas no permitidas se rechazan")
comprobar(len(quedan) == 2, "quedan esperando las de los vídeos que aún no han llegado (P-001 y P-002)")
buzon = privado.leer("estado/cerebro/buzon.json")["mensajes"]
comprobar([m["id"] for m in buzon] == ["cabc123", "orden-o1"], "charla y orden nueva al buzón del Cerebro; la cancelada fuera")
comprobar(privado.leer("ordenes/o1.json")["estado"] == "leida" and privado.leer("ordenes/o2.json")["estado"] == "cancelada",
          "órdenes guardadas en ordenes/ (leída y cancelada)")
comprobar(not os.listdir(ESTANTE), "buzón de la app: todos los archivos borrados de la estantería")
comprobar(set(rama("buzon/C-001")) == {"C-001.mov"}, "clip bueno: a su rama buzon/C-001")
comprobar(rama("buzon/C-002") == {} and rama("juicio/P-004") == {}, "clip demasiado largo y «no es vídeo»: sin rama")
comprobar(set(rama("juicio/P-003")) == {"P-003.mp4"}, "vídeo antes que su entrada: la rama con el vídeo solo")
comprobar(rama("juicio/P-001") == {}, "entrada antes que su vídeo: espera, sin rama")
m = {x["codigo"]: x for x in privado.leer("estado/clips/para_grabar.json")["momentos"]}
comprobar(m["C-001"]["estado"] == "grabado" and m["C-001"]["archivo"] == "C-001.mov" and m["C-001"]["rama"] == "buzon/C-001"
          and m["C-001"]["corte"] == {"desde": 2, "hasta": 9}, "clip grabado: archivo, rama y corte en para_grabar.json")
comprobar(privado.leer(f"parasubir/2026-11-27-{BARRIO}-un-video-tt.json")["estado"] == "subido", "Para subir: marcado subido")
cif = privado.leer("estado/redes/cifras.json")[BARRIO]
comprobar(cif["cifrasPorRed"]["instagram"]["seguidores"] == 55, "cifras del dueño en estado/redes/cifras.json")
comprobar(privado.leer("estado/derechos/sos.json")["mensajes"][0]["decisionDueno"] == "si", "la decisión del dueño en sos.json")
comprobar(len(privado.leer("estado/app/errores.json")["errores"]) == 1, "el error de la app guardado")
comprobar(set(open(SALIDA).read().split("=", 1)[1].split()) == {"cerebro"}, "arranca el Cerebro")

# ---------------------------------------------------------------- la foto
comprobar(set(comisario.COLECCIONES) - {"juicios"} <= set(col), "la foto tiene las 41 colecciones (más juicios.json)")
comprobar(col["charla"]["cabc123"]["estado"] == "leido", "charla: el mensaje queda «leído»")
comprobar(col["ordenes"]["o1"]["estado"] == "leida" and col["ordenes"]["o2"]["estado"] == "cancelada"
          and "vieja" in col["ordenes"], "órdenes en la app")
comprobar(col["propios"]["P-001"]["estado"] == "subido" and col["propios"]["P-001"]["archivo"]["asset_id"],
          "Juzga mi vídeo: subido, esperando su vídeo")
comprobar(col["propios"]["P-004"]["estado"] == "rechazado" and col["propios"]["P-004"]["problema"] == "No es un vídeo.",
          "Juzga mi vídeo: «no es un vídeo» → rechazado, aunque su entrada llegue")
comprobar(col["clips"]["C-002"]["estado"] == "por_grabar" and "70 segundos" in col["clips"]["C-002"]["problema"]
          and not col["clips"]["C-002"].get("enBuzon"), "clip demasiado largo: por grabar, con su problema")
comprobar(col["clips"]["C-001"].get("enBuzon") is True and "video" not in col["clips"]["C-001"], "clip en el buzón")
p = col["parasubir"][f"2026-11-27-{BARRIO}-un-video-tt"]
comprobar(p["estado"] == "subido" and p["videoGithub"] and p["videoNombre"] == "v.mp4", "Para subir con su vídeo de GitHub")
b = col["barrios"][BARRIO]
comprobar(b["cifrasPorRed"]["tiktok"]["seguidores"] == 120 and b["estado"] == "trabaja", "barrio: la cifra de hoy del dueño manda")
comprobar(col["canales"]["gta"]["estado"] == "trabaja" and col["canales"]["gta"]["videosProgramados"] == 1,
          "canal: trabaja (la prueba que falló no cuenta)")
comprobar(col["robots"]["escritor"]["estado"] == "trabaja" and col["robots"]["escritor"]["orden"] == 1 and
          col["robots"]["escritor"]["porCanal"].get(BARRIO), "robots: lo vivo pisa lo de la base, y su sitio se queda")
comprobar(col["robots"]["jefe_taller"]["estado"] == "trabaja", "robots: el taller trabaja (sin cuaderno)")
comprobar(col["robots"]["nuevo_sin_cuaderno"]["estado"] == "parado", "robots: el que nunca trabajó, parado")
comprobar(col["fichas"]["escritor"]["frase"] == "¡Escribo!" and col["skills"]["ciudades"], "fichas y skills de la base")
comprobar(col["ayuda"]["claude"]["gastado"] == 12.5 and col["ayuda"]["claude"]["presupuesto"] == 100 and
          col["ayuda"]["claude"]["renueva"] and col["ayuda"]["viaje"], "ayuda: la tarjeta de Claude rehecha y las de la base")
comprobar(col["avisos"]["mision-1"]["hecho"] is True, "avisos: lo que marca el dueño manda")
comprobar("para-claude" in col["avisos"] and privado.leer("estado/app/para_claude.json")["pendientes"],
          "lo que solo hace Claude: aviso en la app y estado/app/para_claude.json")
t = json.dumps(col["taller"], ensure_ascii=False)
comprobar(NOMBRE in t and "barrio-1" not in t and "lo pasa a Claude" not in json.dumps(col["taller"]["resumen"]["partes"][0]["estado"]),
          "taller en sencillo: el alias cambiado por el nombre de la cuenta; los estados, tal cual")
comprobar(col["taller"]["resumen"]["partes"][0]["canal"] == BARRIO, "el campo canal lleva la clave, no el nombre")
comprobar(NOMBRE in col["coliseo"]["resumen"]["porCuenta"] and "20261127-101010-barrio-1" in col["coliseo"],
          "coliseo: cuentas con su nombre, ids de torneo intactos")
comprobar(any("Para subir" in d["texto"] for d in col["diario"].values()) and
          not any("Una prueba" in d["texto"] for d in col["diario"].values()), "diario de los turnos (sin las pruebas)")
comprobar(col["obras"]["_meta"] is not None and col["liga"]["gancho"]["puesto"] == "mayor", "obras/_meta y la Liga")
comprobar(col["memoria"]["escritor"]["lecciones"][0]["del_dueno"] is True, "memoria: primero lo del dueño")
comprobar(col["calendario"]["proximos"]["items"][0]["titulo"] == "Lo que sale mañana", "calendario: lo próximo que sale")
j = privado.leer(comisario.JUICIOS)["juicios"]
comprobar("nuevo-gta" in j and "viejo-gta" not in j, "juicios.json: los de 30 días")

# ---------------------------------------------------------------- llegan el vídeo que faltaba y la entrada que faltaba
video("propios-P-001.mp4", 3)
entrada("propios", "P-003", {"estado": "subido", "cuenta": "gta", "titulo": "El tres", "subido": iso(0)}, crear=True)
col = pasada()
r1, r3 = rama("juicio/P-001"), rama("juicio/P-003")
pet = json.loads(r1.get("peticion.json") or "{}")
comprobar("P-001.mp4" in r1 and pet.get("cuenta") == "barrio-1" and pet.get("titulo") == "Mi vídeo \"con comillas\"",
          "entrada antes que el vídeo: la rama sale con el vídeo y su peticion.json completa")
comprobar("P-003.mp4" in r3 and json.loads(r3.get("peticion.json") or "{}").get("titulo") == "El tres",
          "vídeo antes que la entrada: la entrada completa la petición en la rama")
comprobar(col["propios"]["P-001"]["estado"] == "en_juzgado" and col["propios"]["P-003"]["estado"] == "en_juzgado"
          and "ventanilla" in open(SALIDA).read(), "los dos al Juzgado y arranca «Juzga mi vídeo»")
comprobar(not os.listdir(ESTANTE), "la estantería vacía otra vez")

# ---------------------------------------------------------------- lo del dueño manda y la respuesta del Cerebro
poner(f"parasubir/2026-11-27-{BARRIO}-un-video-tt.json", {"barrio": BARRIO, "estado": "pendiente", "titulo": "x"})
poner("estado/cerebro/chat.json", {"conversacion": [
    {"id": "cabc123", "de": "dueño", "texto": "Hola", "fecha": iso(0.1)},
    {"id": "cabc123-r", "de": "cerebro", "responde_a": "cabc123", "fecha": iso(0.05), "texto": "Va bien.",
     "acciones": ["plan nuevo para gta"]},
    {"id": "orden-o1-r", "de": "cerebro", "responde_a": "orden-o1", "fecha": iso(0.05), "texto": "Apuntado.",
     "acciones": ["orden apuntada para todas las cuentas"]}]})
poner("estado/propios/P-001.json", {"codigo": "P-001", "estado": "aprobado", "nota": 93, "minimo": 85, "lo_bueno": "el gancho",
                                    "coliseo": {"torneo": "t1", "campeon": "Máximo", "titulo": "Campeón"}})
antes = open(os.path.join(PRIV, comisario.TODO)).read()
col = pasada()
comprobar(col["parasubir"][f"2026-11-27-{BARRIO}-un-video-tt"]["estado"] == "subido",
          "lo del dueño manda aunque un robot reescriba el fichero")
c = col["charla"]["cabc123"]
comprobar(c["estado"] == "contestado" and c["respuesta"].endswith("Hecho: plan nuevo para gta") and c["respondido"],
          "charla → buzón → respuesta del Cerebro, con «Hecho:»")
comprobar(col["ordenes"]["o1"]["estado"] == "hecha" and privado.leer("ordenes/o1.json")["estado"] == "hecha",
          "la orden contestada queda hecha (en la app y en ordenes/)")
pr = col["propios"]["P-001"]
comprobar(pr["estado"] == "aprobado" and pr["loBueno"] == "el gancho" and pr["coliseo"]["campeon"] == "Máximo"
          and pr["archivo"]["asset_id"], "Juzga mi vídeo: el resultado, sin tocar el archivo del dueño")
comprobar(not os.path.exists(SALIDA) or "cerebro" not in open(SALIDA).read(), "sin mensajes nuevos no arranca al Cerebro")
pasada()
comprobar(open(os.path.join(PRIV, comisario.TODO)).read() != antes, "la foto cambia cuando cambia algo")
quieto = open(os.path.join(PRIV, comisario.TODO)).read()
pasada()
distintas = [k for k, v in json.loads(quieto)["colecciones"].items() if privado.leer(comisario.TODO)["colecciones"].get(k) != v]
comprobar(not distintas, "sin cambios no se reescribe la foto" + (f" (cambian: {', '.join(distintas)})" if distintas else ""))

# ---------------------------------------------------------------- el registro público
todo = "\n".join(REGISTRO)
comprobar(not any(x in todo for x in (BARRIO, NOMBRE, "Hola", "Vídeo de la cuenta", "barrio-1", "comillas")),
          "en lo que se imprime no sale ninguna cuenta, título ni texto del dueño")
print("simulacro del Comisario automático: todo bien")
shutil.rmtree(TMP, ignore_errors=True)
