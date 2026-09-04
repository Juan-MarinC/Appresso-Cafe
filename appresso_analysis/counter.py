class ContadorOperaciones:
    """Registra operaciones primitivas para analizar la complejidad."""
    def __init__(self):
        self.comparaciones = 0
        self.sumas = 0
        self.llamadas = 0

    def reiniciar(self):
        self.comparaciones = 0
        self.sumas = 0
        self.llamadas = 0
