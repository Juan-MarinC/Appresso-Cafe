# Resumen académico — Appresso Food

## 1. Introducción

Appresso Food es la evolución de Appresso Café: pasa de ser un simulador de
complejidad computacional a un sistema funcional de gestión para un
restaurante de comida rápida, que conserva toda la lógica de análisis de
algoritmos del proyecto anterior pero la aplica sobre un negocio real de
pedidos por local y por domicilio.

## 2. Objetivo general

Gestionar pedidos de comida rápida por dos canales (local y domicilio),
calcular la ruta de entrega más corta entre el restaurante y el barrio del
cliente, priorizar qué domicilio se despacha primero, y mantener las
estructuras de pilas/colas para el flujo operativo de cocina — todo sin
perder la capacidad de justificar la complejidad computacional de los
algoritmos usados.

## 3. Alcance funcional

1. Registrar pedidos con productos, cantidades, canal y (si aplica) barrio de entrega.
2. Calcular la ruta y distancia de cada domicilio con un grafo de barrios y el algoritmo de Dijkstra.
3. Priorizar el despacho de domicilios con un heap (menor distancia = mayor prioridad).
4. Atender pedidos pendientes en orden FIFO y deshacer la última acción con una pila LIFO.
5. Rechazar automáticamente domicilios fuera de la zona de cobertura del grafo.
6. Mostrar el ranking de productos más pedidos, en general y por barrio.
7. Descontar inventario de ingredientes por cada producto vendido.
8. Consultar el historial de un cliente y proyectar su fidelización.
9. Pronosticar ventas por canal con regresión lineal.
10. Medir, en un laboratorio aparte, cuántas operaciones hacen los
    algoritmos de búsqueda/suma/recursividad cuando crece el número de
    pedidos (Big O).

## 4. Estructuras de datos y algoritmos aplicados

### 4.1 Grafos y Dijkstra
Los barrios son nodos y las distancias son aristas de un grafo no dirigido
(`graph.py`). Ante un pedido a domicilio, Dijkstra calcula la ruta de menor
distancia total entre el restaurante y el barrio, comparando automáticamente
rutas directas contra rutas por barrios intermedios — igual que decidir
entre A→B directo o A→C→D→B cuando la suma de tramos es menor.

### 4.2 Heap (cola de prioridad)
Los domicilios entran a un heap (`dispatch.py`) donde la prioridad es la
distancia calculada por el grafo. La raíz del heap es siempre el pedido que
debe salir primero, sin importar en qué orden llegaron los pedidos —
reorganizándose automáticamente en cada inserción o extracción, como pide
la diapositiva de heaps.

### 4.3 Pilas y colas
Siguiendo el escenario "Restaurante" visto en clase (cola = pedidos
pendientes, pila = deshacer modificación de pedido), `queue_stack.py`
implementa una cola FIFO para la atención en cocina y una pila LIFO que
permite deshacer la creación de un pedido, un avance de cola o un despacho.

### 4.4 Relaciones entre tablas
El modelo de datos vincula al menos dos pares de tablas de verdad:
`orders.neighborhood_id -> neighborhoods.id` (pedido↔barrio) y
`order_items` como puente entre `orders` y `products` (pedido↔producto).
Combinando ambas se obtiene, por ejemplo, el producto más pedido por barrio.
Una tercera relación (`product_ingredients`, producto↔ingrediente) sostiene
el descuento de inventario.

### 4.5 Complejidad computacional y Big O
`find_order_linear` (O(n)), `total_units_sold` (O(n)) y
`recursive_total_units` (trabajo O(n), profundidad O(log n) por divide y
vencerás) se instrumentan con `OperationCounter` para contar comparaciones,
sumas y llamadas. El laboratorio de complejidad (`/laboratorio`) permite
ejecutar estos algoritmos con 10, 100, 1.000, 10.000 o más pedidos
sintéticos y observar cómo escala el número de operaciones.

### 4.6 Progresiones aritméticas
`growth.py` aplica `a_n = a_1 + (n-1)d` para proyectar, a partir del
incremento real de pedidos de un cliente, en cuántos pedidos más alcanzará
una meta de unidades (fidelización).

### 4.7 Regresión lineal
`regression.py` ajusta una recta (`numpy.polyfit`) sobre las unidades
vendidas por día para cada canal y proyecta la demanda a 7 días.

## 5. Justificación del enfoque

Se mantuvo la arquitectura FastAPI + SQLite + Jinja2 del proyecto anterior
porque ya resolvía bien el flujo de generar, persistir y analizar pedidos;
lo que cambió fue el dominio (comida rápida en vez de café) y se agregaron
las estructuras exigidas por la clase de Programación Avanzada (grafos,
heap, pilas y colas) como funcionalidad real del negocio — no como un
ejercicio aislado. Ningún módulo del proyecto original quedó como
adorno: la búsqueda lineal ahora localiza pedidos reales en cocina, la
progresión aritmética ahora proyecta fidelización real de clientes, y la
regresión lineal ahora pronostica ventas reales por canal.

## 6. Guion para la sustentación

1. Mostrar el flujo de un pedido a domicilio y la ruta que calcula Dijkstra.
2. Mostrar cómo el heap de despacho prioriza el barrio más cercano aunque
   haya llegado después que otro pedido.
3. Mostrar la cola de pendientes y la pila de deshacer en la vista de cocina.
4. Mostrar el dashboard: ranking general, ranking por barrio (relación
   barrio↔producto) y comparación local vs. domicilio.
5. Mostrar el rechazo automático de un domicilio fuera de cobertura.
6. Mostrar el laboratorio de complejidad con 100 y 10.000 pedidos y
   explicar por qué la búsqueda y la suma son O(n).
7. Cerrar con el pronóstico de ventas y la proyección de fidelización de un cliente.
