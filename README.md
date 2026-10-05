# Appresso Food

Evolución de **Appresso Café** hacia un sistema de gestión para un restaurante
de comida rápida. Reutiliza la base de datos, los algoritmos y la
arquitectura del proyecto anterior (FastAPI + SQLite + Jinja2), pero cambia
por completo el dominio: ahora gestiona pedidos de comida rápida por dos
canales (local y domicilio), calcula rutas de entrega con un grafo de
barrios y prioriza despachos con un heap.

## Estado actual

Lo que se pidió y qué tiene hoy la app. Todo lo marcado ✅ está implementado y
probado (83 pruebas unitarias, 31 de punta a punta contra MongoDB real y 46 comprobaciones
desde afuera con `tests/prueba_profesor.py`).

### Módulo de transacciones y detección de anomalías

Pedido a partir del PDF *Técnicas de resolución de problemas en desarrollo de software*.

| Requisito | Estado | Dónde |
|---|---|---|
| Formulario web para enviar transacciones (ID, cliente, cédula, correo, fecha y hora, valor, método de pago) | ✅ | `/transacciones` |
| Validaciones en frontend **y** backend (null, vacíos, tipos, correo, cédula, fecha, método de pago, duplicados, JSON mal formado); `"50000"` se normaliza y `"abc"` nunca se vuelve 0 | ✅ | `fraud_validation.py`, `static/transacciones.js` |
| Estados `VALID` / `REJECTED` / `SUSPICIOUS` con motivo; las rechazadas se conservan | ✅ | `fraud_service.py` |
| Hash HMAC-SHA256 sobre JSON determinista: generar, guardar, validar y detectar alteraciones | ✅ | `fraud_hashing.py` |
| **Ventana deslizante real de 10 s (configurable), una por usuario** | ✅ | `sliding_window.py` |
| Detección: 3 o más del mismo usuario en la ventana → `POSSIBLE_FRAUD` (configurable) | ✅ | `fraud_service.py` |
| Reglas por horario (10 / 6 / 3 ventas) como segunda capa, sin reemplazar la ventana | ✅ | `fraud_service.py` |
| Logs (qué, cuándo, usuario, transacción, estado, motivo, hash, anomalía); ventana activa separada del historial | ✅ | colección `logs` + `logs/fraud.log` |
| Persistencia en **MongoDB** con índices (usuario, fecha, estado, ID de transacción) | ✅ | `fraud_repo.py` |
| API REST: `POST /api/transactions` y consultas de transacciones, anomalías, logs, estadísticas y ventana actual | ✅ | `fraud_routes.py` |
| Dashboard de la pág. 44 del PDF (totales día/semana/mes, % anomalías, usuarios afectados, valor sospechoso, estados de anomalías, tendencias, evolución, mapa de calor por hora, métodos de pago, línea de tiempo y **ventana deslizante en vivo**) | ✅ | `/antifraude` |
| Pruebas obligatorias (12 casos) | ✅ | `tests/test_fraud.py`, `tests/e2e_fraud_http.py` |
| Guía para que una IA pruebe la app completa | ✅ | `docs/PRUEBA_CON_IA.md` |

### Capacitación: métodos HTTP, hash y descomposición de problemas

Diapositivas *Métodos HTTP*, *Hash de una transacción* y *Análisis y descomposición de problemas*.
Se probó cada punto contra el servidor corriendo (`python tests/prueba_profesor.py`).

