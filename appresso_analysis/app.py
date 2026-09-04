import csv
import time
import uvicorn
from io import StringIO
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from appresso_analysis.algorithms import find_order_linear, recursive_analyze, total_products
from appresso_analysis.counter import OperationCounter
from appresso_analysis.growth import arithmetic_progression, weeks_to_reach
from appresso_analysis.orders import Order, generate_orders
from appresso_analysis.regression import predict_sales_numpy
from appresso_analysis.storage import init_db, insert_orders

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def build_execution_summary(size: int, find_ops: int, total_ops: int, rec_calls: int, elapsed_seconds: float) -> dict:
    """Build a human-readable summary of the execution metrics for one analysis run."""
    processed_operations = find_ops + total_ops + rec_calls
    elapsed_ms = elapsed_seconds * 1000
    return {
        "size": size,
        "find_ops": find_ops,
        "total_ops": total_ops,
        "rec_calls": rec_calls,
        "processed_operations": processed_operations,
        "elapsed_seconds": elapsed_seconds,
        "elapsed_ms": elapsed_ms,
        "message": (
            f"Tiempo real: se ejecutaron {processed_operations} operaciones sobre {size} pedidos "
            f"y el análisis tardó {elapsed_seconds:.6f} s ({elapsed_ms:.2f} ms)."
        ),
    }


def parse_csv_orders(file_obj) -> list[Order]:
    text = file_obj.read().decode("utf-8")
    reader = csv.DictReader(StringIO(text))
    grouped = {}

    for row in reader:
        order_id = int(row.get("order_id") or 0)
        if not order_id:
            continue

        payload = grouped.setdefault(
            order_id,
            {"client": row.get("client", "Cliente"), "products": [], "quantities": [], "status": row.get("status", "Solicitado")},
        )
        product = row.get("product") or row.get("producto")
        qty = row.get("quantity") or row.get("cantidad")
        if product and qty:
            payload["products"].append(product)
            payload["quantities"].append(int(qty))

    orders = []
    for order_id, data in sorted(grouped.items()):
        orders.append(
            Order(
                order_id=order_id,
                client=data["client"],
                products=data["products"],
                quantities=data["quantities"],
                status=data["status"],
            )
        )
    return orders


@app.on_event("startup")
async def startup_event():
    init_db()


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
        orders = parse_csv_orders(file.file)
        data_source = "csv"
    else:
        if size is None:
            size = 100
        orders = generate_orders(size)

    insert_orders(orders)

    start_time = time.perf_counter()
    counter = OperationCounter()
    target_id = orders[0].order_id if orders else 0
    find_order_linear(orders, target_id, counter)
    find_ops = counter.comparisons

    counter.reset()
    total_products(orders, counter)
    total_ops = counter.additions

    counter.reset()
    recursive_analyze(orders, 0, counter)
    rec_calls = counter.calls
    rec_adds = counter.additions
    elapsed_seconds = time.perf_counter() - start_time

    execution_summary = build_execution_summary(
        size=len(orders),
        find_ops=find_ops,
        total_ops=total_ops,
        rec_calls=rec_calls,
        elapsed_seconds=elapsed_seconds,
    )

    growth_start = 2
    growth_difference = 2
    growth_weeks = {
        target: weeks_to_reach(target, start=growth_start, difference=growth_difference)
        for target in [42, 72, 120]
    }
    progression = arithmetic_progression(growth_start, growth_difference, terms=5)

    daily_totals = [
        order.total_quantity() if isinstance(order, Order) else sum(order["quantities"])
        for order in orders
    ]

    pred_2_5 = predict_sales_numpy(daily_totals, days_ahead=2.5)
    pred_7 = predict_sales_numpy(daily_totals, days_ahead=7)

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
