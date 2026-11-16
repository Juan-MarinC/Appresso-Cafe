from typing import Iterable

import numpy as np


def predict_sales_numpy(series: Iterable[float], days_ahead: float = 7) -> float:
    """Predice unidades vendidas futuras con regresión lineal simple.

    Ajusta una recta sobre la serie histórica de unidades vendidas por día
    (ver storage.daily_totals) y proyecta las unidades del día que queda
    `days_ahead` días después del último. Nunca devuelve menos de 0.
    """
    values = np.asarray(list(series), dtype=float)
    if values.size == 0:
        return 0.0
    if values.size == 1:
        return float(values[0])

    x = np.arange(values.size, dtype=float)
    slope, intercept = np.polyfit(x, values, 1)
    future_x = values.size - 1 + float(days_ahead)  # el último día de la serie es x = n - 1
    return max(0.0, float(slope * future_x + intercept))
