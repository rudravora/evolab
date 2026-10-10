"""CPU environment smoke test: tiny torch MLP and sklearn model on synthetic data.

Must finish in under 2 minutes. Run: python smoke_test.py
"""
import platform
import time

import numpy as np
import sklearn
import torch
import torch.nn as nn
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error


def make_data(n, d, seed):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, d)).astype(np.float32)
    y = (np.sin(x[:, 0]) + 0.5 * x[:, 1] ** 2).astype(np.float32)
    return x, y


def run_torch(x_train, y_train, x_test, y_test, steps=300):
    model = nn.Sequential(nn.Linear(2, 16), nn.Tanh(), nn.Linear(16, 1))
    n_params = sum(p.numel() for p in model.parameters())
    opt = torch.optim.Adam(model.parameters(), lr=0.01)
    loss_fn = nn.MSELoss()

    xt = torch.from_numpy(x_train)
    yt = torch.from_numpy(y_train).unsqueeze(1)

    start = time.perf_counter()
    for _ in range(steps):
        opt.zero_grad()
        pred = model(xt)
        loss = loss_fn(pred, yt)
        loss.backward()
        opt.step()
    train_s = time.perf_counter() - start

    with torch.no_grad():
        test_pred = model(torch.from_numpy(x_test)).squeeze(1).numpy()
    test_mse = float(np.mean((test_pred - y_test) ** 2))
    return test_mse, n_params, train_s


def run_sklearn(x_train, y_train, x_test, y_test):
    model = Ridge(alpha=1.0)
    start = time.perf_counter()
    model.fit(x_train, y_train)
    train_s = time.perf_counter() - start
    test_pred = model.predict(x_test)
    test_mse = mean_squared_error(y_test, test_pred)
    n_params = model.coef_.size + 1
    return test_mse, n_params, train_s


def main():
    x_train, y_train = make_data(500, 2, seed=0)
    x_test, y_test = make_data(200, 2, seed=1)

    torch_mse, torch_params, torch_s = run_torch(x_train, y_train, x_test, y_test)
    sk_mse, sk_params, sk_s = run_sklearn(x_train, y_train, x_test, y_test)

    print("=== Environment ===")
    print(f"python:  {platform.python_version()} ({platform.machine()})")
    print(f"torch:   {torch.__version__}")
    print(f"sklearn: {sklearn.__version__}")
    print()
    print("=== torch MLP ===")
    print(f"test MSE:    {torch_mse:.6f}")
    print(f"params:      {torch_params}")
    print(f"train time:  {torch_s:.3f}s")
    print()
    print("=== sklearn Ridge ===")
    print(f"test MSE:    {sk_mse:.6f}")
    print(f"params:      {sk_params}")
    print(f"train time:  {sk_s:.3f}s")


if __name__ == "__main__":
    main()
