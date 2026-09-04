def arithmetic_progression(start: int, difference: int, terms: int) -> list[int]:
    """Return the first values of an arithmetic progression."""
    return [start + difference * index for index in range(terms)]


def weeks_to_reach(target: int, start: int = 2, difference: int = 2) -> int:
    """Return weeks needed to reach *target* with a fixed weekly increase."""
    weeks = 0
    current = start
    while current < target:
        current += difference
        weeks += 1
    return weeks
