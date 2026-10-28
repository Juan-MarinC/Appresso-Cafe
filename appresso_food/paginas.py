"""Páginas HTML de la app de comidas: pedir, cocina, dashboard, cliente y laboratorio."""

import itertools
import time
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from appresso_food.nucleo import mapa, ranking, runtime, storage
from appresso_food.nucleo.algorithms import find_order_linear, recursive_total_units, total_units_sold
from appresso_food.nucleo.counter import OperationCounter
from appresso_food.nucleo.demo_data import generate_demo_orders
from appresso_food.nucleo.graph import RESTAURANT_NODE
from appresso_food.nucleo.growth import arithmetic_progression, infer_weekly_increase, weeks_to_reach
from appresso_food.nucleo.models import CHANNEL_DOMICILIO, CHANNEL_LOCAL, STATUS_ENTREGADO, OrderItem
from appresso_food.nucleo.regression import predict_sales_numpy
from appresso_food.nucleo.runtime import CoverageError
from appresso_food.web import templates

router = APIRouter()

SERVED_BY_COOKIE = "appresso_served_by"

# Fotos en static/img/menu (créditos en CREDITOS.md); un producto sin foto muestra el emoji de su categoría.
FOTOS_MENU = {
    "Papas Fritas": "papas-fritas", "Papas con Queso": "papas-con-queso", "Gaseosa": "gaseosa",
    "Malteada": "malteada", "Hamburguesa Clásica": "hamburguesa-clasica", "Hamburguesa Doble": "hamburguesa-doble",
    "Perro Caliente": "perro-caliente", "Pizza Personal": "pizza-personal", "Alitas BBQ x6": "alitas-bbq",
    "Ensalada César": "ensalada-cesar",
}

# Combos que se piden con gestos (1 a 4 dedos). Se muestran solo los que tienen todos sus productos en el menú.
COMBOS_GESTOS = [
    ("Combo clásico", [("Hamburguesa Clásica", 1), ("Papas Fritas", 1), ("Gaseosa", 1)]),
    ("Combo doble", [("Hamburguesa Doble", 1), ("Papas con Queso", 1), ("Malteada", 1)]),
    ("Combo perro", [("Perro Caliente", 1), ("Papas Fritas", 1), ("Gaseosa", 1)]),
    ("Combo pizza", [("Pizza Personal", 1), ("Gaseosa", 1)]),
]


def _combos(products) -> list:
    por_nombre = {p.name: p for p in products}
    combos = []
    for nombre, items in COMBOS_GESTOS:
        if all(producto in por_nombre for producto, _ in items):
            lineas = [(por_nombre[producto], cantidad) for producto, cantidad in items]
            combos.append({
                "numero": len(combos) + 1,
                "nombre": nombre,
                "lineas": lineas,
                "total": sum(p.price * cantidad for p, cantidad in lineas),
                "foto": FOTOS_MENU.get(items[0][0]),
            })
    return combos


def _common_context(request: Request) -> dict:
    top = ranking.most_ordered(5)
    return {
        "request": request,
        "products": storage.get_products(),
        "fotos": FOTOS_MENU,
        "neighborhoods": storage.get_neighborhood_names(),
        "top_products": top,
        "popular_product_names": {name for name, _ in top},
        "served_by": request.cookies.get(SERVED_BY_COOKIE, ""),
    }


@router.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", _common_context(request))


@router.get("/gestos")
async def gesture_order(request: Request):
    """Pedido de combos con gestos de la mano (ml5.js en el navegador); envía el mismo formulario a /pedidos."""
    context = _common_context(request)
    context["combos"] = _combos(context["products"])
    return templates.TemplateResponse("gestos.html", context)


# --- Pantalla de turnos: lo que se prepara y lo que ya se puede recoger en el mostrador ---
LISTOS_EN_PANTALLA = 6


def _turno(order) -> dict:
    return {"numero": order.order_id, "cliente": (order.client or "").split(" ")[0]}  # solo el primer nombre en pantalla


@router.get("/turnos")
async def turns_page(request: Request):
    return templates.TemplateResponse("turnos.html", {"request": request})


