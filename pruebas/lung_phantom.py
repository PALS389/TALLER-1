"""Small synthetic chest with two low-intensity lungs and external air."""
import numpy as np


def lung_phantom() -> np.ndarray:
    x, y, z = np.indices((64, 64, 64), dtype=np.float32)
    body = ((x - 32) / 26) ** 2 + ((y - 32) / 24) ** 2 + ((z - 32) / 29) ** 2 < 1
    left = ((x - 20) / 9) ** 2 + ((y - 32) / 13) ** 2 + ((z - 32) / 22) ** 2 < 1
    right = ((x - 44) / 9) ** 2 + ((y - 32) / 13) ** 2 + ((z - 32) / 22) ** 2 < 1
    volume = np.zeros((64, 64, 64), dtype=np.float32)
    volume[body] = 0.75
    volume[(left | right) & body] = 0.12
    return volume
