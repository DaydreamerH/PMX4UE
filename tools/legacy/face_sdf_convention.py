"""Shared face-shadow threshold convention; no Blender or UE imports."""
import math

ENCODING = "linear_azimuth_v1"
POLE_EPSILON = 1e-6


def light_threshold(forward_dot, left_dot):
    """Head-plane azimuth / pi. Inputs use an orthonormal forward/left basis.

    Unlike half-Lambert this matches the baker's equally spaced angular frames.
    At the undefined overhead pole the epsilon gives a finite half-turn threshold.
    """
    if not all(math.isfinite(v) for v in (forward_dot, left_dot)):
        raise ValueError("Non-finite light projection")
    return math.atan2(max(abs(left_dot), POLE_EPSILON), forward_dot) / math.pi


def analyze_monotonicity(masks, coverage, tolerance=0.01):
    """Measure pixels that first-shadow encoding discards; never beauty approval."""
    import numpy as np
    stack = np.asarray(masks, dtype=bool)
    coverage = np.asarray(coverage, dtype=bool)
    if stack.ndim != 3 or len(stack) < 3 or coverage.shape != stack.shape[1:] or not coverage.any():
        raise ValueError("Need >=3 same-size masks and nonempty face coverage")
    if not math.isfinite(tolerance) or not 0 <= tolerance <= 1:
        raise ValueError("Invalid monotonicity tolerance")
    monotone = np.logical_and.accumulate(stack, axis=0)
    lost = stack & ~monotone & coverage[None, :, :]
    count = int(coverage.sum())
    fractions = [float(row.sum()) / count for row in lost]
    front_dark = coverage & ~stack[0]
    report = dict(encoding=ENCODING, covered_pixels=count,
                  discarded_lit_fraction_by_frame=fractions,
                  maximum_discarded_lit_fraction=max(fractions),
                  affected_coverage_fraction=float(lost.any(axis=0).sum()) / count,
                  front_unlit_coverage_fraction=float(front_dark.sum()) / count,
                  tolerance=tolerance, requires_review=max(fractions) > tolerance,
                  note="Coverage includes UV padding; inspect semantic face regions before acceptance.")
    return report, lost.any(axis=0), front_dark
