from typing import Iterable

import numpy as np


def predict_sales_numpy(series: Iterable[float], days_ahead: float = 7) -> float:
    """Predict the next value using simple linear regression.

    The function fits a line to the supplied numeric series and returns the
    estimated value after ``days_ahead`` future periods.
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
