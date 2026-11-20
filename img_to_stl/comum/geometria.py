"""Funções geométricas pequenas, compartilhadas pelas etapas."""
import numpy as np


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
