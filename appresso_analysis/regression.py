from typing import Iterable

import numpy as np


def predecir_ventas_numpy(serie: Iterable[float], dias_adelante: float = 7) -> float:
    """Predice el siguiente valor usando regresión lineal simple.

    The function fits a line to the supplied numeric series and returns the
    estimated value after ``days_ahead`` future periods.
    """
    valores = np.asarray(list(serie), dtype=float)
    if valores.size == 0:
        return 0.0
    if valores.size == 1:
        return float(valores[0])

    posiciones = np.arange(valores.size, dtype=float)
    pendiente, intercepto = np.polyfit(posiciones, valores, 1)
    posicion_futura = valores.size + float(dias_adelante)
    return float(pendiente * posicion_futura + intercepto)
