"""Dummy paper: toy regression with two methods, for testing the harness
end to end (experiments/tests/test_harness.py). Not a real paper -- no
paper-specific libraries, just numpy and scikit-learn which are already
pinned for the shared harness.
"""
from __future__ import annotations


def _make_data(n_samples: int, n_features: int, noise_std: float, seed: int):
    import numpy as np

    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n_samples, n_features))
    true_coef = np.arange(1, n_features + 1, dtype=float)
    y = x @ true_coef + noise_std * rng.normal(size=n_samples)
    return x, y


def run(config: dict) -> dict:
    import numpy as np
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_squared_error

    method = config["method"]
    n_samples = config.get("n_samples", 200)
    n_features = config.get("n_features", 2)
    noise_std = config.get("noise_std", 0.1)
    seed = config["seed"]

    x, y = _make_data(n_samples, n_features, noise_std, seed)
    split = int(n_samples * 0.8)
    x_train, x_test = x[:split], x[split:]
    y_train, y_test = y[:split], y[split:]

    if method == "linear":
        model = LinearRegression()
        model.fit(x_train, y_train)
        test_pred = model.predict(x_test)
        train_pred = model.predict(x_train)
        param_count = int(model.coef_.size + 1)  # weights + intercept
    elif method == "mean":
        mean_pred = float(np.mean(y_train))
        test_pred = np.full_like(y_test, mean_pred)
        train_pred = np.full_like(y_train, mean_pred)
        param_count = 1
    else:
        raise ValueError(f"unknown method for _dummy paper: {method!r}")

    return {
        "test_mse": float(mean_squared_error(y_test, test_pred)),
        "train_mse": float(mean_squared_error(y_train, train_pred)),
        "param_count": param_count,
    }