| Tema de la capacitación | Estado | Dónde |
|---|---|---|
| GET: consultar productos | ✅ | `GET /api/productos`, `GET /api/productos/{id}` |
| POST: crear un producto o una transacción | ✅ | `POST /api/productos`, `POST /api/transactions` |
| PUT: reemplazar completo | ✅ | `PUT /api/productos/{id}` (pide todos los campos; lo no enviado vuelve a su valor por defecto) |
| PATCH: actualizar solo lo enviado | ✅ | `PATCH /api/productos/{id}` (`{"precio": 60000}` no toca nombre ni categoría) |
| DELETE: eliminar por id | ✅ | `DELETE /api/productos/{id}` (si el producto está en pedidos del historial responde 409 y explica) |
| Hash HMAC-SHA256 con la llave de la clase, calculado con el código de la diapositiva | ✅ | `fraud_hashing.py`; llave por defecto `mi_llave_privada_123` |
| Calcular / verificar el hash de **cualquier** JSON (el de la diapositiva: `id, producto, cantidad, valor`) | ✅ | `POST /api/hash/calcular`, `POST /api/hash/verificar` |
| Aceptar o rechazar según coincida el hash (y decir por qué) | ✅ | `POST /api/transactions`, y `hash` opcional en POST/PUT/PATCH de productos |
| "Un hash por sí solo no autentica al remitente" | ✅ documentado | sección *Hash*; el hash prueba integridad, no identidad |
| Descomposición: validar cada producto, saltar los inválidos, sumar el total (`Mouse "50000" x "2"` + `Teclado`) | ✅ | `POST /api/totales` |
| Divide y vencerás / recursividad (dividir, resolver, combinar) | ✅ ya existía | `algorithms.recursive_total_units`, laboratorio `/laboratorio` |

**Qué faltaba y se agregó:** los métodos PUT/PATCH/DELETE (la app solo tenía POST y GET), un hash que
se pueda calcular con el código de la clase (antes el servidor firmaba con otra llave y exigía
`nombre` y `cédula`, que no están en la diapositiva), el cálculo de totales y los logs de cada petición.

### Rutas para probar y ver qué pasa (`/logs`)

Todas funcionan en `http://localhost:8000` y por la URL pública de ngrok.

| Qué | Ruta |
|---|---|
| **Logs en vivo**: cada petición, qué envió, qué respondió la app y por qué | `/logs` |
| Mismos logs en JSON (`?desde=N` trae solo las nuevas, `?automaticas=true` incluye las de las páginas) | `GET /api/logs/http` |
| Documentación interactiva: se prueba cada ruta con un botón | `/docs` |
| Índice de todas las rutas de la API | `GET /api` |
| Estado de MongoDB y de la app | `GET /api/health` |
| Logs de negocio (transacciones, anomalías, hash) | `GET /api/logs` |
| Archivos en disco (también en la consola del servidor) | `logs/http.log`, `logs/fraud.log` |

Cada respuesta de la app (salvo archivos estáticos y `/api/logs/http`) trae el encabezado `X-Request-Id`: ese mismo `id` aparece en `/logs`, así que si alguien
dice "me dio error", se busca su `id` y se ve exactamente qué envió y qué respondió la app.
**Los errores no salen pelados**: un 404, un 405, un JSON roto, un parámetro inválido o un
error inesperado responden `{"ok": false, "motivo": ..., "mensaje": ...}` explicando la causa y qué hacer.
Si el error es un fallo del servidor (500), la traza completa queda en `/logs`.

### Probarlo desde afuera con ngrok

Para que el profesor entre desde su equipo hay que publicar el puerto 8000. Pasos (PowerShell):

