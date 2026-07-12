"""
Fix #6: the scoring weights (safety 40 / liquidity 25 / holders 20 / social 15
from config.py) were hardcoded guesses that were never checked against real
outcomes. This module lets the actual win/loss data (now collected via
feedback_tracker.record_signal + refresh_open_signals) periodically nudge the
weights toward whatever components actually discriminate wins from losses.

Weights are kept in data/score_weights.json, not in config.py, and always
fall back to the config.py defaults if that file doesn't exist yet or there
isn't enough data. Adjustments are small per run and bounded, so the system
can't swing wildly on a handful of trades.
"""
import json
import logging
from pathlib import Path
from typing import Dict

from config import (
    SCORE_SAFETY_WEIGHT,
    SCORE_LIQUIDITY_WEIGHT,
    SCORE_HOLDER_WEIGHT,
    SCORE_SOCIAL_WEIGHT,
)
from core.feedback_tracker import MIN_CLOSED_SIGNALS_FOR_ADJUSTMENT, load_feedback

logger = logging.getLogger("memecoin-bot")

WEIGHTS_FILE = Path(__file__).parent.parent / "data" / "score_weights.json"

COMPONENTS = ("safety", "liquidity", "holders", "social")

DEFAULT_WEIGHTS = {
    "safety": SCORE_SAFETY_WEIGHT,
    "liquidity": SCORE_LIQUIDITY_WEIGHT,
    "holders": SCORE_HOLDER_WEIGHT,
    "social": SCORE_SOCIAL_WEIGHT,
}

# Bounds so no single component can be tuned away to nothing or take over
# entirely just because of a short lucky/unlucky streak.
MIN_WEIGHT = 10
MAX_WEIGHT = 50

# How much of the measured discriminative gap to actually apply each run.
# Small on purpose — this should drift slowly, not jump around per cycle.
LEARNING_RATE = 0.15


def get_current_weights() -> Dict[str, float]:
    if WEIGHTS_FILE.exists():
        try:
            data = json.loads(WEIGHTS_FILE.read_text())
            if all(k in data for k in COMPONENTS):
                return data
        except Exception:
            pass
    return dict(DEFAULT_WEIGHTS)


def _save_weights(weights: Dict[str, float]):
    WEIGHTS_FILE.parent.mkdir(exist_ok=True, parents=True)
    WEIGHTS_FILE.write_text(json.dumps(weights, indent=2))


def tune_weights_from_feedback() -> Dict:
    """Compare each component's raw 0-100 sub-score between winning and
    losing *real* trades. A component that's consistently higher on wins
    than losses is a genuine discriminator and earns a bit more weight;
    a component that doesn't separate wins from losses at all gets less."""
    feedback = load_feedback()
    signals = feedback.get("signals", [])

    real_closed = [
        s for s in signals
        if s.get("status") == "closed"
        and s.get("outcome_source") == "real_trade"
        and s.get("outcome") in ("win", "loss")
        and s.get("score_breakdown")
    ]

    current = get_current_weights()

    if len(real_closed) < MIN_CLOSED_SIGNALS_FOR_ADJUSTMENT:
        logger.info(
            f"Weight tuning skipped: only {len(real_closed)} real closed "
            f"signals with breakdown data (need {MIN_CLOSED_SIGNALS_FOR_ADJUSTMENT})"
        )
        return current

    wins = [s for s in real_closed if s["outcome"] == "win"]
    losses = [s for s in real_closed if s["outcome"] == "loss"]
    if not wins or not losses:
        return current

    gaps = {}
    for comp in COMPONENTS:
        weight_frac = max(current.get(comp, DEFAULT_WEIGHTS[comp]), 1) / 100
        # breakdown stores the *weighted* contribution (e.g. safety_w); divide
        # back out the current weight to recover the underlying 0-100 sub-score.
        win_vals = [s["score_breakdown"].get(comp, 0) / weight_frac for s in wins]
        loss_vals = [s["score_breakdown"].get(comp, 0) / weight_frac for s in losses]
        avg_win = sum(win_vals) / len(win_vals)
        avg_loss = sum(loss_vals) / len(loss_vals)
        gaps[comp] = avg_win - avg_loss  # positive = discriminates well

    new_weights = {}
    for comp in COMPONENTS:
        adjusted = current.get(comp, DEFAULT_WEIGHTS[comp]) + LEARNING_RATE * gaps[comp]
        new_weights[comp] = max(MIN_WEIGHT, min(MAX_WEIGHT, adjusted))

    # Renormalize so weights always sum to 100.
    total = sum(new_weights.values())
    new_weights = {k: round(v / total * 100, 1) for k, v in new_weights.items()}

    logger.info(f"Weight tuning: {current} -> {new_weights} (from {len(real_closed)} real trades, gaps={gaps})")
    _save_weights(new_weights)
    return new_weights
