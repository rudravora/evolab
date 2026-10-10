# _dummy

Not a real paper. A tiny toy regression used only to test the harness end to
end (see experiments/tests/test_harness.py).

`task.py` generates synthetic linear data (`y = x @ true_coef + noise`) and
fits one of two methods:

- `linear` — scikit-learn `LinearRegression`
- `mean` — predicts the training mean (a trivial baseline)

Both are deterministic given the seed (data generation uses
`numpy.random.default_rng(seed)`; scikit-learn's `LinearRegression` has no
randomness of its own).