1. Cree una cuenta gratis en <https://dashboard.ngrok.com/signup> y copie su *authtoken*
   (<https://dashboard.ngrok.com/get-started/your-authtoken>). **Sin authtoken ngrok no arranca** (`ERR_NGROK_4018`).
2. Instale el agente: `winget install ngrok.ngrok` (o descárguelo de <https://ngrok.com/download>) y registre el token una sola vez:

   ```powershell
   ngrok config add-authtoken SU_TOKEN
   ```

3. Arranque MongoDB y la app (ver "Cada vez que quiera usarla") y, en **otra** terminal:

   ```powershell
   ngrok http 8000
   ```

4. ngrok muestra una línea `Forwarding https://xxxx.ngrok-free.app -> http://localhost:8000`.
   Esa URL es la que se le da al profesor. Compruébela primero: `https://xxxx.ngrok-free.app/api/health`.
5. Deje abierto `https://xxxx.ngrok-free.app/logs` (o `http://localhost:8000/logs`): cada petición del
   profesor aparece ahí con `origen: ngrok` y su IP. El inspector de ngrok está en `http://127.0.0.1:4040`.
6. Antes de la sustentación, ejecute **desde otro equipo o red** (el celular con datos sirve):
   `python tests/prueba_profesor.py https://xxxx.ngrok-free.app` y
   `python tests/prueba_clientes_externos.py https://xxxx.ngrok-free.app`. Si pasan, el profesor no debería ver errores.

Qué debe saber el profesor:

- **Llave:** por defecto es `mi_llave_privada_123`, la del código de la clase. Para usar otra, arranque con
  `$env:APPRESSO_HMAC_SECRET="otra"` y avísele.
- **Navegador:** con la cuenta gratis, ngrok muestra una página de advertencia antes de la app. Postman,
  curl, Python `requests` y similares no la ven; en el navegador se pulsa *Visit Site*, o se envía el
  encabezado `ngrok-skip-browser-warning: 1` en las llamadas hechas por código.
- **La URL cambia** cada vez que se reinicia ngrok (salvo que reserve un dominio gratis en el panel de ngrok).
- Si MongoDB está apagado al arrancar, las transacciones se guardan en memoria y la app avisa; si se cae con la app corriendo, responden `503` reintentable. En ambos casos se recupera sola cuando MongoDB vuelve, y productos, hash y totales siguen funcionando.

### Clientes externos: bots de Telegram, Postman, páginas web

La API acepta lo que suelen mandar los clientes externos, sin errores 400 por el formato:

| Cliente | Qué manda | Cómo lo recibe la app |
|---|---|---|
| Bot de Telegram / `requests` | JSON, o los datos en la URL (`requests.post(url, params=...)`) | Ambos sirven; la URL solo se usa si el cuerpo llega vacío |
| Telegram, JavaScript | Fecha como número: segundos (`message.date`) o milisegundos (`Date.now()`) | Se convierte a la hora local del servidor |
| Webhook de Telegram apuntado a la API | Un `Update` de Telegram (no es una transacción) | Responde 201 `REJECTED` y queda en la cuarentena; Telegram no reintenta |
| Postman | Pestaña *raw* (JSON), *x-www-form-urlencoded* o *form-data* (también un `.json` adjunto) | Los tres sirven |
| PowerShell 5.1 | JSON en Windows-1252 o UTF-16 (tildes) | Se decodifica bien |
| Página web de otro dominio, Hoppscotch | Primero un `OPTIONS` (CORS) | Permitido; orígenes en `APPRESSO_CORS_ORIGINS` (por defecto `*`) |
| Monitores de disponibilidad | `HEAD` | Responde como `GET`, sin cuerpo |

Las fechas numéricas, la URL como cuerpo y el `user` sin "@" solo se aceptan en modo tolerante
(`APPRESSO_LENIENT_INPUTS`, activo por defecto). Desde el **navegador** con ngrok gratis, las llamadas
por código deben enviar el encabezado `ngrok-skip-browser-warning: 1` (CORS ya lo permite).
`tests/prueba_clientes_externos.py` comprueba todo esto (35 casos, sin URL simula ngrok en local).

**Limitaciones conocidas:**

- La ventana activa vive en **memoria del proceso**: ejecute un solo proceso
  de uvicorn (sin `--workers`). Al reiniciar se reconstruye desde MongoDB.
- La página `/logs` guarda en memoria las últimas 1.000 peticiones (se vacía al reiniciar); lo que
  sigue disponible en `logs/http.log`. No registra `/static` ni `/api/logs/http`.
- `DELETE /api/productos/{id}` borra de verdad un producto sin historial: quien tenga la URL pública
  puede vaciar el menú. Úsela solo durante la prueba.
- Los pedidos de la app de comidas (`/`) y las transacciones antifraude son
  sistemas **separados**: un pedido no genera una transacción automáticamente.
- No hay autenticación de usuarios. El hash garantiza integridad, no identidad.
- El PDF no aclara si el límite por horario es por usuario o global; se aplicó
  por usuario (ver "Reglas por horario").
- Las estadísticas se calculan en Python sobre el último mes; es suficiente
  para el volumen de este proyecto, no para millones de transacciones.

### Aplicación de comidas rápidas (base del proyecto)

Menú y pedidos por local y domicilio, ranking de más pedidos, grafo de barrios
con Dijkstra, heap de despacho, cola FIFO y pila de deshacer, inventario,
historial y fidelización, pronóstico de ventas y laboratorio de complejidad.
Detalle en la sección siguiente.

## Alcance funcional

1. **Menú y pedidos**: catálogo de productos, carrito y registro de ventas
   tanto en el local físico como a domicilio.
2. **Ranking de "más pedidos"**: guía al cliente sobre lo más vendido, en
   general y por barrio.
3. **Grafo de barrios + Dijkstra**: cada barrio es un nodo, cada distancia
   una arista. Al recibir un domicilio se calcula la ruta más corta desde el
   restaurante hasta el barrio del cliente (ej. `Restaurante -> Laureles ->
   Centro -> El Poblado`).
4. **Heap de despacho**: los domicilios entran a una cola de prioridad
   (`heapq`) ordenada por distancia; el barrio más cercano siempre está en
   la raíz, sin importar el orden de llegada.
5. **Cola y pila de pedidos**: una cola FIFO de pedidos pendientes (se
   atienden en el orden en que llegaron) y una pila LIFO para deshacer la
   última acción (crear pedido, avanzar la cola o despachar un domicilio).
6. **Zona de cobertura**: un domicilio hacia un barrio que no está en el
   grafo se rechaza automáticamente.
7. **Inventario básico**: cada producto descuenta sus ingredientes al
   venderse; se avisa cuando un ingrediente se queda sin stock.
8. **Historial por cliente y fidelización**: se puede consultar el
   historial de pedidos de un cliente y proyectar, con una progresión
   aritmética, en cuántos pedidos más alcanzará una meta de unidades.
9. **Pronóstico de ventas**: regresión lineal sobre las unidades vendidas
   por día, separado por canal (local/domicilio).
10. **Laboratorio de complejidad computacional**: genera pedidos sintéticos
    (no se guardan en la base de datos) para medir cómo escalan los
    algoritmos de búsqueda, suma y recursividad (Big O), tal como se pedía
    en el proyecto original.

## Relaciones del modelo de datos

El esquema (`storage.py`) tiene varias relaciones reales entre tablas, con
ambas puntas de cada relación usadas de verdad en el código:

- `orders.neighborhood_id -> neighborhoods.id`: relación **pedido <-> barrio**.
- `order_items.order_id -> orders.id` y `order_items.product_id ->
  products.id`: relación **pedido <-> producto** (tabla puente).
- `product_ingredients -> products / ingredients`: relación **producto <->
  ingrediente**, usada para descontar inventario.

Con las dos primeras ya se puede responder, por ejemplo, "¿qué producto es
el más pedido en Belén Castilla?" con un solo `JOIN` entre `orders`,
`order_items`, `products` y `neighborhoods` (ver
`storage.top_products_by_neighborhood`).

## Estructura del proyecto

```
appresso_food/
  app.py              arranque: crea la app y conecta los módulos
  paginas.py          páginas HTML (pedir, cocina, dashboard, cliente, laboratorio)
  web.py              plantillas y carpeta estática compartidas
  nucleo/             lógica del restaurante
    models.py  storage.py  seed_data.py  runtime.py  ranking.py  growth.py  regression.py
    graph.py (Dijkstra)  dispatch.py (heap)  queue_stack.py (cola FIFO y pila LIFO)
    algorithms.py  counter.py  demo_data.py (laboratorio de complejidad)
  antifraude/         transacciones, ventana deslizante, hash HMAC y MongoDB
    fraud_*.py  sliding_window.py
  api/                API REST y bitácora
    productos_api.py  capacitacion_api.py  api_helpers.py  http_log.py (/logs)
  templates/          base.html (cabecera, menú y pie) + una plantilla por página
  static/css/         app.css (tema) y antifraude.css
  static/js/          nav.js, transacciones.js, antifraude.js, fraud-common.js
tests/                pruebas automáticas
docs/                 diccionario de lógica, resumen académico y plan
requirements.txt
```

## Cómo ejecutar la app

### Requisitos

- **Python 3.11** o superior.
- **MongoDB** (solo para el módulo antifraude; el resto de la app funciona sin él).
  La forma más simple es **Docker Desktop**.

### Primera vez

Desde la carpeta del proyecto, en PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
docker run -d --name appresso-mongo --restart unless-stopped -p 27017:27017 -v appresso-mongo-data:/data/db mongo:7
```

### Cada vez que quiera usarla

1. Abra **Docker Desktop** y arranque MongoDB (si el contenedor ya existe):

   ```powershell
   docker start appresso-mongo
   ```

2. Arranque la app (un solo proceso):

   ```powershell
   .\venv\Scripts\python.exe -m uvicorn appresso_food.app:app --host 0.0.0.0 --port 8000
   ```

3. Abra las páginas:

| Qué | URL |
|---|---|
| Pedir (app de comidas) | `http://localhost:8000/` |
| Cocina | `http://localhost:8000/cocina` |
| Dashboard del negocio | `http://localhost:8000/dashboard` |
| Laboratorio de complejidad | `http://localhost:8000/laboratorio` |
| **Formulario de transacciones** | `http://localhost:8000/transacciones` |
| **Dashboard antifraude** | `http://localhost:8000/antifraude` |
| Estado de MongoDB | `http://localhost:8000/api/health` |

Si MongoDB no está disponible **al arrancar**, la app arranca igual: el módulo antifraude
guarda en **memoria** (esos datos se pierden al reiniciar), muestra un aviso,
`/api/health` responde `"mongodb": "no disponible (modo memoria)"` y cada 15 s reintenta
MongoDB: cuando vuelve, se conecta sola sin reiniciar la app.
Si MongoDB **se cae con la app corriendo**, las rutas de transacciones responden `503`
(`MONGODB_NO_DISPONIBLE`, con `Retry-After`) en vez de un error interno, la petición no se
guarda (se puede reenviar) y al volver MongoDB todo sigue funcionando.
Para que otro equipo de la misma red entre, use la IP de este equipo en lugar de `localhost`
y permita el puerto 8000 en el firewall de Windows; desde otra red, use ngrok (ver más abajo).

### Comprobar que todo funciona

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests
.\venv\Scripts\python.exe tests\prueba_profesor.py
```

El segundo necesita la app corriendo (con MongoDB para que los datos persistan)
y deja transacciones de prueba visibles en `/antifraude`.

`tests\e2e_fraud_http.py` comprueba los códigos HTTP **estrictos** (422/400 en
los rechazos), así que solo pasa si la app se arranca con
`APPRESSO_REJECTED_AS_201=false` y `APPRESSO_LENIENT_INPUTS=false`. Sus datos se
borran con `tests\e2e_fraud_http.py --clean` (reinicie la app después, porque la
ventana activa está en memoria).

Para que una IA pruebe la aplicación completa por el navegador, siga
`docs/PRUEBA_CON_IA.md`.

## Pruebas

Resumen de los últimos cambios: `docs/CAMBIOS.md`. Para la prueba desde afuera (ngrok): `python tests/prueba_profesor.py https://xxxx.ngrok-free.app` (58 comprobaciones; funciona con MongoDB o en modo memoria). `tests/e2e_fraud_http.py` espera los códigos estrictos y MongoDB real: córralo con `APPRESSO_REJECTED_AS_201=false` y `APPRESSO_LENIENT_INPUTS=false`. Clientes externos (Telegram, Postman, CORS): `python tests/prueba_clientes_externos.py [URL]`.

```powershell
python -m unittest discover -s tests
```

Cubren: Dijkstra sobre el grafo, orden del heap de despacho, comportamiento
FIFO/LIFO de la cola y la pila, los algoritmos de búsqueda/suma/recursividad,
el flujo completo de `runtime` (crear domicilio con ruta calculada,
rechazo por cobertura, deshacer con restitución de inventario) y todo el
módulo antifraude (`tests/test_fraud.py`, sin necesidad de MongoDB).

## Módulo antifraude: transacciones, ventana deslizante y hash

Basado en el PDF *Técnicas de resolución de problemas en desarrollo de
software*. Recibe transacciones de compra, las valida, firma su integridad y
detecta comportamiento anómalo con una **ventana deslizante por usuario**.
Convive con lo anterior: no reemplaza ninguna funcionalidad ni toca SQLite.

| Página | URL |
|---|---|
| Formulario de transacciones | `/transacciones` |
| Dashboard antifraude | `/antifraude` |

Cómo ejecutarlo: ver "Cómo ejecutar la app" más arriba (necesita MongoDB).
`python tests\e2e_fraud_http.py` ejecuta 31 comprobaciones de punta a punta.

### Variables de entorno (todas opcionales)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `APPRESSO_WINDOW_SECONDS` | `10` | Tamaño de la ventana deslizante |
| `APPRESSO_MAX_TRANSACTIONS` | `3` | N o más transacciones del mismo usuario en la ventana = `POSSIBLE_FRAUD` |
| `APPRESSO_HMAC_SECRET` | `mi_llave_privada_123` (la de la clase) | Llave del HMAC-SHA256 (**cámbiela fuera de la clase**) |
| `APPRESSO_MONGO_URI` | `mongodb://localhost:27017` | Conexión a MongoDB |
| `APPRESSO_MONGO_DB` | `appresso_food` | Base de datos |
| `APPRESSO_BAND_RULES_ENABLED` | `true` | Segunda capa: límite por franja horaria |
| `APPRESSO_BAND_RULES` | ver abajo | JSON `[["NOMBRE","HH:MM:SS","HH:MM:SS",límite],...]` |
| `APPRESSO_PAYMENT_METHODS` | `Tarjeta,Efectivo,Nequi,Daviplata,PSE,Transferencia` | Métodos válidos |
| `APPRESSO_HASH_HELPER` | `true` | Habilita `POST /api/transactions/hash` (firma desde el formulario) |
| `APPRESSO_LENIENT_INPUTS` | `true` | Modo generador externo: `user` como correo o id simple, método de pago libre, hash SHA-256 sin llave |
| `APPRESSO_REJECTED_AS_201` | `true` | Una petición recibida que queda RECHAZADA (o cuerpo roto) responde 201 con el resultado en el cuerpo y se guarda en la cuarentena; `false` devuelve 422 / 400 |

### Flujo de `POST /api/transactions`

```
JSON -> validación + normalización -> hash HMAC-SHA256 -> ID duplicado
     -> identificar usuario (correo) -> ventana deslizante: ENTRA / SALEN
     -> contar -> comparar con el límite -> regla por horario -> guardar -> log -> responder
```

Cuerpo (los nombres de campo son los del PDF; `nombre`, `cedula` y `hash` son opcionales):

```json
{ "idTxn": 10001, "user": "aa@aa.com", "date": "2026-09-23T10:30:01.120",
  "value": 50000, "paymentMethod": "Tarjeta" }
```

El formulario web sí exige `nombre` y `cedula`; por API, si llegan se validan igual que el resto y si no
llegan no pasa nada. Si faltan campos obligatorios, la respuesta incluye `formato_esperado` con un ejemplo.

Respuestas: `201` válida o sospechosa, `422` rechazada, `409` ID duplicado,
`400` JSON mal formado, `503` sin MongoDB.

### Ventana deslizante

- **Una ventana por usuario** (correo en minúsculas); nunca se mezclan.
- Con cada transacción: **1)** entra a la ventana en orden cronológico,
  **2)** salen las que tienen N segundos o más de antigüedad respecto a la
  más reciente, **3)** se cuenta y se compara con el límite.
