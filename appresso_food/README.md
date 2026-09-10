# Appresso Food

Evolución de **Appresso Café** hacia un sistema de gestión para un restaurante
de comida rápida. Reutiliza la base de datos, los algoritmos y la
arquitectura del proyecto anterior (FastAPI + SQLite + Jinja2), pero cambia
por completo el dominio: ahora gestiona pedidos de comida rápida por dos
canales (local y domicilio), calcula rutas de entrega con un grafo de
barrios y prioriza despachos con un heap.

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
- `templates/`, `static/`: interfaz web.

## Cómo ejecutar la app

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r appresso_food\requirements.txt
python -m uvicorn appresso_food.app:app --host 0.0.0.0 --port 8010
```

Luego abre `http://localhost:8010/`.

## Pruebas

```powershell
python -m unittest discover -s tests
```

Cubren: Dijkstra sobre el grafo, orden del heap de despacho, comportamiento
FIFO/LIFO de la cola y la pila, los algoritmos de búsqueda/suma/recursividad,
y el flujo completo de `runtime` (crear domicilio con ruta calculada,
rechazo por cobertura, deshacer con restitución de inventario).
