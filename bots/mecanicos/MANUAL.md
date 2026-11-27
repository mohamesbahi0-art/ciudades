# Manual de los Mecánicos (cómo va la fábrica y cómo se arregla)

La fábrica hace vídeos sola en GitHub: cada hora una ronda (`fabrica.py`) con varios turnos (`turno.py`): guion → Jurado
popular → voz → dibujos o clips → montaje → Juzgado (90 o más) → Coliseo → YouTube o «Para subir».

## Quién piensa
- Guiones e ideas: Claude de pago, con un tope al día repartido por horas; si no puede, la IA gratis.
- La IA gratis es una cadena que salta sola de un eslabón al siguiente (`bots/comun/gemini.py` y `bots/comun/cadena.py`):
  Gemini de primera → su segunda fila con la misma llave (el pequeño de la familia nueva y los modelos Gemma, con mucho
  más cupo al día) → los servicios de reserva que tengan llave puesta (Groq y Cloudflare) → al final, los que van SIN
  llave (OVH AI Endpoints y el texto de AI Horde). Lo que cada servicio dice que ya no le queda hoy se apunta en
  `estado/cadena.json` y no se le vuelve a llamar hasta que le toca.
- Jueces: Gemini de primera; si no le queda cupo, un juez SUPLENTE (la segunda fila o la cadena) y, si tampoco, Claude.
  Un suplente puede suspender y mandar arreglar, pero su aprobado no publica nada: lo confirma un juez de primera
  (Gemini de primera o Claude) en el momento o, si no hay ninguno, el vídeo espera en la Sala de espera
  (`bots/juzgado/espera.py`, estantería «espera», `estado/espera/`) y se confirma en el siguiente turno de la cuenta.
- «SinIA» = nadie contesta (ni la cadena). Es pasajero: Gemini se renueva a las 08:00 UTC y Claude a las 00:00 UTC, y
  cada hora tiene su parte. Salida: esperar. Nunca es un fallo del código.

## La cadena de IA gratis
- Dentro solo están los servicios que dejan usarlo así (automático y para publicar) con UNA cuenta gratis y sin
  tarjeta. Fuera (mirado el 25-nov-2026): Mistral y Together (ya no hay API gratis), Cerebras (pide tarjeta), Hugging
  Face (quitó el cupo gratis), GitHub Models (cerrado), Cohere y NVIDIA (su cuenta gratis prohíbe usarlo «en
  producción»), SambaNova (20 preguntas al día y solo «para probar») y OpenRouter (ya es de pago: apagado en
  `config/fabrica.json` → `cadena.apagados`). Nunca se multiplican cuentas para tener más cupo. (La misma lista está en
  `bots/mecanicos/explorador.py` → `DESCARTADOS`: si cambia aquí, cambiarla allí.)
- Sin llave (desde el 27-nov-2026), siempre detrás de los de llave:
  · OVH AI Endpoints (`oai.endpoints.kepler.ai.cloud.ovh.net/v1`, formato OpenAI): su documentación deja usarlo sin
    cuenta con 2 peticiones por minuto por dirección y por modelo; la cadena cuenta 2 por minuto para todo el servicio y
    por máquina (`cadena.MINUTO`). Su 429 es del minuto: vuelve a los 2 minutos, no mañana.
  · AI Horde, texto (`oai.aihorde.net/v1`, en pruebas): voluntarios, anónimo con la llave de pega «0000000000» y la
    prioridad más baja; espera a que conteste un voluntario. Solo preguntas pequeñas (6.000 caracteres), respuestas
    cortas (400) y 170 s como mucho. Sus modelos cambian cada día: se usan los 2 primeros de su lista de hoy.
  · Un 401/403 de un sin llave no es «llave mala» (no hay llave que cambiar): se le aparta 6 horas.
  · Apagarlos todos: `config/fabrica.json` → `"cadena": {"sin_llave": false}`; en las pruebas sin red,
    `CADENA_SIN_LLAVE=0` (lo pone `simulacro.yml`).
- Una llave nueva: el dueño la crea y la guarda como secreto de GitHub (`GROQ_API_KEY`,
  `CLOUDFLARE_AI_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`). Ese eslabón se enciende solo. Para comprobarlo: escribir
  `peticiones/cadena.json` (turno «Probar la cadena»), que dice qué modelos del catálogo existen y contestan.
- Los modelos gratis cambian a menudo. Los pone al día solo el Explorador de IA gratis (abajo). Si «Probar la cadena»
  dice que falta alguno del catálogo, se puede cambiar también en `cadena.SERVICIOS` (la prueba enseña la lista que
  ofrece hoy cada servicio y prueba también los sin llave). Los de Google, con `peticiones/gemini.json`.

