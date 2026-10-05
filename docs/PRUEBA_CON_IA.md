# Probar Appresso Food con una IA

## Antes de empezar (lo haces tú, 1 minuto)

1. Abre **Docker Desktop** y arranca MongoDB:
   ```powershell
   docker start appresso-mongo
   ```
2. Arranca la app:
   ```powershell
   cd C:\Users\SebasDeveloper\Documents\Appresso-Cafe
   .\venv\Scripts\python.exe -m uvicorn appresso_food.app:app --host 0.0.0.0 --port 8000
   ```
3. Comprueba que `http://localhost:8000/api/health` responde `{"mongodb":"ok",...}`.
4. (Opcional) Deja la base limpia: `.\venv\Scripts\python.exe tests\e2e_fraud_http.py --clean`

## Qué IA usar

Necesita **controlar un navegador** (abrir páginas, escribir, hacer clic, leer la pantalla):

- **Claude Code / app de escritorio de Claude** con el navegador integrado: pega el prompt tal cual.
- **Claude en Chrome** (extensión): abre `http://localhost:8000/transacciones` y pega el prompt.
- Cualquier otro agente con navegador. Debe correr en **tu** equipo para ver `localhost`.

Para probar solo la API, sin IA: `python tests\prueba_profesor.py` (con la configuración por defecto).
`python tests\e2e_fraud_http.py` exige el modo estricto (`APPRESSO_REJECTED_AS_201=false` y `APPRESSO_LENIENT_INPUTS=false`).

## Prompt para pegar

