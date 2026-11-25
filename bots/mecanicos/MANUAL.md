# Manual de los Mecánicos (cómo va la fábrica y cómo se arregla)

La fábrica hace vídeos sola en GitHub: cada hora una ronda (`fabrica.py`) con varios turnos (`turno.py`): guion → Jurado
popular → voz → dibujos o clips → montaje → Juzgado (90 o más) → Coliseo → YouTube o «Para subir».

## Quién piensa
- Guiones e ideas: Claude de pago, con un tope al día repartido por horas; si no puede, la IA gratis.
- La IA gratis es una cadena que salta sola de un eslabón al siguiente (`bots/comun/gemini.py` y `bots/comun/cadena.py`):
  Gemini de primera → su segunda fila con la misma llave (el pequeño de la familia nueva y los modelos Gemma, con mucho
  más cupo al día) → los servicios de reserva que tengan llave puesta (Groq, OpenRouter, Cloudflare). Lo que cada
  servicio dice que ya no le queda hoy se apunta en `estado/cadena.json` y no se le vuelve a llamar hasta que le toca.
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
  producción») y SambaNova (20 preguntas al día y solo «para probar»). Nunca se multiplican cuentas para tener más cupo.
- Una llave nueva: el dueño la crea y la guarda como secreto de GitHub (`GROQ_API_KEY`, `OPENROUTER_API_KEY`,
  `CLOUDFLARE_AI_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`). Ese eslabón se enciende solo. Para comprobarlo: escribir
  `peticiones/cadena.json` (turno «Probar la cadena»), que dice qué modelos del catálogo existen y contestan.
- Los modelos gratis cambian a menudo. Si «Probar la cadena» dice que falta alguno del catálogo, se cambia en
  `cadena.SERVICIOS` (la prueba enseña la lista que ofrece hoy cada servicio). Los de Google, con `peticiones/gemini.json`.
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

## Lo que un mecánico NO hace
No toca el código, no borra vídeos ni cuentas, no sube nada sin juicio, no cambia llaves ni permisos y no se salta
bloqueos de ninguna plataforma. Si duda, deja el parte para Claude.
