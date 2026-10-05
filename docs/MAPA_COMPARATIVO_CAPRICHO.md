# Mapa comparativo: Appresso Food vs CAPRICHO

| | Appresso Food (nuestro) | CAPRICHO (compañero) |
|---|---|---|
| Framework | FastAPI | Flask |
| Base de datos | SQLite (pedidos) + MongoDB (antifraude) | SQLite para todo |
| Páginas | Pedir, Cocina, Dashboard, Transacciones, Antifraude, Laboratorio, Logs | Tienda, Pagar, Laboratorio, Dashboard, Operación, Ingresar/Registro, Mis pedidos |
| Diseño | Ahora: paleta vino/crema/caramelo, Fraunces + Barlow, barra rayada (tomado de CAPRICHO) | Vino/crema/caramelo, logo, fotos, gráficas SVG |
| Organización | Ahora: `nucleo/`, `antifraude/`, `api/`, `templates/base.html`, `static/css|js` | `rutas/`, `servicios/`, `templates/`, `static/` |

## Qué hay en CAPRICHO que falta en el nuestro (no se tocó, solo visual y orden)

| Funcionalidad | Dónde está en CAPRICHO | Estado en el nuestro |
|---|---|---|
| Login, registro y roles (admin / cliente), scrypt, bloqueo tras 5 intentos | `seguridad.py`, `api_auth.py` | No existe |
| Token CSRF, cabeceras CSP, detección de inyección SQL | `seguridad.py` | No existe |
| Carrito y pago con precio recalculado en el servidor (`PRECIO_MANIPULADO`) | `servicios/pedidos.py`, `carrito.js`, `pagar.js` | No existe |
| Arma-tu-producto (tamaño, sabor, adiciones) | `tienda.js` | No aplica (menú fijo) |
| Mapa SVG de domicilios con tarifa por km | `mapa.js`, `servicios/domicilios.py` | Solo grafo y Dijkstra en tablas |
| Detector con ráfaga (5 en 1 s), monto atípico, reglas por franja | `servicios/detector.py` | Ventana deslizante y franjas, sin ráfaga ni monto atípico |
| Hash aceptado en varias formas (HMAC con llaves extra, SHA-256 simple) | `seguridad.py`, README | HMAC con una llave configurable |
| Índice hash O(1), merge sort para lotes | `estructuras.py` | Parcial (búsqueda lineal medida en laboratorio) |
| Respuesta 201 siempre que se registra, incluso si es fraude; resultado en el cuerpo | `api_transacciones.py` | Devuelve 422 para rechazadas |
| Script para enviar transacciones desde la terminal | `herramientas/enviar_transacciones.py` | Hay `tests/prueba_profesor.py` |
| Guía de sustentación y pruebas de seguridad | `GUIA_SUSTENTACION.md`, `tests/` | `docs/PRUEBA_CON_IA.md` |

## Qué tiene el nuestro y CAPRICHO no

- Cola FIFO + heap de despacho + pila de deshacer en pantalla de cocina.
- Inventario por ingredientes, fidelización (progresión aritmética) y pronóstico por regresión lineal.
- API de capacitación: PUT/PATCH/DELETE de productos, `/api/hash/calcular`, `/api/totales`, bitácora `/logs` con `X-Request-Id`.

## Error 400 en transacciones (pendiente)

Se revisará aparte con el prompt que enviará Juan. Pista de CAPRICHO: responde 201 aunque la transacción sea fraudulenta y reserva 400 solo para inyección SQL; el nuestro devuelve 400 para JSON mal formado y 422 para rechazos.
