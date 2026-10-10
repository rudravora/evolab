"""Seed every RNG the harness knows about so the same seed gives the same
result on CPU. Call seed_everything(seed) before invoking a paper's run().

Only covers CPU determinism (this project's compute target per CONTEXT.md
section 3: laptop CPU or free-tier Colab/Kaggle). GPU/CUDA determinism needs
extra torch flags this project does not currently need.
"""
import os
import random


def seed_everything(seed: int) -> None:
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass

    try:
        import torch

        torch.manual_seed(seed)
        torch.use_deterministic_algorithms(True, warn_only=True)
    except ImportError:
        pass
