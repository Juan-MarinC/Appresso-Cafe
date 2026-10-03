# Resumen de cambios

## 1. Organización del proyecto
- Código separado en `appresso_food/nucleo/` (restaurante y algoritmos), `antifraude/` (transacciones, ventana, hash, MongoDB) y `api/` (API REST y bitácora `/logs`).
- `app.py` solo arranca la app; las páginas HTML están en `paginas.py`; `web.py` guarda plantillas y estáticos.
- `templates/base.html` (cabecera, menú, pie) que reutilizan todas las páginas.
- Estáticos en `static/css` y `static/js`. `README.md` y `requirements.txt` en la raíz; documentos en `docs/`.
- Comando de arranque igual: `python -m uvicorn appresso_food.app:app --host 0.0.0.0 --port 8000`.

## 2. Diseño (tomado de CAPRICHO)
- Paleta vino/crema/caramelo, tipografías Fraunces y Barlow, barra superior rayada, menú en píldoras.
- Portada con ilustración (`static/img/hero.svg`) y iconos de comida en el menú.
- Mapa de domicilios (grafo de barrios con Dijkstra) en Pedir y en Dashboard: `nucleo/mapa.py`, `static/js/mapa.js`, `templates/_mapa.html`, endpoints `/api/domicilios/mapa` y `/api/domicilios/ruta`.

## 3. Transacciones (error 400 y flujo de erróneas)
- Rutas alias: `POST /api/transactions`, `/api/transacciones`, `/transacciones` (con y sin `/` final).
- Lee el cuerpo en UTF-8, UTF-8 con BOM, UTF-16/32, JSON doblemente codificado, una transacción por línea, comillas simples y formularios. Una lista se procesa como lote.
- Modo "generador externo" (activo por defecto): `user` como correo o id simple, método de pago de texto libre, hash SHA-256 sin llave además del HMAC.
- Toda petición recibida responde 201 y queda clasificada en el cuerpo: buena (`VALID`), sospechosa (`SUSPICIOUS`) o errónea (`REJECTED`, `clasificacion: ERRONEA`). Solo el ID repetido responde 409.
- Cuarentena (`transacciones_invalidas`): se guarda la petición original, el motivo, campos que faltan o sobran, IP y encabezados. Se puede reprocesar o descartar:
  `GET /api/transactions/invalid`, `GET .../invalid/{id}`, `POST .../invalid/{id}/reprocess`, `POST .../invalid/{id}/discard`.
- Sin MongoDB la app usa memoria (los datos se pierden al reiniciar) y avisa con un banner.
- Variables de entorno nuevas: `APPRESSO_LENIENT_INPUTS` y `APPRESSO_REJECTED_AS_201` (ambas `true` por defecto; con `false` vuelve el comportamiento estricto).

## 4. Dashboard antifraude (`/antifraude`)
- Panel "Qué llegó": buenas, sospechosas y erróneas con cantidad, porcentaje y barra, por Hoy/Semana/Mes.
- Panel "Peticiones erróneas en cuarentena": ver original, reprocesar, descartar, filtrar por estado.

## 5. Pruebas
- `python -m unittest discover -s tests` → 101 pruebas (antes 84). Nuevas en `tests/test_invalid_flow.py`.

## Pendiente / a tener en cuenta
- La cuarentena y los alias se probaron con la base en memoria y con la API; falta probarlos contra un MongoDB real.
- Se pueden borrar a mano (sobran): `.system_generated/`, `logs/`, `appresso_food/appresso_food.db` (se recrea sola).
