# Implementation Plan for Appresso Order Analysis Application

# Goal Description

Desarrollar una aplicación (en Python) que simule una cafetería digital y permita:
- Buscar un pedido por su identificador.
- Calcular el total de productos procesados.
- Analizar la lista de pedidos mediante una función recursiva.
- Contar explícitamente el número de operaciones realizadas por cada algoritmo.
- Ejecutar los algoritmos con tamaños de entrada crecientes (10, 100, 1 000, 10 000, n) y registrar los conteos.
- Identificar el comportamiento (lineal, cuadrático, logarítmico, etc.) y expresar la complejidad con notación Big O.
- Modelar el crecimiento de pedidos de un cliente que duplica su compra cada semana y determinar cuándo alcanzará 42, 72 y 120 productos.
- Predecir ventas futuras (2.5 y 7 días) usando regresión lineal simple basada en datos simulados.

El objetivo final es generar código claro, documentación y un informe de resultados que justifique la solución más eficiente y escalable.

## User Review Required

> [!IMPORTANT] **Decisiones abiertas que requieren tu revisión**
>
> 1. **Lenguaje de programación**: Se propone Python 3.11 por su simplicidad y disponibilidad de bibliotecas (NumPy, scikit‑learn). Si prefieres otro lenguaje (e.g., JavaScript, C#) indícalo.
> 2. **Entorno de ejecución**: ¿Quieres que la aplicación sea una CLI simple o una pequeña API/GUI? Señala tu preferencia.
> 3. **Persistencia de datos**: La propuesta usa estructuras en memoria; si deseas leer/escribir pedidos desde/ hacia un archivo JSON o una base SQLite, avísanos.
> 4. **Salida esperada**: ¿ prefieres que los resultados se impriman en consola, se guarden en archivos CSV, o se generen notebooks Jupyter?
> 5. **Bibliotecas de regresión**: Proponemos usar `numpy` para cálculo manual o `scikit‑learn` para regresión lineal. Confirma cuál prefieres.

## Open Questions

> [!WARNING] **Preguntas para aclarar requerimientos**
>
> - ¿Qué formato exacto debe tener un "pedido" (campos obligatorios, tipos)?
> - ¿Deseas incluir un campo de "estado" (Solicitado, En Proceso, Entregado) en los experimentos?
> - ¿Cuál es la regla de crecimiento de pedidos del cliente (doble cada semana) y durante cuántas semanas quieres simular?
> - ¿Qué métrica de "operaciones" deseas contar (comparaciones, asignaciones, llamadas recursivas, etc.)?
> - ¿Quieres que la aplicación incluya pruebas unitarias automatizadas?

## Proposed Changes

---
### Project Structure

#### [NEW] `appresso_analysis/`
- Root directory for el proyecto.

#### [NEW] `appresso_analysis/main.py`
- Entrada principal. Genera datos de pedidos, ejecuta los algoritmos con diferentes tamaños y muestra resultados.

#### [NEW] `appresso_analysis/orders.py`
- Definición de la clase `Order` y generación de listas de pedidos simuladas.

#### [NEW] `appresso_analysis/algorithms.py`
- Funciones:
  - `find_order_linear(orders, order_id, counter)` – búsqueda lineal, cuenta comparaciones.
  - `total_products(orders, counter)` – suma total de cantidades.
  - `recursive_analyze(orders, index, counter)` – ejemplo recursivo (p.ej., suma de cantidades usando recursión).
  - Cada función recibe un objeto `counter` (instancia de `OperationCounter`) para registrar operaciones.

#### [NEW] `appresso_analysis/counter.py`
- Clase `OperationCounter` con atributos `comparisons`, `assignments`, `calls`, etc., y método `reset()`.

#### [NEW] `appresso_analysis/analysis.py`
- Funciones que ejecutan los algoritmos para tamaños `[10, 100, 1_000, 10_000, 100_000]` y guardan los conteos en una tabla (CSV o pandas DataFrame).
- Genera gráficos de crecimiento (usando `matplotlib`).

#### [NEW] `appresso_analysis/growth.py`
- Modela el patrón aritmético‑geométrico del cliente que duplica su compra cada semana.
- Función `weeks_to_reach(target, start=2, factor=2)` que devuelve la semana en que se supera o alcanza `target`.

#### [NEW] `appresso_analysis/regression.py`
- Genera datos de ventas diarias simuladas y entrena una regresión lineal para predecir ventas a 2.5 y 7 días.
- Opción de usar `numpy.linalg.lstsq` o `sklearn.linear_model.LinearRegression`.

#### [NEW] `appresso_analysis/README.md`
- Instrucciones de instalación, uso y explicación de la metodología de análisis.

---
## Verification Plan

### Automated Tests
- **Unit tests** (`tests/` directory) para cada función que verifiquen resultados y que el contador refleje operaciones esperadas en casos pequeños.
- Ejecutar `python -m unittest discover`.

### Manual Verification
- Ejecutar `python -m appresso_analysis.main` y revisar los archivos de salida:
  - `operation_counts.csv` con columnas: `size, find_comparisons, total_assignments, recursive_calls, ...`.
  - Gráficos `operations_vs_n.png` que ilustran la complejidad observada.
  - Salida de `growth.py` indicando semanas para 42, 72 y 120 productos.
  - Predicciones de ventas mostradas en consola y guardadas en `prediction.csv`.

Una vez aprobada la propuesta, procederemos a crear los archivos e implementar el código.