@router.get("/api/turnos")
async def turns():
    """Pedidos del local: los que esperan en cocina y los últimos de hoy que cocina ya marcó como entregados."""
    return {
        "preparando": [_turno(o) for o in storage.get_pending_orders() if o.channel == CHANNEL_LOCAL],
        "listos": [_turno(o) for o in storage.get_orders_by_status(
            STATUS_ENTREGADO, CHANNEL_LOCAL, date.today().isoformat(), LISTOS_EN_PANTALLA)],  # solo los de hoy
    }


# --- Avisos de ayuda desde el kiosko de gestos hacia cocina ---
# shortcut: viven en memoria, se pierden al reiniciar y no se comparten entre procesos; pasar a una tabla si se usan varios workers.
_avisos_ayuda: List[dict] = []
_ids_aviso = itertools.count(1)
AYUDA_SIN_REPETIR_S = 30  # un mismo gesto sostenido no debe llenar cocina de avisos


def _aviso_publico(aviso: dict, ahora: float) -> dict:
    return {"id": aviso["id"], "creado": aviso["creado"], "hace_segundos": int(ahora - aviso["ts"])}


@router.post("/api/ayuda", status_code=201)
async def ask_for_help():
    """Un cliente pide ayuda desde /gestos (palma abierta o botón)."""
    ahora = time.time()
    reciente = next((a for a in _avisos_ayuda if ahora - a["ts"] < AYUDA_SIN_REPETIR_S), None)
    if reciente:
        return JSONResponse(_aviso_publico(reciente, ahora), status_code=200)
    aviso = {"id": next(_ids_aviso), "creado": datetime.now().isoformat(timespec="seconds"), "ts": ahora}
    _avisos_ayuda.append(aviso)
    return _aviso_publico(aviso, ahora)


@router.get("/api/ayuda")
async def pending_help():
    ahora = time.time()
    return [_aviso_publico(a, ahora) for a in _avisos_ayuda]


@router.post("/api/ayuda/{aviso_id}/atender")
async def attend_help(aviso_id: int):
    aviso = next((a for a in _avisos_ayuda if a["id"] == aviso_id), None)
    if aviso is None:
        raise HTTPException(status_code=404, detail=f"No hay un aviso de ayuda pendiente con id {aviso_id}.")
    _avisos_ayuda.remove(aviso)
    return {"ok": True, "id": aviso_id}


@router.post("/pedidos")
async def create_order(
    request: Request,
    client: str = Form(...),
    channel: str = Form(...),
    neighborhood: Optional[str] = Form(None),
    served_by: str = Form(""),
):
    form = await request.form()
    product_ids = form.getlist("product_id")
    quantities = form.getlist("quantity")

    items = []
    for product_id_raw, quantity_raw in zip(product_ids, quantities):
        quantity = int(quantity_raw or 0)
        if quantity <= 0:
            continue
        product = storage.get_product(int(product_id_raw))
        if product:
            items.append(OrderItem(product_id=product.id, product_name=product.name, quantity=quantity, unit_price=product.price))

    context = _common_context(request)

    if not items:
        context["error"] = "Selecciona al menos un producto con cantidad mayor a cero."
        return templates.TemplateResponse("index.html", context, status_code=400)

    try:
        result = runtime.place_order(
            client=client or "Cliente",
            channel=channel,
            neighborhood=neighborhood if channel == CHANNEL_DOMICILIO else None,
            items=items,
            served_by=served_by or None,
        )
    except CoverageError as exc:
        context["error"] = str(exc)
        return templates.TemplateResponse("index.html", context, status_code=400)

    response = templates.TemplateResponse(
        "confirmacion.html",
        {
            "request": request,
            "order": result.order,
            "warnings": result.warnings,
            "top_products": ranking.most_ordered(5),
        },
    )
    if served_by:
        response.set_cookie(SERVED_BY_COOKIE, served_by, max_age=60 * 60 * 24 * 30)
    return response


@router.get("/api/domicilios/mapa")
async def delivery_map():
    return mapa.datos_mapa()


@router.get("/api/domicilios/ruta")
async def delivery_route(barrio: str):
    resultado = mapa.ruta_a(barrio)
    if resultado is None:
        return JSONResponse({"ok": False, "motivo": "FUERA_DE_COBERTURA", "mensaje": f"{barrio} no está en la zona de cobertura."}, status_code=404)
    return resultado


