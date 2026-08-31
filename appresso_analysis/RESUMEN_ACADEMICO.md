# Resumen académico del proyecto Appresso Café Analyzer

## 1. Introducción

El proyecto desarrollado en Python tiene como objetivo analizar el comportamiento de diferentes algoritmos aplicados a un escenario de pedidos en una cafetería. A través de un dashboard web, se simulan datos de clientes, productos y cantidades, y se evalúa cómo cada algoritmo procesa la información cuando aumenta el tamaño de la entrada.

La propuesta conecta conceptos de complejidad computacional, notación Big O, análisis de crecimiento, sumatorias y regresión lineal en una solución práctica y visual. Esto permite no solo generar resultados, sino también interpretarlos desde una perspectiva teórica y aplicada.

## 2. Objetivo general

El objetivo del sistema es mostrar cómo cambian las operaciones necesarias para resolver una tarea cuando el volumen de datos aumenta. En particular, se analizan:

- búsqueda de un pedido por identificador
- suma total de productos procesados
- recorrido de datos por estructura recursiva/iterativa
- modelado del crecimiento de compras por semana
- predicción de ventas futuras

## 3. Alcance funcional

La aplicación permite:

1. Generar pedidos sintéticos con información realista.
2. Ejecutar algoritmos sobre listas de diferentes tamaños.
3. Contar las operaciones realizadas por cada algoritmo.
4. Interpretar el comportamiento con base en la complejidad computacional.
5. Visualizar resultados en una interfaz web.
6. Cargar un archivo CSV con datos reales o personalizados.
7. Descargar la información generada en formato CSV.

## 4. Estructura lógica del proyecto

El proyecto está dividido en módulos con fines claros:

- `orders.py`: define la entidad `Order` y genera los pedidos.
- `algorithms.py`: contiene la lógica principal del análisis.
- `counter.py`: mide operaciones primitivas como comparaciones, sumas y llamadas.
- `growth.py`: modela el crecimiento por duplicación semanal.
- `regression.py`: realiza predicción lineal usando NumPy.
- `storage.py`: almacena datos en SQLite.
- `app.py`: integra el sistema completo con FastAPI.
- `templates/` y `static/`: componentes web para la interfaz.

## 5. Algoritmos analizados

### 5.1 Búsqueda lineal

La búsqueda por identificador recorre la lista elemento por elemento hasta encontrar el pedido solicitado. Esta estrategia es directa y fácil de implementar, pero su costo aumenta conforme crece la cantidad de registros.

Su complejidad es:

- Tiempo: O(n)
- Espacio: O(1)

Esto se refleja en el número de comparaciones realizadas entre cada elemento y el ID buscado.

### 5.2 Suma total de productos

El algoritmo recorre cada pedido y cada cantidad asociada para obtener el total acumulado. En este caso, el costo también depende directamente del número de elementos procesados.

Su complejidad es:

- Tiempo: O(n)
- Espacio: O(1)

Se mide con la cantidad de sumas acumuladas durante la ejecución.

### 5.3 Análisis recursivo

El proyecto incluye un análisis del recorrido de datos a través de una estructura recursiva controlada, evitando que el programa falle cuando se trabaja con conjuntos grandes. Esto es importante porque la recursión directa, sin control, puede provocar errores por profundidad máxima.

La solución implementada mantiene la idea del análisis recursivo, pero la ejecuta de forma segura para mantener la funcionalidad incluso en tamaños grandes.

## 6. Complejidad computacional y Big O

La notación Big O permite describir el crecimiento del costo computacional de un algoritmo frente al tamaño de la entrada. En este proyecto, los análisis principales muestran una escala lineal, lo que significa que el tiempo de ejecución crece proporcionalmente con el número de pedidos.

Esto es significativo porque demuestra que el sistema se comporta de manera predecible y escalable para cantidades moderadas y grandes de datos. La capacidad de contar operaciones ayuda a justificar la eficiencia de cada alternativa.

## 7. Modelo de crecimiento del cliente

Otra parte del proyecto aplica una progresión geométrica donde el cliente duplica su compra cada semana. Este enfoque permite modelar un crecimiento acelerado y calcular cuántas semanas se requieren para alcanzar objetivos como 42, 72 y 120 productos.

La lógica es útil para explicar conceptos de progresiones, crecimiento exponencial y análisis de tendencias. Además, hace visible la diferencia entre crecimiento lineal y crecimiento geométrico.

## 8. Predicción de ventas

La aplicación también utiliza regresión lineal para estimar ventas futuras. Esta parte del proyecto conecta el análisis computacional con un uso real de modelado predictivo.

Con una serie de valores históricos, se ajusta una línea que representa la tendencia general y se proyecta lo que podría ocurrir en días posteriores. Esto ilustra cómo la estadística y la computación se complementan en soluciones reales.

## 9. Diseño de la interfaz

La aplicación web se presenta como un dashboard de complejidad, con una estética clara y funcional. Su objetivo es que el usuario pueda:

- ingresar el tamaño del conjunto de datos
- cargar un archivo CSV
- ejecutar la prueba
- observar los resultados en una sola vista
- descargar la información de salida

Esto facilita tanto la explicación académica como la experiencia de uso.

## 10. Justificación del enfoque final

Se decidió mantener un proyecto centrado en la finalidad académica. Esto implica conservar únicamente los elementos que apoyan directamente la explicación de análisis de algoritmos, crecimiento y predicción. Se eliminaron elementos redundantes y otros artefactos que no aportaban valor al objetivo principal.

La ventaja de esta decisión es que la solución:

- es más clara para revisión
- presenta mejor estructura modular
- responde al objetivo del curso
- evita ruido innecesario en la explicación
- tiene una narrativa coherente desde la lógica hasta la interfaz

## 11. Conclusión

Este proyecto cumple con el propósito de aplicar conceptos fundamentales de algoritmia y análisis de complejidad a un caso práctico de una cafetería digital. A través de búsqueda, suma, recursividad, crecimiento y predicción, se demuestra cómo la eficiencia de un algoritmo depende de cómo se procesa la información y del tamaño de la entrada.

Además, la solución combina teoría con implementación funcional, lo que la hace apropiada tanto para una demostración técnica como para una explicación académica. La versión final está enfocada, funcional y lista para ser presentada con claridad y rigor.
