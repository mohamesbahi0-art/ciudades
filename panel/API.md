# El portero de la app (panel/)

La app de la fábrica vive en Cloudflare Pages (gratis), con la contraseña del dueño, y funciona sin Claude. Hay tres piezas:

- **El portero:** las Functions de este proyecto. Guarda escondida una llave de GitHub del dueño (`PANEL_GH_TOKEN`, que solo tiene permiso de «Contents» sobre `ciudades` y `ciudades-memoria`). Lee y escribe por él en los repositorios.
- **El Comisario automático:** `bots/app/comisario.py` y `.github/workflows/app.yml`, cada 15 minutos.
  - Prepara los datos que lee la app en el privado: `app/datos/todo.json` y `app/datos/juicios.json`.
  - Aplica lo que el dueño hace en la app: las entradas `entrada/*.json` del privado.
  - Hace lo mismo que hacían las rondas de Claude del Comisario (`RONDA.md` del privado).
- **La app:** `torre.html` y lo que la acompaña. Viene del repositorio privado (`app/`), y el despliegue la copia, nunca este repositorio.
  - Todo, también la app, pasa por `_middleware.js`: sin la sesión del dueño solo se ven `/entrar` y `/api/entrar`.

Nada privado en este repositorio: las direcciones de abajo no llevan nombres de cuentas. Lo privado viaja por la llave.

## Sesión

| Petición | Qué hace |
|---|---|
| `POST /api/entrar` `{clave}` | Si `clave` = `PANEL_CLAVE`, pone la cookie `sesion` (HttpOnly, Secure, SameSite=Strict, 90 días, firmada con HMAC). 10 intentos fallidos por IP y hora como mucho. |
| `POST /api/salir` | Borra la cookie. |
| `GET /api/yo` | `{dentro: true}` o 401. |

Cualquier `/api/*` sin sesión devuelve 401 `{error: "sin_sesion"}`. La app entonces manda a `/entrar`.

## Leer

| Petición | Qué devuelve |
|---|---|
| `GET /api/todo` | `{actualizado, colecciones: {<coleccion>: {<id>: {...campos}}}}`. Son las 42 colecciones de la app, menos `juicios`, tal cual las tenía la base (mismos nombres de colección, ids y campos). Va tal cual, en streaming (el portero no lo lee). Lleva `ETag` (el sha del fichero en git: solo cambia si cambia el contenido): con `If-None-Match` devuelve 304. Basta un sondeo cada 60 s. |
| `GET /api/juicios` | `{juicios: {<id>: {...}}}`: `app/datos/juicios.json` entero, en streaming y con `ETag`/304 como `/api/todo`. El Comisario automático ya lo deja en los juicios de los últimos 30 días. No admite `desde` (si llega, se ignora). |
| `GET /api/video/<nombre>` | Un vídeo o una foto de las estanterías del privado («para-subir», «videoteca», «canales»…). Redirige 302 a la descarga de GitHub, que caduca a los pocos minutos. `nombre` es el final del enlace `video`/`videoGithub`. Con `?descargar=1`, la descarga lleva el nombre del fichero. |
| `GET /api/subido/<id>` | Un vídeo que subió el dueño (lo devuelve `POST /api/subir`). Mientras sigue en la estantería «buzon-app», redirige 302 a su descarga, como `/api/video`. Cuando el Comisario automático ya lo ha pasado a su rama, devuelve el fichero de la rama tal cual, en streaming. Cuando la fábrica ha borrado la rama, 404. |
| `GET /api/turnos` | Los últimos 30 turnos de GitHub Actions: `{turnos: [{nombre, estado, resultado, empezado, terminado}]}`. Sustituye a «Constructores en directo». |

## Escribir

Todo lo que escribe el dueño va por una sola puerta:

`POST /api/escribir` `{coleccion, id, campos, crear}` → `{ok: true, entrada: "<id de la entrada>"}`

- `crear: true` sirve para un documento nuevo (charla, ordenes, propios, errores). Si no, es un «update» del documento.
- El portero solo acepta estas colecciones y estos campos. Lo demás da 400 `{error: "no_permitido"}`:

| coleccion | crear | campos que acepta |
|---|---|---|
| `charla` | sí | de (`"dueno"`), texto (≤1000), fecha, estado (`"enviado"`) |
| `ordenes` | sí / no | texto (≤600), fecha, estado (`"nueva"` al crear; `"cancelada"` al cambiar) |
| `propios` | sí | estado (`"subido"`), cuenta, tipoCuenta, titulo, texto, subido, archivo |
| `clips` | no | estado (`"grabado"`/`"por_grabar"`), grabadoEl, archivo |
| `parasubir` | no | estado (`"subido"`/`"descartado"`), subidoEl, descartadoEl, motivo (≤120) |
| `barrios` | no | cifras, cifrasPorRed, historialCifras |
| `sos` | no | decisionDueno (`"si"`/`"no"`), decididoEl |
| `avisos` | no | hecho, hechoEn |
| `errores` | sí | fecha, donde, msg, pila, vista, ua, app (cada uno ≤2000) |

- Cada escritura queda como fichero en el privado: `entrada/<AAAAMMDDhhmmss>-<4 letras>.json` = `{coleccion, id, campos, crear, fecha}`.
- Después el portero escribe `peticiones/app.json` en el público para que el Comisario automático la aplique enseguida, en 1 o 2 minutos. Mientras tanto, la app enseña el cambio ella misma.

## Subir un vídeo (Juzga mi vídeo y clips)

`POST /api/subir?para=propios|clips&codigo=<codigo>`, con el vídeo como cuerpo → `{id, url}`.

- El vídeo va con `Content-Type: video/mp4`, `video/quicktime` o `video/webm` y con `Content-Length` (sin él, 411). Tiene que pesar entre 2 KB y 15 MiB.
- El portero no lee el vídeo entero ni lo pasa a base64 (el plan gratis de Cloudflare da 10 ms de CPU). Solo mira los primeros bytes para ver que de verdad es un vídeo. Después lo pasa tal cual, en streaming, a la estantería «buzon-app» del privado, con el nombre `<para>-<codigo>.<ext>`.
  - Si ya había uno con ese `<para>-<codigo>` (en cualquier extensión), lo borra antes.
  - La estantería se crea si no existe.
- El portero no hace ramas: en su pasada, el Comisario automático lo pasa a su rama y lo quita del buzón.
  - **propios:** la rama `juicio/<codigo>` del privado, con `<codigo>.<ext>` y `peticion.json`, que el Comisario completa con la entrada de `propios`.
  - **clips:** la rama `buzon/<codigo>` del privado, con `<codigo>.<ext>`.
- Para que esa pasada llegue en 1 o 2 minutos, el portero toca `peticiones/app.json` en el público. Con propios, también `peticiones/juicio.json`.
- `id` = `<para>:<codigo>`, y `url` = `/api/subido/<id>`. La app lo guarda en `archivo.asset_id` como antes y pone `archivo.url` = `url`.
- `codigo` solo puede llevar letras, números, «-» y «_» (64 como mucho).

## Lanzar un turno

`POST /api/lanzar` `{que}`, con `que` dentro de una lista cerrada:

- `actualizar`: el Comisario automático ahora mismo;
- `cerebro`: la pasada del Cerebro;
- `juicio`: «Juzga mi vídeo».

Escribe el fichero de `peticiones/` que lo arranca. Como mucho 1 cada 2 minutos por cada `que`.
