# Diccionario de lógica y archivos

## 1. `app.py`

### Propósito
Es la capa principal de la aplicación web. Aquí se conectan los datos, los algoritmos, la lógica de cálculo y la vista.

### Qué hace
- crea la aplicación FastAPI
- monta los archivos estáticos
- define la ruta `/`
- define la ruta `/run`
- procesa un CSV si el usuario lo sube
- genera pedidos sintéticos si no se carga archivo
- cuenta operaciones por algoritmo
- calcula predicciones y crecimiento
- devuelve el dashboard con resultados

### Lógica clave
- `parse_csv_orders()`: convierte filas de CSV en objetos `Order`
- `run_analysis()`: eje principal del procesamiento
- `download_file()`: permite descargar el CSV generado

## 2. `orders.py`

### Propósito
Representa los pedidos que se usan en el análisis.

### Qué hace
- define la clase `Order`
- calcula el total de productos por pedido
- genera listas de pedidos aleatorias con clientes, productos y cantidades

### Lógica clave
- `Order.total_quantity()`: suma todas las cantidades del pedido
- `generate_orders()`: genera `n` órdenes simuladas

## 3. `algorithms.py`

### Propósito
Contiene los algoritmos principales del proyecto.

### Qué hace
- busca un pedido por ID
- suma cantidades en todas las órdenes
- recorre la lista para contar trabajo realizado

### Lógica clave
- `find_order_linear()`: búsqueda lineal, compara uno a uno
- `total_products()`: suma todas las cantidades
- `recursive_analyze()`: realiza un recorrido acumulativo sin provocar un error de recursión profunda

## 4. `counter.py`

### Propósito
Permite documentar el costo computacional de cada algoritmo.

### Qué hace
- cuenta comparaciones
- cuenta sumas
- cuenta llamadas

### Lógica clave
- `OperationCounter.__init__()`: inicializa contadores
- `reset()`: limpia los contadores para otra prueba

## 5. `growth.py`

### Propósito
Modela la expansión de compras por crecimiento exponencial.

### Qué hace
- toma un valor inicial
- duplica el crecimiento por semana
- calcula cuántas semanas se requieren para alcanzar una meta

### Lógica clave
- `weeks_to_reach()`: itera mientras el valor actual no supere el objetivo

## 6. `regression.py`

### Propósito
Predice valores futuros a partir de datos históricos.

### Qué hace
- convierte una lista de datos a un arreglo NumPy
- ajusta una línea a la serie
- estima el valor futuro en `n` días

### Lógica clave
- `predict_sales_numpy()`: usa regresión lineal simple con `np.polyfit`

## 7. `storage.py`

### Propósito
Guarda los pedidos en SQLite.

### Qué hace
- crea la base de datos si no existe
- inserta órdenes
- recupera órdenes desde la BD

### Lógica clave
- `init_db()`: crea la tabla `orders`
- `insert_orders()`: guarda las órdenes
- `get_all_orders()`: devuelve los registros como objetos `Order`

## 8. `templates/index.html`

### Propósito
Página inicial de la app.

### Qué hace
- permite elegir el tamaño del dataset
- permite subir un CSV
- lanza la ejecución del análisis

## 9. `templates/results.html`

### Propósito
Muestra el dashboard con los resultados del análisis.

### Qué hace
- presenta las métricas principales
- imprime comparaciones, sumas y predicción
- muestra objetivos de crecimiento
- ofrece la posibilidad de descargar CSV

## 10. `static/styles.css`

### Propósito
Estilo visual de la aplicación.

### Qué hace
- define colores, paneles, tarjetas, layout y responsive design
- hace que la interfaz se vea limpia y profesional

## 11. `requirements.txt`

### Propósito
Define las dependencias del proyecto.

### Qué hace
- instala FastAPI, Uvicorn, NumPy y otras librerías necesarias

## Resumen de la lógica general

La aplicación toma datos, los procesa con distintos algoritmos, mide operaciones, interpreta su costo y presenta todo de forma visual. La intención no es solo mostrar resultados, sino demostrar cómo cambia el comportamiento de un algoritmo cuando crece la entrada y por qué la complejidad computacional es central en la toma de decisiones de diseño.
