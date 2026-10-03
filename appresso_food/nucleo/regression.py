from typing import Iterable

import numpy as np


def predict_sales_numpy(series: Iterable[float], days_ahead: float = 7) -> float:
    """Predice unidades vendidas futuras con regresión lineal simple.

    Ajusta una recta sobre la serie histórica de unidades vendidas por día
    (ver storage.daily_totals) y proyecta el valor a `days_ahead` días.
    """
    values = np.asarray(list(series), dtype=float)
    if values.size == 0:
        return 0.0
    if values.size == 1:
        return float(values[0])

    x = np.arange(values.size, dtype=float)
    slope, intercept = np.polyfit(x, values, 1)
    future_x = values.size + float(days_ahead)
    return float(slope * future_x + intercept)
