class OperationCounter:
    """Tracks primitive operations performed by algorithms for complexity analysis.
    Fields:
        comparisons: counting conditional checks (e.g., id equality)
        additions: counting arithmetic additions (e.g., summing quantities)
        calls: counting recursive function calls
    """
    def __init__(self):
        self.comparisons = 0
        self.additions = 0
        self.calls = 0

    def reset(self):
        self.comparisons = 0
        self.additions = 0
        self.calls = 0