- Es deslizante de verdad, no un contador que se reinicia: con N=10, las
  transacciones a los 8, 9 y 11 s cuentan como 3 en 3 s, aunque una ventana
  fija las separaría. Intervalo vigente `(último − N, último]`: una
  transacción exactamente N segundos más antigua ya salió.
- Se mide con la **fecha de la transacción** (`date`), no con la hora de
  llegada, para que los casos de prueba sean reproducibles.
- **Llegadas fuera de orden.** El conteo es el mayor grupo de transacciones
  dentro de menos de N segundos que **contenga** a la nueva, no solo lo que
  la precede: `10:00:10`, `10:00:01` y `10:00:02` son 3 en 9 s aunque la
  última en llegar sea la de `:02`. Si llega con fecha anterior a otra ya
  recibida (`tardia: true`), el conteo usa el historial de MongoDB (±N s),
  porque lo que ya salió de la ventana activa pudo formar grupo con ella.
  Una llegada tardía nunca aparece como su propia salida.
- **Ventana activa ≠ historial.** Lo que sale de la ventana se registra
  (`VENTANA_SALE`) y sigue en MongoDB. Al reiniciar el servidor la ventana se
  reconstruye desde el historial.

### Reglas por horario (segunda capa)

Del PDF (pág. 38): máximo de ventas **por usuario y franja** — mañana
05:00:01–12:00:00 → 10, tarde 12:00:01–20:00:00 → 6, noche 20:00:01–05:00:00
(cruza la medianoche) → 3. El PDF no precisa si el límite es por usuario o
global; se interpretó por usuario y **se marca al superar el límite** (más de N).
Genera la anomalía `TOO_MANY_TRANSACTIONS` (nivel `BAJO`). **No reemplaza** la
regla principal: ambas se evalúan y una transacción puede disparar las dos.
Se desactiva con `APPRESSO_BAND_RULES_ENABLED=false`.

