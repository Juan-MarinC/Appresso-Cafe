def weeks_to_reach(target: int, start: int = 2, factor: int = 2) -> int:
    """Return the number of weeks needed for a client to reach *target* purchases.
    The client starts at *start* purchases and doubles each week (factor).
    """
    weeks = 0
    current = start
    while current < target:
        current *= factor
        weeks += 1
    return weeks
