# Appresso Café Analyzer

## Objetivo del proyecto

Esta aplicación simula una cafetería digital y permite analizar el comportamiento de diferentes algoritmos usando:

- complejidad computacional
- notación Big O
- progresiones aritméticas
- sumatorias
- regresión lineal
- recursividad (aplicada con control para evitar errores por profundidad)

El sistema genera pedidos sintéticos, ejecuta algoritmos de búsqueda y suma, mide operaciones primitivas y muestra resultados en un dashboard web.

## ¿Qué hace la app?

La aplicación permite:

1. Generar una lista de pedidos aleatoria.
2. Buscar un pedido por su identificador.
3. Sumar el total de cantidades de todos los productos.
4. Analizar la estructura de los datos usando un enfoque recursivo.
5. Medir cuántas operaciones hacen cada algoritmo.
6. Calcular cuánto tarda un cliente en llegar a cierto número de productos aumentando una cantidad fija cada semana.
7. Predecir ventas futuras con regresión lineal.
8. Mostrar todo en una interfaz web con resultados claros.

## Estructura del proyecto

- `app.py`: punto principal de la aplicación FastAPI.
- `orders.py`: definición del modelo `Order` y generación de datos sintéticos.
- `algorithms.py`: lógica de búsqueda, suma y análisis.
- `counter.py`: conteo de operaciones para justificar la complejidad.
- `growth.py`: cálculo de semanas necesarias para alcanzar una meta.
- `regression.py`: predicción con regresión lineal.
- `storage.py`: persistencia en SQLite.
- `templates/`: HTML de la interfaz.
- `static/`: archivos CSS.
- `requirements.txt`: dependencias del proyecto.

## Cómo ejecutar la app

### 1) Crear y activar el entorno virtual

En Windows PowerShell:

```powershell
cd "c:\Users\juan2\Escritorio\Appresso_cafe"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Instalar dependencias

```powershell
python -m pip install --upgrade pip
python -m pip install -r appresso_analysis\requirements.txt
```

### 3) Ejecutar la aplicación

Se recomienda usar un puerto libre, por ejemplo 8010:

```powershell
python -m uvicorn appresso_analysis.app:app --host 0.0.0.0 --port 8010
```

### 4) Abrir la app en el navegador

```text
http://localhost:8010/
```

### 5) Si el puerto 8010 está ocupado

Prueba otro puerto libre, por ejemplo:

```powershell
python -m uvicorn appresso_analysis.app:app --host 0.0.0.0 --port 8011
```

Y luego abre:

```text
http://localhost:8011/
```

## Nota para otros desarrolladores

Si alguien quiere reproducir el proyecto en otra máquina, basta con seguir estos pasos:

1. clonar o abrir el proyecto
2. crear el entorno virtual
3. activar el entorno
4. instalar las dependencias desde `appresso_analysis/requirements.txt`
5. ejecutar `uvicorn` con un puerto disponible

Esto permite ver la misma interfaz y la misma lógica del análisis con el dashboard funcional.

## Flujo de la app

- El usuario entra a la página principal.
- Puede elegir un tamaño de dataset o subir un CSV.
- El backend genera o carga los pedidos.
- Cada algoritmo cuenta operaciones.
- La app calcula crecimiento y predicción.
- Se renderiza el dashboard con resultados.

## Relación con la complejidad computacional

Los algoritmos principales tienen esta lógica:

- Búsqueda lineal: O(n)
- Suma de cantidades: O(n)
- Análisis de recorrido: O(n)
- Progresión aritmética: crecimiento lineal con diferencia constante
- Regresión lineal: se basa en una aproximación lineal sobre una serie de valores

El proyecto busca mostrar que la eficiencia no depende solo del resultado, sino también del número de operaciones y del comportamiento cuando aumenta la entrada.

## Relevancia académica

Este proyecto está diseñado para explicar claramente:

- qué hace cada algoritmo
- cómo se mide el costo
- cómo se interpreta la complejidad
- cómo diseñar un análisis de datos con enfoque computacional

## Notas finales

Se eliminó el código redundante y los artefactos no relevantes para mantener una solución más clara y defensable ante una revisión académica.