### Estados y motivos

- Transacción: `VALID`, `SUSPICIOUS` (válida pero dispara una regla) y
  `REJECTED` (mal formada: no cuenta, queda guardada con su motivo).
- Motivos de rechazo: `NULL_FIELD`, `EMPTY_FIELD`, `INVALID_TYPE`,
  `INVALID_EMAIL`, `INVALID_VALUE`, `INVALID_DATE`, `INVALID_ID`,
  `INVALID_NAME`, `INVALID_CEDULA`, `INVALID_PAYMENT_METHOD`,
  `INVALID_HASH_FORMAT`, `MALFORMED_JSON`, `DUPLICATE_TRANSACTION`, `HASH_MISMATCH`.
- Anomalías: tipo `POSSIBLE_FRAUD` / `TOO_MANY_TRANSACTIONS`; nivel `BAJO`,
  `MEDIO` (justo en el límite), `ALTO` (lo supera); estado `NUEVA`,
  `ABIERTA`, `REVISADA`, `DESCARTADA` (cambia con `PATCH /api/anomalies/{id}`).

### Validaciones

El backend es la autoridad; el formulario valida lo mismo solo para avisar
antes. Se reúnen **todos** los errores, no solo el primero. `"50000"` se
normaliza a número; `"abc"`, `"50.000,00"`, `NaN`, negativos, cero o booleanos
**se rechazan y nunca se vuelven 0**. El correo, la cédula (6–10 dígitos), la
fecha ISO 8601 con hora y el método de pago se comprueban; las fechas con
zona horaria se convierten a la hora local del servidor.