## El Explorador de IA gratis (`explorador.yml`, los lunes a las 5:41 UTC, o con `peticiones/explorador.json`)
`bots/mecanicos/explorador.py`, sin Claude y sin gastar nada:
- Pide a cada servicio de la cadena su lista oficial de modelos (Gemini, Groq, Cloudflare y, si la dan, OVH y AI Horde).
  El del catálogo que ya no sale y, al preguntarle, dice «no existe» se apaga; el que vuelve a salir, vuelve. Los nuevos
  que sirven para lo mismo (texto o ver imágenes, de 20B o más si lo dice el nombre; nada de voz, dibujos ni adultos) se
  prueban con una pregunta cortita: el que contesta bien entra detrás de los del catálogo (2 por clase y servicio). Lo
  deja en `estado/explorador/modelos.json`, que `cadena.py` aplica al leer (y `gemini.py`, solo los quitados). Los nuevos
  de Google solo los propone (`propuestos`): un juez de primera lo eligen Claude o el dueño. Nunca cambia de servicio
  ni mete uno nuevo. (Un 400/404 en plena ronda lo sigue apartando la cadena 3 horas, como siempre.)
- Lee el catálogo y la revisión de condiciones de FreeLLMAPI y la lista awesome-freellm-apis (raw.githubusercontent.com)
  y apunta en `estado/explorador/novedades.json` → `candidatos` los servicios que podrían cumplir las normas, con lo que
  haría falta (una cuenta y su llave, o nada si va sin llave). Lo que pide tarjeta o pago, solo deja probar o sus
  condiciones lo prohíben va a `descartados` con su porqué, igual que los del MANUAL. Cada novedad, una sola vez; lo
  descartado no se vuelve a proponer. Para descartar un candidato, pasarlo a `descartados` con su motivo.
- «fuente …: no contesta» o «… no deja ver su lista»: no es avería; lo apunta y sigue. Lo de la otra semana se queda.
- Un candidato NO entra solo en la cadena: hay que leer sus condiciones, que el dueño cree UNA cuenta si hace falta y
  añadirlo a `cadena.SERVICIOS` con su secreto.
- Reordenar o apagar un servicio sin tocar código: `config/fabrica.json` → `"cadena": {"orden_texto", "orden_vision",
  "apagados"}`. Vídeos por cuenta en la Sala de espera: `juzgado.espera_por_cuenta` (2).

## Fallos conocidos y su arreglo
- «faltan N dibujos de M»: el servicio gratis de dibujos (AI Horde) está caído o lento. Esperar 3 horas.
- «SinIA…»: sin cupo. Esperar a la siguiente ronda.
- «cadena: <servicio>: HTTP 401/403»: la llave de ese servicio de reserva no vale. La cadena sigue con los demás; el
  dueño tiene que poner una llave nueva: avisar_dueno. «HTTP 429»: sin cupo; se apunta sola hasta que le toca.
- Un vídeo «esperando» con «espera en la Sala de espera a que lo confirme un juez de primera»: no es un atasco. Sale
  solo cuando vuelve un juez de primera (a las 36 horas se quita).
- La ronda no arranca (GitHub se retrasa o se salta el horario): arrancarla a mano.
- Un turno falla en «Herramientas» o al sacar el repositorio: fallo de GitHub; repetirlo una vez.
  (Si es «packages.microsoft.com … 403 Forbidden» al hacer apt-get update: es un almacén ajeno de la máquina de
  GitHub; desde el 27 nov los turnos siguen sin él, `apt-get update || true`.)
- «permiso», «invalid_grant», «unauthorized» en la subida a YouTube: el permiso del canal ha caducado. Solo lo arregla
  el dueño (pulsar «Permitir»): avisar_dueno.
- «quotaExceeded», «uploadLimitExceeded»: tope de YouTube por hoy. Esperar.
- «ElevenLabs dice 401» o «403»: la llave de ElevenLabs de GitHub no vale (mal copiada o con permisos
  restringidos). Los vídeos salen con la voz gratis. Solo lo arregla el dueño: llave nueva sin restricciones. avisar_dueno.
- «credit», «billing», «saldo»: la cuenta de Claude sin saldo. avisar_dueno.
- «KeyError», «TypeError», «ValueError», «AttributeError», «IndexError», «JSONDecodeError» repetidos en un canal: fallo
  de código o de formato. descansar_canal y para_claude.
- Un vídeo colgado más de 3 horas en «Ahora en la fábrica»: la ronda se cortó. Limpiarlo.
- Notas bajas (menos de 90): no es una avería; el Juzgado manda. Los formatos que no pasan de 80 descansan solos.

## El Investigador de webs (`capturas.yml`, 7:21 y 19:21 UTC)
Saca los datos públicos de una web sin API con reverse-api-engineer y un modelo GRATIS de OpenCode, dentro de una caja
desechable (`herramientas/caja_capturas/`: `turno.py` en la máquina de GitHub, `caja.py` dentro del contenedor). Sin
llaves, navegador nuevo sin sesiones, red solo por el filtro (squid) y 2 capturas al día y 5 a la semana. En el registro
público solo salen «cap-N» y cifras; el detalle de un fallo del programa va a `estado/capturas/fallo_turno.json` (privado).
Lo que no es avería (sale en verde y no se toca):
- «sin_modelo_gratis»: hoy OpenCode no tiene ningún modelo con coste 0 (o «no serving provider»). Esperar: el pedido se
  repite otro día. Si dura más de 3 días, mirarlo con la prueba (`peticiones/capturas.json` con `{"probar": true}`).
  NUNCA poner una llave de OpenCode ni de nadie para arreglarlo.
