def progresion_aritmetica(inicio: int, diferencia: int, terminos: int) -> list[int]:
    """Devuelve los primeros valores de una progresión aritmética."""
    return [inicio + diferencia * indice for indice in range(terminos)]


def semanas_para_alcanzar(objetivo: int, inicio: int = 2, diferencia: int = 2) -> int:
    """Devuelve las semanas necesarias con un aumento semanal constante."""
    semanas = 0
    actual = inicio
    while actual < objetivo:
        actual += diferencia
        semanas += 1
    return semanas
