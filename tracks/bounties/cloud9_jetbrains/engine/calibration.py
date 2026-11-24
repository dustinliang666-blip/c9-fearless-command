"""Forward-only fitting and series-clustered evaluation for draft probabilities."""

from math import log

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from .draft_engine import (
    FEATURES, STAGES, chronological_split, draft_examples, probability, results_history,
    rolling_examples, series_windows,
)


def fit_offset(x, y, offset, *, center, penalty, bounds=None):
    """Minimize penalized Bernoulli loss with a fixed logit offset."""
    center, penalty = np.asarray(center), np.asarray(penalty)

    def objective(weights):
        logits = offset + x @ weights
        deviation = weights - center
        loss = np.sum(np.logaddexp(0, logits) - y * logits)
        gradient = x.T @ (expit(logits) - y)
        return loss + (penalty * deviation**2).sum() / 2, gradient + penalty * deviation

    fit = minimize(objective, center, jac=True, bounds=bounds, method="L-BFGS-B")
    if not fit.success:
        raise RuntimeError(f"Calibration failed: {fit.message}")
    return fit.x


def fit_pre(ratings, labels, stats):
    # Shrink the Platt intercept toward the observed training side rate and
    # the slope toward zero. Negative rating slopes would reverse the Elo order.
    side_logit = log((stats.blue_wins + 5) / (stats.games - stats.blue_wins + 5))
    if not len(labels):
        return np.array([side_logit, 0.0])
    design = np.column_stack((np.ones(len(labels)), ratings))
    return fit_offset(design, labels, 0, center=[side_logit, 0.0], penalty=[30, 12],
                      bounds=[(None, None), (0, None)])


def fit_weights(examples, pre):
    usable = [(game, rating, rows) for game, (rating, rows) in examples if rows[-1] is not None]
    if not usable:
        return np.zeros(len(FEATURES))
    stages = len(STAGES)
    matrix = np.asarray([rows[stage] for _, _, rows in usable for stage in STAGES])
    y = np.repeat([game.blue_won for game, _, _ in usable], stages)
    offset = np.repeat([pre[0] + pre[1] * rating for _, rating, _ in usable], stages)
    scale = np.maximum(matrix.std(axis=0), 0.02)
    return fit_offset(matrix / scale, y, offset, center=np.zeros(len(FEATURES)),
                      penalty=64 * stages) / scale


def gamma_for_stage(labels, base, delta):
    if not len(labels):
        return 0.0
    gamma = float(fit_offset(delta[:, None], labels, base, center=[0.0], penalty=[6.0],
                             bounds=[(0, 1)])[0])
    baseline = np.mean(np.logaddexp(0, base) - labels * base)
    candidate = base + gamma * delta
    loss = np.mean(np.logaddexp(0, candidate) - labels * candidate)
    return gamma if loss < baseline - 1e-8 else 0.0