```text
Eres un tester de QA. Prueba COMPLETAMENTE la aplicación "Appresso Food" que corre en
http://localhost:8000. NO modifiques el código ni borres archivos: solo usa la app como un
usuario y reporta.

Contexto: la app detecta anomalías en transacciones de compra. Regla principal: 3 o más
transacciones del MISMO usuario (identificado por el correo) dentro de una ventana deslizante
de 10 segundos = POSSIBLE_FRAUD. Cada usuario tiene su propia ventana. Hay una segunda capa por
franja horaria (mañana 05:00:01-12:00:00 límite 10, tarde 12:00:01-20:00:00 límite 6, noche
20:00:01-05:00:00 límite 3 ventas por usuario; se marca al SUPERAR el límite).

Páginas: formulario http://localhost:8000/transacciones, dashboard
http://localhost:8000/antifraude. En el formulario hay: "Usar la hora actual al enviar"
(desactívalo para fijar fechas a mano), "Modo prueba" (envía aunque el navegador detecte
errores), el panel "Ráfaga" y el panel "JSON crudo y casos de prueba" con casos precargados.

Usa un correo DISTINTO y nuevo para cada caso, salvo donde se indique lo contrario, para que
unas pruebas no contaminen a otras. Para cada caso anota: lo que hiciste, el resultado real y
si coincide con lo esperado.

CASOS
1. Transacción correcta (formulario, valores por defecto). Esperado: estado VALID, HTTP 201,
   hash de 64 caracteres hexadecimales, ventana 1 de 3.
2. Campo null (caso precargado "2. Campo null"). Esperado: REJECTED, motivo NULL_FIELD.
3. Campo vacío (caso 3). Esperado: REJECTED, EMPTY_FIELD.
4. Correo inválido: con el formulario normal sin "Modo prueba", escribe "sin-arroba": debe
   bloquearse en el navegador con un mensaje. Luego marca "Modo prueba" y envía: el backend
   debe responder REJECTED, INVALID_EMAIL.
5. Tipo incorrecto (caso 5). Esperado: REJECTED, INVALID_TYPE.
6. Número como texto: caso 6 ("50000") -> VALID, se normaliza. Caso 6b ("abc") -> REJECTED,
   INVALID_VALUE (nunca debe aceptarse como 0). Prueba también "-5", "0" y "50.000,00": todos
   deben dar INVALID_VALUE.
7. ID duplicado: envía una transacción válida y vuelve a enviar el MISMO ID (caso 7). Esperado:
   HTTP 409, DUPLICATE_TRANSACTION; la primera sigue VALID.
8. Tres transacciones en 10 s: panel Ráfaga con un correo nuevo, cantidad 4, pausa 400 ms.
   Esperado: 1ª VALID (1/3), 2ª VALID (2/3), 3ª SUSPICIOUS POSSIBLE_FRAUD (3/3, nivel MEDIO),
   4ª SUSPICIOUS (4/3, nivel ALTO).
8b. Transacciones espaciadas: en JSON crudo, mismo usuario nuevo, fechas 2026-09-23T10:00:01,
   10:00:05 y 10:00:12 (sin hora automática). Esperado: las tres VALID; la última deja 2 en
   la ventana.
8c. Ventana deslizante real: mismo usuario, fechas 10:00:08, 10:00:09 y 10:00:11 (mismo día).
   Esperado: la 3ª es SUSPICIOUS (3 transacciones en 3 s, aunque cruzan un múltiplo de 10 s).
9. Usuarios distintos: tres correos diferentes con fechas 10:00:01, 10:00:02 y 10:00:03.
   Esperado: las tres VALID, 1/3 cada una; en el dashboard, tres ventanas separadas.
10. Salida de la ventana: un usuario nuevo con fechas 10:00:00, 10:00:03 y 10:00:14 (en ese
   orden). Esperado: al enviar la 3ª, la respuesta lista las 2 anteriores como "salieron" y la
   ventana queda en 1; en el dashboard la ventana activa de ese usuario muestra 1 punto; el
   historial de transacciones sigue mostrando las 3; en Logs aparecen eventos VENTANA_SALE.
11. Hash: caso 11 -> REJECTED, HASH_MISMATCH. Luego, en el formulario con datos válidos, pulsa
   "Calcular" (hash) y envía: VALID con hash_origen CLIENTE_VERIFICADO. Pulsa "Verificar
   integridad del hash guardado": debe decir que la integridad es correcta. Prueba un hash
   escrito a mano "abc": INVALID_HASH_FORMAT.
12. Bot: ráfaga de 10 con pausa 100 ms. Esperado: desde la 3ª todas SUSPICIOUS; el dashboard
   debe mostrar más anomalías y el usuario como recurrente.
13. JSON mal formado (caso "JSON mal formado"). Esperado: HTTP 400, MALFORMED_JSON, y la
   transacción queda guardada como REJECTED en el historial.
14. Segunda capa por horario: con un usuario nuevo y fechas de hoy entre las 21:00 y las 23:00
   (franja NOCHE, límite 3) separadas por minutos, envía 4. Esperado: la 4ª SUSPICIOUS con
   motivo TOO_MANY_TRANSACTIONS y mensaje que menciona la regla por horario. Envía otras 4 un
   día con hora de mañana (10:00 a 10:10): las 4 deben ser VALID (límite 10).
15. Dashboard (http://localhost:8000/antifraude), con todos los datos anteriores:
   - Los totales de Hoy / Semana / Mes y las pestañas del Resumen cambian el contenido.
   - Hay: total de anomalías, % con anomalías, usuarios afectados, valor sospechoso, promedio
     por usuario, anomalías nuevas/abiertas/revisadas/descartadas, evolución temporal, mapa de
     calor por hora, métodos de pago, niveles, casos y usuarios recurrentes, tendencias.
   - La ventana deslizante se actualiza sola (envía una transacción desde otra pestaña y
     compruébalo sin recargar).
   - En la tabla de anomalías cambia el estado de una a ABIERTA y de otra a DESCARTADA: los
     contadores del Resumen deben actualizarse en pocos segundos.
   - "Línea de tiempo" muestra las transacciones de la anomalía con sus segundos de diferencia.
   - Los filtros por estado (anomalías e historial) funcionan; "Verificar" en una transacción
     del historial responde que coincide.
   - Revisa que no haya errores en la consola del navegador.
16. Funcionalidad anterior (no debe haberse roto): abre / , /cocina, /dashboard y /laboratorio;
   haz un pedido normal en / y confirma que aparece en /cocina.
17. Responsive: repite una carga de /transacciones y /antifraude con ancho de móvil (375 px):
   no debe haber scroll horizontal de la página (las tablas pueden desplazarse por dentro).

OPCIONAL (solo si puedes ejecutar comandos): detener y reiniciar MongoDB con
`docker stop appresso-mongo` y luego `docker start appresso-mongo`. Con Mongo detenido,
/transacciones debe mostrar un aviso rojo y POST /api/transactions debe responder 503; al
reiniciarlo, la app debe volver a funcionar sin reiniciarla.

ENTREGA un informe con:
- Una tabla: caso | acción | resultado esperado | resultado real | OK/FALLA.
- Para cada FALLA: pasos exactos para reproducirla, y captura o texto de la respuesta.
- Problemas de usabilidad o confusión que notes aunque no sean fallas.
- Un resumen final: cuántos casos pasaron, cuántos fallaron y los 3 hallazgos más importantes.
```

## Después de la prueba

- Para borrar los datos que generó la IA: `.\venv\Scripts\python.exe tests\e2e_fraud_http.py --clean`
- Reinicia la app después de limpiar, porque la ventana activa vive en memoria.
