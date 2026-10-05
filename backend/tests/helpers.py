import numpy as np


def serie_normale(rng: np.random.Generator, n: int) -> np.ndarray:
    return np.column_stack(
        [
            rng.normal(23, 0.5, n),
            rng.normal(50, 2, n),
            rng.integers(1100, 1301, n).astype(float),
        ]
    )