### Hash (HMAC + SHA-256)

Es el código de la clase: JSON determinista (`sort_keys=True`, separadores `(",", ":")`) firmado con
`hmac.new(LLAVE, datos.encode("utf-8"), hashlib.sha256).hexdigest()`. Si el cliente envía `hash`, el
servidor lo compara con el HMAC **del JSON tal como llegó** (sin el campo `hash`), que es lo que firmó el
cliente; también acepta el de los datos normalizados (el que calcula el formulario, donde `50000` y
`"50000"` dan el mismo hash). Si no coincide se rechaza (`HASH_MISMATCH`, HTTP 422); si no lo envía, el
servidor lo genera y lo guarda. `GET /api/transactions/{id}/verify` lo recalcula después con los datos
guardados y detecta alteraciones en la base de datos.

**Un `HASH_MISMATCH` siempre explica la causa** (campo `diagnostico_hash`): si el hash es el de otra llave
conocida ("firmó con la llave anterior de Appresso"), si es un SHA-256 simple sin llave, o si los datos
cambiaron; además entrega el texto exacto que firma el servidor y la huella de su llave
(`hashlib.sha256(LLAVE).hexdigest()[:12]`) para compararla con la de quien firmó. Ver la huella en `GET /api/config`.
La huella y `POST /api/hash/calcular` solo existen con `APPRESSO_HASH_HELPER=true` (el modo clase, por defecto):
firmar datos a pedido de cualquiera permite fabricar hashes válidos, así que fuera de la clase se desactiva con `APPRESSO_HASH_HELPER=false`.