def fit_model(windows):
    rolling = list(rolling_examples(windows))
    boundaries = sorted(set(len(windows) * index // 6 for index in range(1, 7)))
    oof = []
    for first, stop in zip(boundaries, boundaries[1:]):
        cutoff = windows[first][0]
        past = [window for window in windows[:first] if window[1] < cutoff]
        if not past:
            continue
        series = {group[0].series for _, _, group in past}
        train = [(game, features) for game, features in rolling if game.series in series]
        stats = results_history(past)
        # Each fold weights the BP features against a pre-draft offset fitted
        # before the fold. Its calibration strictly filters earlier OOF rows by
        # series completion time (< cutoff) so no unresolved outcomes leak in.
        past_oof = [row for row in oof if row[4] < cutoff]
        prior = fit_pre(
            [row[1] for row in past_oof] if past_oof else [features[0] for _, features in train],
            [row[0] for row in past_oof] if past_oof else [game.blue_won for game, _ in train],
            stats,
        )
        weights = fit_weights(train, prior)
        fold = []
        for _, series_end, group in windows[first:stop]:
            for game, (rating, rows) in draft_examples(group, stats):
                deltas = [np.dot(rows[stage], weights) if rows[stage] is not None else None for stage in STAGES]
                fold.append((game.blue_won, rating, prior[0] + prior[1] * rating, deltas, series_end))
        oof.extend(fold)

    stats = results_history(windows)
    pre = fit_pre([row[1] for row in oof], [row[0] for row in oof], stats)
    gamma = {}
    for index, stage in enumerate(STAGES):
        usable = [(y, base, delta[index]) for y, _, base, delta, _ in oof if delta[index] is not None]
        if usable:
            labels, base, deltas = np.asarray(usable).T
            gamma[str(stage)] = gamma_for_stage(labels, base, deltas)
        else:
            gamma[str(stage)] = 0.0
    return {
        "pre": {"intercept": float(pre[0]), "slope": float(pre[1])},
        "weights": fit_weights(rolling, pre).tolist(),
        "gamma": gamma,
        "games": len(rolling),
        "oof_games": len(oof),
        "oof_legal_drafts": sum(row[3][-1] is not None for row in oof),
    }, stats


def series_bootstrap(labels, predictions, series, *, replicates=2000):
    """Percentile intervals from whole-series resamples, with midrank AUC."""
    groups, inverse = np.unique(series, return_inverse=True)
    rng = np.random.default_rng(20261124)
    counts = rng.multinomial(len(groups), np.full(len(groups), 1 / len(groups)), size=replicates)
    weights = np.vstack((np.ones(len(labels)), counts[:, inverse]))
    y = np.asarray(labels)
    p = np.asarray(predictions)
    order = p.argsort(kind="stable")
    boundaries = np.r_[0, np.flatnonzero(np.diff(p[order])) + 1]
    positives = np.add.reduceat(weights[:, order] * y[order], boundaries, axis=1)
    negatives = np.add.reduceat(weights[:, order] * (1 - y[order]), boundaries, axis=1)
    pairs = positives.sum(axis=1) * negatives.sum(axis=1)
    auc = np.divide(
        (positives * (negatives.cumsum(axis=1) - negatives / 2)).sum(axis=1), pairs,
        out=np.full(len(pairs), np.nan), where=pairs > 0,
    )
    totals = weights.sum(axis=1)
    loss = -(y * np.log(p) + (1 - y) * np.log1p(-p))
    metrics = {
        "auc": auc,
        "log_loss": np.einsum("ij,j->i", weights, loss) / totals,
        "brier": np.einsum("ij,j->i", weights, (p - y) ** 2) / totals,
    }
    return {
        metric: {
            "value": float(values[0]) if np.isfinite(values[0]) else None,
            "ci95": np.quantile(samples, [0.025, 0.975]).tolist() if len(samples) else None,
        }
        for metric, values in metrics.items()
        for samples in [values[1:][np.isfinite(values[1:])]]
    }


def train_and_validate(games, *, fit_serving=True):
    windows = series_windows(games)
    train, test, cutoff = chronological_split(windows)
    fitted, stats = fit_model(train)
    stages = (0, *STAGES)
    predictions = {stage: [] for stage in stages}
    labels, series = [], []
    fallback = 0
    for _, _, group in test:
        for game, (rating, rows) in draft_examples(group, stats):
            labels.append(game.blue_won)
            series.append(game.series)
            fallback += rows[-1] is None
            for stage in stages:
                predictions[stage].append(probability(fitted, rating, rows[stage], stage))
    if not labels:
        raise ValueError("Validation contains no complete ordered drafts")

    def evaluate(probabilities):
        return series_bootstrap(labels, probabilities, series)

    blue_prior = stats.blue_wins / stats.games
    report = {
        "cutoff": cutoff.isoformat(),
        "last_train_end": max(end for _, end, _ in train).isoformat(),
        "train_series": len(train), "test_series": len(test),
        "purged_series": len(windows) - len(train) - len(test),
        "untimed_games": len(games) - sum(len(group) for _, _, group in windows),
        "train_games": fitted["games"], "test_games": len(labels),
        "blue_prior": blue_prior, "test_blue_wins": sum(labels),
        "pre_only_fallback_games": fallback,
        "oof_games": fitted["oof_games"], "oof_legal_drafts": fitted["oof_legal_drafts"],
        "gamma": fitted["gamma"],
        "coin_flip": evaluate([0.5] * len(labels)),
        "side_baseline": evaluate([blue_prior] * len(labels)),
        "draft": {str(stage): evaluate(predictions[stage]) for stage in stages},
    }
    if not fit_serving:
        return {"validation": report}
    serving, stats = fit_model(windows)
    return {
        "validation": report, "serving": serving, "as_of": max(end for _, end, _ in windows).isoformat(),
        "history": vars(stats), "features": FEATURES,
    }


def fit_historical(games, as_of, *, before=None, exclude=None):
    cutoff = min(as_of, before) if before is not None else as_of
    windows = [window for window in series_windows(games) if window[1] < cutoff and window[2][0].series != exclude]
    fitted, stats = fit_model(windows)
    return {"serving": fitted, "history": vars(stats), "as_of": as_of.isoformat(), "historical": True}