- «vetada · captcha / cloudflare / datadome / perimeterx / bloqueo_401 / bloqueo_403 / bloqueo_429»: la web no quiere
  robots. No se insiste: el dominio queda fuera 30 días (a la segunda, para siempre).
- «vetada · web_prohibida»: el navegador intentó ir a una red o a una página de entrar; el filtro lo cortó y la captura
  se tira. Si se repite con la misma web, dejarla.
- «fallida · pide_sesion, clave_dentro, disfraz, otro_dominio, import_prohibido, llamada_prohibida, programa_roto,
  cliente_grande, cliente_enlace»: el programa que escribió la IA no pasa la revisión y no se ejecuta. Normal con un
  modelo gratis; el pedido no se repite solo.
- «fallida · sin_datos» (el programa no sacó nada), «sin_har» (no quedó grabación), «sin_cliente» (rae no lo escribió):
  la web no se dejó o el modelo no supo. «colgada»: rae pasó de 20 min y se cortó.
- «fallida · sin_coste» (rae no dijo cuánto costó) y «de_pago» (costó más de 0 $): se tira todo; con «de_pago» el modelo
  queda vetado para siempre en la cola. Avisar a Claude (para_claude) una vez.
Lo que sí es avería (el turno sale en ROJO): para_claude siempre, sin repetir a ciegas.
- «filtro_roto»: la caja podía salir por donde no debía (sin el filtro, DNS de fuera o el filtro dejó pasar una prueba
  prohibida). No se ha capturado nada. Mirar `turno.py` (cortafuegos, redes) y `filtro.conf`.
- «filtro_caido»: el filtro no contestaba a la caja. Repetir una vez; si sigue, para_claude.
- «llave_en_la_caja»: alguien ha metido una variable con llave (…_KEY, …_TOKEN, …_SECRET, OPENCODE_…) donde no debe.
  Quitarla de `capturas.yml`/`Dockerfile`: la caja no lleva ninguna. «proveedor_extra»: OpenCode ve conectado otro
  proveedor además del gratis (eso solo pasa con una llave): lo mismo, buscarla y quitarla.
- «error_caja» o «caja_sin_resultado»: el programa de la caja se rompió o el contenedor murió (memoria, tiempo).
- «opencode_no_arranca» / «opencode_no_para»: OpenCode no arranca sin npm (la caché de npx de la imagen) o no se apagó.
  Repetir una vez; si sigue, revisar en el `Dockerfile` las versiones fijas (opencode-ai@1.18.31,
  rae-playwright-mcp@0.0.9) y el calentado de npx.
- «no he podido preparar la imagen…»: falló `docker build` (red de GitHub, o Google cambió su Chrome). Repetir una vez.
  Las demás versiones están fijadas con su huella (`rae.lock`, `cliente.lock`, Node): no se cambian sin probar.
- «capturas.py elegir/guardar ha fallado»: fallo de `bots/cerebro/capturas.py`; el detalle, en `fallo_turno.json`.
- Ya arreglados en las primeras pruebas de verdad (27 nov), por si vuelven tras un cambio de squid o de Playwright:
  · «no he podido preparar el filtro» con squid funcionando: squid con ssl-bump escribe «Accepting SSL bumped HTTP
    Socket connections», no «Accepting HTTP Socket connections» (`turno.FILTRO_LISTO` acepta las dos).
  · «filtro_roto» con el filtro bien: con ssl-bump squid contesta «200» también a lo que corta y enseña su 403 dentro
    del túnel; `caja._connect` mira dentro, solo si contesta el propio filtro (su certificado «caja»).
  · Chrome no arranca en la caja: Playwright MCP solo lee `PLAYWRIGHT_MCP_SANDBOX=false` (no `…_NO_SANDBOX`).
  · Clientes buenos tirados por «llamada_prohibida» o «clave_dentro»: un HTMLParser propio (`__init__` vale) y las
    rutas largas de la web (la «/» no cuenta como parte de una llave).
  Así quedó bien la primera captura (web de práctica: 20 filas, 0 $, minuto y medio).
Nunca: quitar el filtro o el cortafuegos, dar llaves o secretos a la caja, guardar el HAR, las cookies o los registros de
rae, subir artefactos, imprimir la web en el registro ni subir los topes sin que lo pida el dueño.

## Lo que un mecánico NO hace
No toca el código, no borra vídeos ni cuentas, no sube nada sin juicio, no cambia llaves ni permisos y no se salta
bloqueos de ninguna plataforma. Si duda, deja el parte para Claude.