> Un hash **no autentica al remitente**: garantiza integridad, no identidad.
> Además, `POST /api/transactions/hash` firma cualquier dato con la llave del
> servidor (existe para poder probar desde el formulario); en un entorno real
> se deshabilita con `APPRESSO_HASH_HELPER=false`.

### MongoDB

Colecciones (adaptación a documentos del modelo de la pág. 45 del PDF):

- `usuarios`: `email` (único), `nombre`, `cedula`, `estado`, `fecha_creacion`, `fecha_actualizacion`.
- `transacciones`: `id_txn`, `usuario_id`, `usuario_email`, `valor`, `fecha_txn`,
  `estado`, `motivo`, `errores[]`, `hash`, `metodo_pago`, `aceptada`, `payload_original`,
  `fecha_creacion`, `fecha_actualizacion`. Guarda **todos** los intentos; la
  unicidad de `id_txn` es solo entre las `aceptada: true` (un rechazo no "quema" el ID).
- `anomalias`: `transaccion_id`, `tipo`, `nivel`, `estado`, `cantidad_transacciones`,
  `ventana_segundos`, `limite`, `transacciones_ventana[]`, fechas.
- `logs`: `ts`, `nivel`, `evento`, `usuario`, `id_txn`, `estado`, `motivo`, `hash`, `anomalia`, `detalle`.

