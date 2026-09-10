# Diccionario de lógica y archivos — Appresso Food

## 1. `app.py`
Rutas de FastAPI que conectan la interfaz con la lógica de negocio.

- `GET /`: menú + formulario de pedido + ranking de "más pedidos".
- `POST /pedidos`: crea un pedido (local o domicilio); si es domicilio,
  calcula la ruta con `runtime.place_order` (grafo + Dijkstra) y rechaza el
  barrio si está fuera de cobertura.
- `GET /cocina`, `POST /cocina/atender|despachar|deshacer`: operación de la
  cola FIFO, el heap de despacho y la pila de deshacer.
- `GET /dashboard`: ranking general, ranking por barrio, comparación de
  canales, grafo de cobertura y pronóstico de ventas.
- `GET /clientes/{client}`: historial y proyección de fidelización.
- `GET|POST /laboratorio`: laboratorio de complejidad computacional (Big O)
  sobre pedidos sintéticos.

## 2. `models.py`
Entidades del dominio: `Product`, `Ingredient`, `Neighborhood`, `OrderItem`
y `Order` (con `total` y `total_quantity` calculados).

## 3. `storage.py`
Esquema SQLite y consultas. Relaciones clave:
`orders.neighborhood_id -> neighborhoods.id` (pedido↔barrio) y
`order_items` como tabla puente entre `orders` y `products` (pedido↔producto),
más `product_ingredients` (producto↔ingrediente) para el inventario.
`top_products_by_neighborhood()` combina las dos primeras relaciones con un
`JOIN` para responder "qué se pide más en cada barrio".

## 4. `seed_data.py`
Menú, ingredientes, barrios (barrios reales de Medellín: Laureles, El
Poblado, Belén Castilla, Envigado, etc.) y las distancias iniciales del
grafo de domicilios.

## 5. `graph.py`
`DeliveryGraph`: grafo no dirigido de barrios. `shortest_path()` implementa
Dijkstra con un heap (`heapq`) para encontrar la distancia mínima y la ruta
entre el restaurante y el barrio del cliente, igual que el ejemplo de la
diapositiva (A→B directo vs. A→C→D→B, gana la ruta de menor distancia total).

## 6. `dispatch.py`
`DispatchHeap`: heap de prioridad para domicilios. La raíz siempre es el
barrio más cercano sin importar el orden de llegada; ante empate, gana el
que llegó primero. `remove()` purga la tupla física del heap (no solo la
entrada lógica) para que un `push` posterior con el mismo `order_id` — como
ocurre al deshacer un despacho — no quede duplicado.

## 7. `queue_stack.py`
- `PendingOrdersQueue`: cola FIFO de pedidos pendientes (mostrador/cocina).
- `UndoStack`: pila LIFO de las últimas acciones (crear pedido, avanzar la
  cola, despachar un domicilio) para poder deshacerlas en orden inverso.

## 8. `runtime.py`
Estado en memoria que conecta las estructuras anteriores con la base de
datos: reconstruye el grafo y la cola/heap al iniciar la app, y expone
`place_order`, `advance_pending`, `dispatch_next_delivery` y `undo_last`.

## 9. `ranking.py`
Envuelve las consultas de "más pedidos", "más pedido por barrio" y
comparación de canales para las vistas.

## 10. `algorithms.py` + `counter.py`
Igual que en el proyecto original, pero aplicados a pedidos reales:
- `find_order_linear()`: búsqueda lineal O(n).
- `total_units_sold()`: suma de unidades O(n).
- `recursive_total_units()`: mismo total por divide y vencerás (trabajo
  O(n), profundidad O(log n)).
`OperationCounter` cuenta comparaciones, sumas y llamadas para justificar
la complejidad frente al profesor.

## 11. `demo_data.py`
Genera pedidos sintéticos (no se guardan en la base de datos) para el
laboratorio de complejidad, con tamaños crecientes (10, 100, 1.000, 10.000…).

## 12. `growth.py`
Progresión aritmética (`a_n = a_1 + (n-1)d`) aplicada a fidelización: dado
el incremento real de pedidos de un cliente, calcula en cuántos pedidos más
alcanzará 42, 72 o 120 unidades.

## 13. `regression.py`
Regresión lineal simple (`numpy.polyfit`) sobre las unidades vendidas por
día, para pronosticar ventas a 7 días por canal.

## 14. `templates/` y `static/`
Interfaz web: pedir (`index.html`), confirmación con la ruta calculada
(`confirmacion.html`), cocina (`cocina.html`), analítica (`dashboard.html`),
historial de cliente (`cliente.html`) y laboratorio (`laboratorio.html`).

## Relación con la rúbrica de Programación Avanzada

- **Pilas y colas**: `queue_stack.py` implementa exactamente el escenario
  "Restaurante" de la diapositiva (cola = pedidos pendientes, pila =
  deshacer modificación de pedido).
- **Heap**: `dispatch.py` mantiene siempre la prioridad más alta (menor
  distancia) en la raíz, sin importar el orden de llegada.
- **Grafos**: `graph.py` modela barrios como nodos y distancias como
  aristas, con Dijkstra para elegir la ruta más corta entre varias posibles.
- **Relaciones de datos**: mínimo dos relaciones con ambas tablas
  vinculadas de verdad (pedido↔barrio y pedido↔producto), más una relación
  extra (producto↔ingrediente) para el inventario.
- **Complejidad computacional / Big O**: `algorithms.py`, `counter.py` y el
  laboratorio de la ruta `/laboratorio` retoman el análisis del proyecto
  anterior (búsqueda lineal, suma, recursividad) aplicado a un dominio real.
- **Progresiones aritméticas y regresión lineal**: `growth.py` y
  `regression.py`, ahora alimentados con el historial real de pedidos en
  vez de datos sintéticos fijos.
