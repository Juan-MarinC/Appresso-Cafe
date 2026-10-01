# Appresso Food

Evolución de **Appresso Café** hacia un sistema de gestión para un restaurante
de comida rápida. Reutiliza la base de datos, los algoritmos y la
arquitectura del proyecto anterior (FastAPI + SQLite + Jinja2), pero cambia
por completo el dominio: ahora gestiona pedidos de comida rápida por dos
canales (local y domicilio), calcula rutas de entrega con un grafo de
barrios y prioriza despachos con un heap.

## Estado actual

Lo que se pidió y qué tiene hoy la app. Todo lo marcado ✅ está implementado y
probado (63 pruebas unitarias + 31 de punta a punta contra MongoDB real).

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
| Guía para que una IA pruebe la app completa | ✅ | `tests/PRUEBA_CON_IA.md` |

**Limitaciones conocidas:**

- La ventana activa vive en **memoria del proceso**: ejecute un solo proceso
  de uvicorn (sin `--workers`). Al reiniciar se reconstruye desde MongoDB.
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

- `app.py`: rutas de FastAPI (pedir, cocina, dashboard, cliente, laboratorio).
- `models.py`: entidades del dominio (`Product`, `Ingredient`, `Order`, `OrderItem`).
- `storage.py`: esquema SQLite, seed inicial y consultas de analítica.
- `seed_data.py`: menú, ingredientes, barrios y distancias iniciales.
- `graph.py`: grafo de barrios y Dijkstra (`DeliveryGraph`).
- `dispatch.py`: heap de prioridad para despacho de domicilios (`DispatchHeap`).
- `queue_stack.py`: cola FIFO de pendientes y pila LIFO de deshacer.
- `runtime.py`: estado en memoria que conecta grafo + cola + heap + pila con la base de datos.
- `ranking.py`: consultas de "más pedidos" y comparación de canales.
- `algorithms.py` / `counter.py`: búsqueda lineal, suma y recursividad instrumentadas para medir Big O.
- `demo_data.py`: generador de pedidos sintéticos para el laboratorio de complejidad.
- `growth.py`: progresión aritmética aplicada a fidelización de clientes.
- `regression.py`: pronóstico de ventas con regresión lineal (NumPy).
- `fraud_*.py`, `sliding_window.py`: módulo antifraude (ver sección más abajo).
- `templates/`, `static/`: interfaz web.

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
python -m pip install -r appresso_food\requirements.txt
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

Si MongoDB no está disponible, la app arranca igual: solo el módulo
antifraude responde `503` con el motivo y se reconecta solo cuando MongoDB vuelve.
Para que otro equipo entre, use la IP de este equipo en lugar de `localhost`
y permita el puerto 8000 en el firewall de Windows.

### Comprobar que todo funciona

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests
.\venv\Scripts\python.exe tests\e2e_fraud_http.py
```

El segundo necesita la app y MongoDB corriendo; deja datos de prueba visibles
en `/antifraude`, que se borran con `tests\e2e_fraud_http.py --clean`
(reinicie la app después, porque la ventana activa está en memoria).
Para que una IA pruebe la aplicación completa por el navegador, siga
`tests/PRUEBA_CON_IA.md`.

## Pruebas

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
| `APPRESSO_HMAC_SECRET` | llave de desarrollo | Llave del HMAC-SHA256 (**cámbiela fuera de desarrollo**) |
| `APPRESSO_MONGO_URI` | `mongodb://localhost:27017` | Conexión a MongoDB |
| `APPRESSO_MONGO_DB` | `appresso_food` | Base de datos |
| `APPRESSO_BAND_RULES_ENABLED` | `true` | Segunda capa: límite por franja horaria |
| `APPRESSO_BAND_RULES` | ver abajo | JSON `[["NOMBRE","HH:MM:SS","HH:MM:SS",límite],...]` |
| `APPRESSO_PAYMENT_METHODS` | `Tarjeta,Efectivo,Nequi,Daviplata,PSE,Transferencia` | Métodos válidos |
| `APPRESSO_HASH_HELPER` | `true` | Habilita `POST /api/transactions/hash` (firma desde el formulario) |

### Flujo de `POST /api/transactions`

```
JSON -> validación + normalización -> hash HMAC-SHA256 -> ID duplicado
     -> identificar usuario (correo) -> ventana deslizante: ENTRA / SALEN
     -> contar -> comparar con el límite -> regla por horario -> guardar -> log -> responder
```

Cuerpo (los nombres de campo son los del PDF más `nombre` y `cedula`):

```json
{ "idTxn": 10001, "nombre": "Ana Pérez", "cedula": "1012345678", "user": "aa@aa.com",
  "date": "2026-09-23T10:30:01.120", "value": 50000, "paymentMethod": "Tarjeta", "hash": "(opcional)" }
```

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

Se calcula sobre JSON determinista (`sort_keys=True`, separadores `(",", ":")`)
de los datos **ya normalizados**, por lo que `50000` y `"50000"` dan el mismo
hash. Si el cliente envía `hash`, se recalcula y se rechaza (`HASH_MISMATCH`)
si no coincide; si no lo envía, el servidor lo genera y lo guarda.
`GET /api/transactions/{id}/verify` lo recalcula después con los datos
guardados y detecta alteraciones en la base de datos.

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
| POST | `/api/transactions/hash` | Calcular el hash que espera el servidor |
| GET | `/api/anomalies?estado=` · `PATCH /api/anomalies/{id}` | Anomalías y cambio de estado |
| GET | `/api/anomalies/{id}/timeline` | Línea de tiempo de una anomalía |
| GET | `/api/window?usuario=` | Ventana deslizante activa |
| GET | `/api/logs?usuario=&evento=` · `/api/stats` · `/api/config` · `/api/health` | Logs, estadísticas, configuración, estado |

Las estadísticas se agrupan por la fecha de la transacción (hora local del servidor).