Índices: `usuarios.email` único; `transacciones.id_txn` único parcial
(`aceptada: true`), `(usuario_email, fecha_txn)`, `fecha_ref`, `(estado, fecha_ref)`;
`anomalias`: `(usuario_email, fecha_txn)`, `(estado, fecha_creacion)`, `tipo`, `transaccion_id`;
`logs`: `ts`, `(usuario, ts)`, `id_txn`, `evento`. Los logs también se escriben en `logs/fraud.log`.

### API

| Método | Ruta | Uso |
|---|---|---|
| POST | `/api/transactions` | Procesar una transacción |
| GET | `/api/transactions?estado=&usuario=&limit=` | Historial |
| GET | `/api/transactions/{id}/verify` | Re-verificar el hash guardado |
| POST | `/api/transactions/hash` | Calcular el hash que espera el servidor (datos de una transacción) |
| POST | `/api/hash/calcular` · `/api/hash/verificar` | Hash de **cualquier** JSON / verificarlo y decir ACEPTADA o RECHAZADA |
| GET · POST · PUT · PATCH · DELETE | `/api/productos` · `/api/productos/{id}` | CRUD de productos del menú |
| POST | `/api/totales` | Total de una lista de productos validando cada uno |
| GET | `/api` · `/api/logs/http` · `/logs` | Índice de rutas, logs de peticiones (JSON y página) |
| GET | `/api/anomalies?estado=` · `PATCH /api/anomalies/{id}` | Anomalías y cambio de estado |
| GET | `/api/anomalies/{id}/timeline` | Línea de tiempo de una anomalía |
| GET | `/api/window?usuario=` | Ventana deslizante activa |
| GET | `/api/logs?usuario=&evento=` · `/api/stats` · `/api/config` · `/api/health` | Logs, estadísticas, configuración, estado |

Las estadísticas se agrupan por la fecha de la transacción (hora local del servidor).
