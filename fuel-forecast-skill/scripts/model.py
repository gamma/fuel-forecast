#!/usr/bin/env python3
from __future__ import annotations
import math
from common import clamp

MODEL_VERSION = 2

FEATURE_NAMES = [
    "bias",
    "local_1d",
    "local_3d",
    "brent_eur_1d_up",
    "brent_eur_1d_down",
    "brent_eur_5d_up",
    "brent_eur_5d_down",
    "distillate_eur_1d_up",
    "distillate_eur_1d_down",
    "distillate_eur_5d_up",
    "distillate_eur_5d_down",
    "eurusd_5d",
    "news",
    "weekday_sin",
    "weekday_cos",
]

def initial_weights(h):
    local_scale = min(1.0, 0.35 + 0.22*h)
    # Rockets-and-feathers prior: increases pass through sooner; decreases
    # receive progressively more weight at longer forecast horizons.
    up_scale = min(1.0, 0.55 + 0.18*h)
    down_scale = min(0.85, 0.15 + 0.15*h)
    return [
        0.0,                       # bias
        1.6*local_scale,           # local 1d momentum
        2.0*local_scale,           # local 3d momentum
        0.9*up_scale,              # Brent EUR 1d rise
        0.9*down_scale,            # Brent EUR 1d fall (slower)
        1.4*up_scale,              # Brent EUR 5d rise
        1.4*down_scale,            # Brent EUR 5d fall (slower)
        1.6*up_scale,              # distillate EUR 1d rise
        1.6*down_scale,            # distillate EUR 1d fall (slower)
        4.0*up_scale,              # distillate EUR 5d rise
        4.0*down_scale,            # distillate EUR 5d fall (slower)
        0.0,                       # residual FX lag; EUR already converted
        2.2*local_scale,           # residual news shock
        0.15, 0.15,                # weak weekday seasonality
    ]


def split_change(value, scale):
    value = float(value or 0.0)
    normalized = clamp(value / scale, -2.0, 2.0)
    return max(0.0, normalized), min(0.0, normalized)


def feature_vector(today, local1_ct=0.0, local3_ct=0.0,
                   brent_eur_d1=0.0, brent_eur_d5=0.0,
                   distillate_eur_d1=0.0, distillate_eur_d5=0.0,
                   eurusd_d5=0.0, news_score=0.0):
    from datetime import date
    brent1_up, brent1_down = split_change(brent_eur_d1, 5.0)
    brent5_up, brent5_down = split_change(brent_eur_d5, 10.0)
    dist1_up, dist1_down = split_change(distillate_eur_d1, 5.0)
    dist5_up, dist5_down = split_change(distillate_eur_d5, 10.0)
    weekday = date.fromisoformat(today).weekday()
    return [
        1.0,
        clamp(float(local1_ct) / 5.0, -2.0, 2.0),
        clamp(float(local3_ct) / 5.0, -2.0, 2.0),
        brent1_up,
        brent1_down,
        brent5_up,
        brent5_down,
        dist1_up,
        dist1_down,
        dist5_up,
        dist5_down,
        clamp(float(eurusd_d5 or 0.0) / 3.0, -2.0, 2.0),
        clamp(float(news_score or 0.0) / 2.0, -1.5, 1.5),
        math.sin(2*math.pi*weekday/7.0),
        math.cos(2*math.pi*weekday/7.0),
    ]

def new_model(h):
    return {
        "version": MODEL_VERSION,
        "horizon": h,
        "feature_names": FEATURE_NAMES,
        "weights": initial_weights(h),
        "samples": 0,
        "bootstrap_samples": 0,
        "mae_ema_ct": 2.5 + 0.35*h,
        "direction_hits": 0,
        "direction_total": 0,
    }


def is_compatible(m):
    return (
        isinstance(m, dict)
        and m.get("version") == MODEL_VERSION
        and m.get("feature_names") == FEATURE_NAMES
        and len(m.get("weights", [])) == len(FEATURE_NAMES)
    )

def predict(m, x):
    if len(m.get("weights", [])) != len(x):
        raise ValueError("Model/feature length mismatch")
    return clamp(sum(w*v for w,v in zip(m["weights"], x)), -15.0, 15.0)

