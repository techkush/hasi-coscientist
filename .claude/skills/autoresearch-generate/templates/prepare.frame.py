"""
FIXED YARDSTICK — do not edit during experiments.   ({{NAME}})

This file holds the read-only parts of the experiment:
  - fixed constants (the compute budget, data location),
  - data / benchmark preparation (if any), and
  - the ground-truth measure  ({{METRIC}}, {{DIRECTION}}).

The editable approach ({{EDITABLE}}) imports from here and must NEVER recompute
the measure itself. Keeping the measure here is what stops the loop from gaming
the score.

Budget note: the loop hard-kills any run that exceeds {{TIMEOUT_MINUTES}} minute(s)
({{KILL_SECONDS}}s). TIME_BUDGET below is deliberately smaller so startup + final
evaluation fit inside the kill window — never let a run train all the way to the
kill timeout.

Usage:
    python {{READONLY}}        # one-time data/benchmark preparation (if needed)
"""

# >>> GENERATE:imports — add ONLY what the measure / data prep need (e.g. math,
#     random, numpy as np, torch). Leave empty if nothing is needed. <<<
# >>> END GENERATE <<<

# ---------------------------------------------------------------------------
# Constants (fixed, do not modify)
# ---------------------------------------------------------------------------

KILL_SECONDS = {{KILL_SECONDS}}          # hard kill: the loop aborts a run beyond this
OVERHEAD_RESERVE = {{OVERHEAD_RESERVE}}  # seconds reserved for startup + final eval
TIME_BUDGET = max({{MIN_BUDGET}}, KILL_SECONDS - OVERHEAD_RESERVE)  # compute budget a run targets
DATA_LOCATION = {{DATA_LOCATION_REPR}}   # where data lives, or None

# ---------------------------------------------------------------------------
# Data / benchmark preparation   ({{DATA_DESC}})
# ---------------------------------------------------------------------------

# >>> GENERATE:data — load/prepare the fixed data or benchmark and return what the
#     run consumes. If the spec says data is none/n/a, return None (no-op). <<<
def get_data():
    """Return the fixed data/benchmark the run consumes (or None if not needed)."""
    raise NotImplementedError("GENERATE must fill get_data() (or return None)")
# >>> END GENERATE <<<

# ---------------------------------------------------------------------------
# Measure (DO NOT CHANGE — this is the fixed metric: {{METRIC}}, {{DIRECTION}})
# ---------------------------------------------------------------------------

# >>> GENERATE:measure — compute the spec's metric deterministically. This is the
#     ground-truth scorer the editable file calls; never recompute it elsewhere.
#     Return a float. <<<
def measure(*args, **kwargs):
    """Compute {{METRIC}} ({{DIRECTION}}). Self-contained and deterministic."""
    raise NotImplementedError("GENERATE must fill measure()")
# >>> END GENERATE <<<


if __name__ == "__main__":
    # One-time prep entry point (download/build). Safe no-op if nothing to prepare.
    print(f"Compute budget: {TIME_BUDGET}s  (hard kill at {KILL_SECONDS}s)")
    # >>> GENERATE:prep-main — call get_data() to materialize data if needed; print
    #     a short readiness line. If there is no data, leave the message below. <<<
    print("Nothing to prepare. Ready to run.")
    # >>> END GENERATE <<<
