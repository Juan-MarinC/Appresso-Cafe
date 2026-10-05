"""Punto de entrada: arma la app FastAPI y conecta los módulos.

    python -m uvicorn appresso_food.app:app --host 0.0.0.0 --port 8000
"""

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from appresso_food import paginas
from appresso_food.antifraude import fraud_routes
from appresso_food.api import capacitacion_api, compat, http_log, productos_api
from appresso_food.nucleo import runtime, storage
from appresso_food.web import BASE_DIR, STATIC_DIR

app = FastAPI(title="Appresso Food")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(paginas.router)
app.include_router(fraud_routes.router)
app.include_router(productos_api.router)
app.include_router(capacitacion_api.router)
compat.install(app)  # CORS y HEAD para clientes externos (ngrok, Telegram, Postman, páginas de otro dominio)
http_log.install(app, BASE_DIR.parent / "logs" / "http.log")  # bitácora de peticiones (/logs) y errores explicados


@app.on_event("startup")
async def startup_event():
    storage.init_db()
    runtime.init_runtime()
    fraud_routes.init_fraud()  # si MongoDB no está disponible, el resto de la app sigue funcionando


if __name__ == "__main__":
    uvicorn.run("appresso_food.app:app", host="0.0.0.0", port=8000, reload=False)
