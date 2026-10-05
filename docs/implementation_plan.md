# Appresso Food — historial de evolución del proyecto

Este proyecto nació como **Appresso Café Analyzer**: una app académica que
simulaba pedidos de una cafetería para analizar complejidad computacional
(Big O, recursividad, progresiones aritméticas, regresión lineal).

Se evolucionó a **Appresso Food** (paquete `appresso_food/`): un sistema de
gestión para un restaurante de comida rápida que reutiliza esa misma base
(FastAPI + SQLite + Jinja2, y los algoritmos de búsqueda/suma/recursividad)
pero la aplica a un negocio real con pedidos por local y por domicilio,
rutas calculadas con un grafo de barrios (Dijkstra), despacho priorizado
con un heap, y una cola/pila de pedidos — los temas vistos en la clase de
Programación Avanzada sobre pilas, colas, heaps y grafos.

La documentación viva del proyecto está en
[`README.md`](../README.md) (arquitectura y cómo
ejecutarlo), [`DICCIONARIO_LOGICA.md`](DICCIONARIO_LOGICA.md)
(qué hace cada módulo) y
[`RESUMEN_ACADEMICO.md`](RESUMEN_ACADEMICO.md)
(justificación académica y guion de sustentación).
