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
- `parsear_pedidos_csv()`: convierte filas de CSV en objetos `Pedido`
- `run_analysis()`: eje principal del procesamiento
- `download_file()`: permite descargar el CSV generado

## 2. `orders.py`

### Propósito
Representa los pedidos que se usan en el análisis.

### Qué hace
- define la clase `Pedido`
- calcula el total de productos por pedido
- genera listas de pedidos aleatorias con clientes, productos y cantidades

### Lógica clave
- `Pedido.cantidad_total()`: suma todas las cantidades del pedido
- `generar_pedidos()`: genera `n` órdenes simuladas

## 3. `algorithms.py`

### Propósito
Contiene los algoritmos principales del proyecto.

### Qué hace
- busca un pedido por ID
- suma cantidades en todas las órdenes
- recorre la lista mediante recursividad para contar trabajo realizado

### Lógica clave
- `buscar_pedido_lineal()`: búsqueda lineal, compara uno a uno
- `sumar_productos()`: suma todas las cantidades
- `analizar_recursivamente()`: divide la lista y suma sus mitades mediante recursividad real

## 4. `counter.py`

### Propósito
Permite documentar el costo computacional de cada algoritmo.

### Qué hace
- cuenta comparaciones
- cuenta sumas
- cuenta llamadas

### Lógica clave
- `ContadorOperaciones.__init__()`: inicializa contadores
- `reiniciar()`: limpia los contadores para otra prueba

## 5. `growth.py`

### Propósito
Modela el aumento de compras mediante una progresión aritmética.

### Qué hace
- toma un valor inicial y una diferencia constante
- aumenta la compra por semana
- calcula cuántas semanas se requieren para alcanzar una meta

### Lógica clave
- `arithmetic_progression()`: genera valores con una diferencia constante
- `weeks_to_reach()`: itera mientras el valor actual no supere el objetivo

## 6. `regression.py`

### Propósito
Predice valores futuros a partir de datos históricos.

### Qué hace
- convierte una lista de datos a un arreglo NumPy
- ajusta una línea a la serie
- estima el valor futuro en `n` días

### Lógica clave
- `predecir_ventas_numpy()`: usa regresión lineal simple con `np.polyfit`

## 7. `storage.py`

### Propósito
Guarda los pedidos en SQLite.

### Qué hace
- crea la base de datos si no existe
- inserta órdenes
- recupera órdenes desde la BD

### Lógica clave
- `inicializar_bd()`: crea la tabla `orders`
- `insertar_pedidos()`: guarda los pedidos
- `obtener_pedidos()`: devuelve los registros como objetos `Pedido`

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

## 12. Relación con la rúbrica

### Tecnología utilizada

- **Python 3**: lenguaje principal.
- **FastAPI**: creación del servidor web y las rutas de la aplicación.
- **Jinja2**: generación de las páginas HTML del dashboard.
- **NumPy**: cálculo de la regresión lineal.
- **SQLite**: almacenamiento local de los pedidos.
- **HTML y CSS**: interfaz visual.

### Big O

La búsqueda lineal revisa los pedidos uno por uno. Su complejidad es `O(n)` en el peor caso y `O(1)` si encuentra el pedido en la primera posición.

La suma de cantidades recorre todos los productos de todos los pedidos, por lo que su costo es `O(n)` respecto al número de elementos procesados.

El análisis recursivo divide la lista en dos partes hasta llegar a pedidos individuales. El trabajo total es `O(n)` y la profundidad de la recursividad es `O(log n)`. Por eso puede procesar 25.000 pedidos sin superar el límite de llamadas de Python.

El objeto `ContadorOperaciones` permite relacionar la explicación teórica con datos observables: comparaciones, sumas y llamadas recursivas.

### Recursividad

`analizar_recursivamente()` utiliza el caso base cuando el rango está vacío o contiene un solo pedido. En los demás casos divide el rango en dos, analiza cada mitad y combina los resultados.

La idea que se puede explicar es:

1. dividir el problema original
2. resolver recursivamente cada mitad
3. sumar los resultados parciales

### Progresión aritmética

El proyecto usa una progresión aritmética con valor inicial `2` y diferencia `2`:

```text
2, 4, 6, 8, 10, ...
```

Su fórmula es `a_n = a_1 + (n - 1)d`. En este caso, cada semana se agregan dos productos. La función `weeks_to_reach()` calcula cuántas semanas hacen falta para llegar a 42, 72 y 120 productos.

Resultados actuales:

- 42 productos: 20 semanas
- 72 productos: 35 semanas
- 120 productos: 59 semanas

### Regresión lineal

`predecir_ventas_numpy()` recibe una serie de ventas, asigna una posición a cada dato y ajusta una recta mediante `np.polyfit`. Después usa esa recta para estimar ventas a 2.5 y 7 días.

La regresión no adivina un valor exacto: calcula una tendencia aproximada basada en los datos disponibles.

## 13. Guion para la sustentación

### Fase 1: presentación inicial, 5 minutos

Se puede explicar lo siguiente:

> Appresso Café es una aplicación web desarrollada en Python que simula pedidos de una cafetería y analiza el costo de varios algoritmos. El usuario puede generar una cantidad de pedidos, cargar un CSV y observar las operaciones, el tiempo de ejecución, el crecimiento de productos y una predicción de ventas.

Después se muestran la tecnología y las funcionalidades: FastAPI, HTML, CSS, NumPy, SQLite, generación de pedidos, carga de CSV y dashboard de resultados.

### Fase 1: implementaciones, entre 10 y 20 minutos

Orden recomendado para la demostración:

1. Ejecutar el proyecto y mostrar el dashboard.
2. Ejecutar el análisis con 10 pedidos y explicar los contadores.
3. Ejecutar el análisis con 25.000 pedidos y comparar el tiempo y las operaciones.
4. Explicar que búsqueda, suma y análisis tienen comportamiento `O(n)`.
5. Mostrar `analizar_recursivamente()` y explicar el caso base y la división en mitades.
6. Mostrar la progresión `2, 4, 6, 8, 10` y los objetivos semanales.
7. Mostrar las predicciones de regresión lineal para 2.5 y 7 días.

El dashboard muestra el mensaje de tiempo real con el tamaño de entrada y el número total de operaciones ejecutadas.

### Fase 2: preguntas, 5 minutos

Respuestas clave:

- **¿Por qué `O(n)`?** Porque los algoritmos principales recorren proporcionalmente los elementos de entrada.
- **¿Por qué usar recursividad?** Para dividir el problema y demostrar una solución recursiva controlada.
- **¿Qué diferencia hay entre progresión aritmética y geométrica?** En la aritmética se suma una diferencia constante; en la geométrica se multiplica por un factor constante.
- **¿Qué hace la regresión?** Ajusta una tendencia a los datos históricos para estimar valores futuros.
- **¿Cómo se verifica el funcionamiento?** Se inicia FastAPI, se ejecutan tamaños distintos y se comprueba el dashboard y los resultados.

El tiempo máximo total es de 30 minutos: 5 minutos de presentación, entre 10 y 20 minutos de implementación y 5 minutos de preguntas.