def update(m, x, actual_delta_ct, predicted_delta_ct=None, lr=0.10):
    pred = predict(m, x) if predicted_delta_ct is None else predicted_delta_ct
    err = clamp(actual_delta_ct - pred, -10.0, 10.0)
    norm = 0.35 + sum(v*v for v in x)
    step = lr * err / norm
    m["weights"] = [w*0.999 + step*v for w,v in zip(m["weights"], x)]
    m["samples"] += 1
    ae = abs(actual_delta_ct - pred)
    m["mae_ema_ct"] = 0.88*m.get("mae_ema_ct", 3.0) + 0.12*ae
    if abs(actual_delta_ct) >= 0.5:
        m["direction_total"] += 1
        if (actual_delta_ct > 0) == (pred > 0):
            m["direction_hits"] += 1
    return err


def _solve(matrix, vector):
    """Solve a small dense linear system with pivoted Gauss-Jordan."""
    n = len(vector)
    augmented = [list(matrix[i]) + [float(vector[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            raise ValueError("Singular calibration matrix")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        divisor = augmented[col][col]
        augmented[col] = [value / divisor for value in augmented[col]]
        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            if factor:
                augmented[row] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(augmented[row], augmented[col])
                ]
    return [augmented[i][-1] for i in range(n)]


def ridge_weights(examples, h, penalty=20.0):
    """Fit around the asymmetric prior instead of around zero."""
    prior = initial_weights(h)
    size = len(FEATURE_NAMES)
    matrix = [[0.0] * size for _ in range(size)]
    vector = [penalty * value for value in prior]
    for i in range(size):
        matrix[i][i] = penalty
    for x, target in examples:
        if len(x) != size:
            continue
        for i in range(size):
            vector[i] += x[i] * target
            for j in range(size):
                matrix[i][j] += x[i] * x[j]
    return _solve(matrix, vector)


def constrain_bootstrap_asymmetry(weights, h):
    """Project historical start weights onto plausible pass-through signs.

    Both split features retain their original sign: rise features are positive,
    fall features are negative. Their coefficients therefore need to be
    non-negative. The shorter the horizon, the smaller the allowed fall/rise
    coefficient ratio (the feathers lag).
    """
    constrained = list(weights)
    positions = {name: i for i, name in enumerate(FEATURE_NAMES)}
    ratio = {1: 0.55, 2: 0.75, 3: 0.90}.get(h, 1.0)
    for prefix in ("brent_eur_1d", "brent_eur_5d",
                   "distillate_eur_1d", "distillate_eur_5d"):
        up = positions[prefix + "_up"]
        down = positions[prefix + "_down"]
        constrained[up] = max(0.0, constrained[up])
        constrained[down] = max(0.0, constrained[down])
        constrained[down] = min(constrained[down], constrained[up] * ratio)
    return constrained


def calibration_metrics(weights, examples):
    if not examples:
        return {"mae_ct": None, "direction_hits": 0, "direction_total": 0}
    errors = []
    hits = total = 0
    for x, target in examples:
        predicted = clamp(sum(w*v for w, v in zip(weights, x)), -15.0, 15.0)
        errors.append(abs(target - predicted))
        if abs(target) >= 0.5:
            total += 1
            if (target > 0) == (predicted > 0):
                hits += 1
    return {
        "mae_ct": sum(errors) / len(errors),
        "direction_hits": hits,
        "direction_total": total,
    }

def confidence(m):
    samples = m.get("samples", 0)
    bootstrap_samples = m.get("bootstrap_samples", 0)
    mae = m.get("mae_ema_ct", 3.0)
    # Historical tankzeit noon rows are useful priors but not equivalent to
    # true local 11:50 observations, so their confidence contribution is capped.
    effective_samples = samples + min(18.0, bootstrap_samples * 0.12)
    sample_factor = min(1.0, 0.35 + effective_samples/40.0)
    error_factor = max(0.15, min(1.0, 1.0 - mae/8.0))
    score = max(0.20, min(0.90, 0.30 + 0.35*sample_factor + 0.35*error_factor))
    # Do not present a noon/bootstrap calibration as mature personalized 11:50
    # learning. Real observations progressively lift this ceiling.
    base_cap = 0.62 if bootstrap_samples else 0.55
    live_cap = min(0.90, base_cap + 0.28 * min(1.0, samples / 40.0))
    return min(score, live_cap)
