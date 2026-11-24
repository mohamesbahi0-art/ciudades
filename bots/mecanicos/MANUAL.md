# Manual de los Mecánicos (cómo va la fábrica y cómo se arregla)

La fábrica hace vídeos sola en GitHub: cada hora una ronda (`fabrica.py`) con varios turnos (`turno.py`): guion → Jurado
popular → voz → dibujos o clips → montaje → Juzgado (90 o más) → Coliseo → YouTube o «Para subir».

## Quién piensa
- Guiones e ideas: Claude de pago, con un tope al día repartido por horas. Jueces: Gemini gratis y Claude de reserva.
- «SinIA» = nadie contesta (cupo gastado). Es pasajero: Gemini se renueva a las 08:00 UTC y Claude a las 00:00 UTC, y
  cada hora tiene su parte. Salida: esperar. Nunca es un fallo del código.

## Fallos conocidos y su arreglo
- «faltan N dibujos de M»: el servicio gratis de dibujos (AI Horde) está caído o lento. Esperar 3 horas.
- «SinIA…»: sin cupo. Esperar a la siguiente ronda.
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
