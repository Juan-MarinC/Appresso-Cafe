import csv
import time
import uvicorn
from io import StringIO
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from appresso_analysis.algorithms import analizar_recursivamente, buscar_pedido_lineal, sumar_productos
from appresso_analysis.counter import ContadorOperaciones
from appresso_analysis.growth import progresion_aritmetica, semanas_para_alcanzar
from appresso_analysis.orders import Pedido, generar_pedidos
from appresso_analysis.regression import predecir_ventas_numpy
from appresso_analysis.storage import inicializar_bd, insertar_pedidos

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def resumen_ejecucion(tamano: int, operaciones_busqueda: int, operaciones_totales: int, llamadas_recursivas: int, segundos_transcurridos: float) -> dict:
    """Construye un resumen legible de las métricas de una ejecución."""
    operaciones_procesadas = operaciones_busqueda + operaciones_totales + llamadas_recursivas
    milisegundos_transcurridos = segundos_transcurridos * 1000
    return {
        "size": tamano,
        "find_ops": operaciones_busqueda,
        "total_ops": operaciones_totales,
        "rec_calls": llamadas_recursivas,
        "processed_operations": operaciones_procesadas,
        "elapsed_seconds": segundos_transcurridos,
        "elapsed_ms": milisegundos_transcurridos,
        "message": (
            f"Tiempo real: se ejecutaron {operaciones_procesadas} operaciones sobre {tamano} pedidos "
            f"y el análisis tardó {segundos_transcurridos:.6f} s ({milisegundos_transcurridos:.2f} ms)."
        ),
    }


def parsear_pedidos_csv(archivo) -> list[Pedido]:
    texto = archivo.read().decode("utf-8")
    lector = csv.DictReader(StringIO(texto))
    agrupados = {}

    for fila in lector:
        id_pedido = int(fila.get("order_id") or 0)
        if not id_pedido:
            continue

        datos = agrupados.setdefault(
            id_pedido,
            {"cliente": fila.get("client", "Cliente"), "productos": [], "cantidades": [], "estado": fila.get("status", "Solicitado")},
        )
        producto = fila.get("product") or fila.get("producto")
        cantidad = fila.get("quantity") or fila.get("cantidad")
        if producto and cantidad:
            datos["productos"].append(producto)
            datos["cantidades"].append(int(cantidad))

    pedidos = []
    for id_pedido, datos in sorted(agrupados.items()):
        pedidos.append(
            Pedido(
                id_pedido=id_pedido,
                cliente=datos["cliente"],
                productos=datos["productos"],
                cantidades=datos["cantidades"],
                estado=datos["estado"],
            )
        )
    return pedidos


@app.on_event("startup")
async def startup_event():
    inicializar_bd()


@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/run")
async def run_analysis(
    request: Request,
    size: int = Form(None),
    file: UploadFile = File(None),
):
    orders = []
    data_source = "synthetic"

    if file is not None and file.filename:
        orders = parsear_pedidos_csv(file.file)
        data_source = "csv"
    else:
        if size is None:
            size = 100
        orders = generar_pedidos(size)

    insertar_pedidos(orders)

    start_time = time.perf_counter()
    contador = ContadorOperaciones()
    id_objetivo = orders[0].id_pedido if orders else 0
    buscar_pedido_lineal(orders, id_objetivo, contador)
    find_ops = contador.comparaciones

    contador.reiniciar()
    sumar_productos(orders, contador)
    total_ops = contador.sumas

    contador.reiniciar()
    analizar_recursivamente(orders, 0, contador)
    rec_calls = contador.llamadas
    rec_adds = contador.sumas
    elapsed_seconds = time.perf_counter() - start_time

    execution_summary = resumen_ejecucion(
        tamano=len(orders),
        operaciones_busqueda=find_ops,
        operaciones_totales=total_ops,
        llamadas_recursivas=rec_calls,
        segundos_transcurridos=elapsed_seconds,
    )

    growth_start = 2
    growth_difference = 2
    growth_weeks = {
        target: semanas_para_alcanzar(target, inicio=growth_start, diferencia=growth_difference)
        for target in [42, 72, 120]
    }
    progression = progresion_aritmetica(growth_start, growth_difference, terminos=5)

    daily_totals = [
        order.cantidad_total() if isinstance(order, Pedido) else sum(order["cantidades"])
        for order in orders
    ]

    pred_2_5 = predecir_ventas_numpy(daily_totals, dias_adelante=2.5)
    pred_7 = predecir_ventas_numpy(daily_totals, dias_adelante=7)

    output_size = len(orders)
    out_path = Path("operation_counts.csv")
    out_path.write_text(
        "size,find_comparisons,total_additions,recursive_calls,recursive_additions\n"
        f"{output_size},{find_ops},{total_ops},{rec_calls},{rec_adds}\n",
        encoding="utf-8",
    )

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "size": output_size,
            "find_ops": find_ops,
            "total_ops": total_ops,
            "rec_calls": rec_calls,
            "rec_adds": rec_adds,
            "growth_weeks": growth_weeks,
            "progression": progression,
            "pred_2_5": pred_2_5,
            "pred_7": pred_7,
            "data_source": data_source,
            "execution_summary": execution_summary,
        },
    )


@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = Path(filename)
    if not file_path.is_file():
        return JSONResponse(content={"error": "File not found"}, status_code=404)
    return FileResponse(path=file_path, filename=filename, media_type="text/csv")


if __name__ == "__main__":
    uvicorn.run("appresso_analysis.app:app", host="0.0.0.0", port=8000, reload=False)
