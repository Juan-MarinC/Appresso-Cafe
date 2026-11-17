# Imagen de Appresso Food: FastAPI + uvicorn. MongoDB va en su propio contenedor (docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APPRESSO_DB_PATH=/data/appresso_food.db

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY appresso_food ./appresso_food

# Usuario sin privilegios; las carpetas que se escriben existen antes para que los volúmenes hereden el dueño.
RUN useradd --create-home appresso \
    && mkdir -p /data /app/logs /app/appresso_food/datos_privados \
    && chown -R appresso /data /app/logs /app/appresso_food/datos_privados /app/appresso_food/static/modelos/gestos
USER appresso

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# Un solo proceso: la ventana deslizante antifraude vive en memoria.
# --forwarded-allow-ips: ngrok corre fuera del contenedor y llega por la red interna de Docker. Solo se confía en esas
# redes, así uvicorn toma la IP que agregó ngrok (la real) y no la que escriba quien llama en X-Forwarded-For.
# No abre permisos: gestos_api niega el token si llega cualquier cabecera de proxy.
CMD ["python", "-m", "uvicorn", "appresso_food.app:app", "--host", "0.0.0.0", "--port", "8000", \
     "--forwarded-allow-ips", "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"]