@router.get("/cocina")
async def kitchen(request: Request):
    pending_orders = [storage.get_order(order_id) for order_id in runtime.pending_queue.as_list()]
    dispatch_list = runtime.dispatch_heap.as_priority_list()
    undo_preview = runtime.undo_stack.peek()
    return templates.TemplateResponse(
        "cocina.html",
        {
            "request": request,
            "pending_orders": [o for o in pending_orders if o],
            "dispatch_list": dispatch_list,
            "undo_preview": undo_preview,
        },
    )


@router.post("/cocina/atender")
async def kitchen_advance(request: Request):
    runtime.advance_pending()
    return RedirectResponse("/cocina", status_code=303)


@router.post("/cocina/despachar")
async def kitchen_dispatch(request: Request):
    runtime.dispatch_next_delivery()
    return RedirectResponse("/cocina", status_code=303)


@router.post("/cocina/deshacer")
async def kitchen_undo(request: Request):
    runtime.undo_last()
    return RedirectResponse("/cocina", status_code=303)


@router.get("/dashboard")
async def dashboard(request: Request):
    channel_totals = ranking.channel_comparison()
    local_daily = storage.daily_totals(CHANNEL_LOCAL)
    domicilio_daily = storage.daily_totals(CHANNEL_DOMICILIO)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "top_products": ranking.most_ordered(8),
            "top_by_neighborhood": ranking.most_ordered_by_neighborhood(),
            "channel_totals": channel_totals,
            "graph_edges": storage.get_graph_edges(),
            "restaurant_node": RESTAURANT_NODE,
            "forecast_local": predict_sales_numpy(local_daily, days_ahead=7) if local_daily else None,
            "forecast_domicilio": predict_sales_numpy(domicilio_daily, days_ahead=7) if domicilio_daily else None,
        },
    )


@router.get("/clientes/{client}")
async def client_history(request: Request, client: str):
    history = storage.get_client_history(client)
    weekly_quantities = [order.total_quantity for order in history]
    difference = infer_weekly_increase(weekly_quantities) if len(weekly_quantities) >= 2 else 2
    progression = arithmetic_progression(weekly_quantities[0], difference, terms=5) if weekly_quantities else []
    growth_weeks = {
        target: weeks_to_reach(target, start=weekly_quantities[-1] if weekly_quantities else 0, difference=difference or 1)
        for target in [42, 72, 120]
    }

    return templates.TemplateResponse(
        "cliente.html",
        {
            "request": request,
            "client": client,
            "history": history,
            "progression": progression,
            "growth_weeks": growth_weeks,
            "difference": difference,
        },
    )


@router.get("/laboratorio")
async def lab_home(request: Request):
    return templates.TemplateResponse("laboratorio.html", {"request": request, "result": None})


@router.post("/laboratorio")
async def lab_run(request: Request, size: int = Form(100)):
    products = storage.get_products()
    neighborhoods = storage.get_neighborhood_names()
    demo_orders = generate_demo_orders(size, products, neighborhoods)

    start_time = time.perf_counter()
    counter = OperationCounter()
    target_id = demo_orders[len(demo_orders) // 2].order_id if demo_orders else 0
    find_order_linear(demo_orders, target_id, counter)
    find_ops = counter.comparisons

    counter.reset()
    total_units_sold(demo_orders, counter)
    total_ops = counter.additions

    counter.reset()
    recursive_total_units(demo_orders, counter)
    rec_calls = counter.calls
    rec_adds = counter.additions
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    result = {
        "size": size,
        "find_ops": find_ops,
        "total_ops": total_ops,
        "rec_calls": rec_calls,
        "rec_adds": rec_adds,
        "elapsed_ms": elapsed_ms,
    }

    out_path = Path("operation_counts.csv")
    out_path.write_text(
        "size,find_comparisons,total_additions,recursive_calls,recursive_additions\n"
        f"{size},{find_ops},{total_ops},{rec_calls},{rec_adds}\n",
        encoding="utf-8",
    )

    return templates.TemplateResponse("laboratorio.html", {"request": request, "result": result})


@router.get("/download/{filename}")
async def download_file(filename: str):
    file_path = Path(filename)
    if not file_path.is_file():
        return JSONResponse(content={"error": "File not found"}, status_code=404)
    return FileResponse(path=file_path, filename=filename, media_type="text/csv")
