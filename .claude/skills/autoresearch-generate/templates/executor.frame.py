"""
EDITABLE APPROACH — this is the file the loop iterates on.   ({{NAME}})

GOAL: {{GOAL_LINE}}   ({{DIRECTION_WORD}} is better)

This file must always:
  - import the fixed measure + TIME_BUDGET from {{READONLY_MODULE}},
  - finish within TIME_BUDGET seconds (stop any open-ended work at the budget),
  - populate `results` with EVERY metric key, and
  - print the result block at the end EXACTLY as scaffolded (do not rename the
    metric lines) so the loop can score the run.

Everything else — the approach and its knobs — is fair game.{{SOURCE_NOTE}}
"""

import time
# >>> GENERATE:imports — add ONLY what the approach needs (e.g. numpy as np, torch). <<<
# >>> END GENERATE <<<
from {{READONLY_MODULE}} import TIME_BUDGET, measure{{DATA_IMPORT}}

# ---------------------------------------------------------------------------
# Tunable knobs (edit these directly — this is what the loop sweeps)
# ---------------------------------------------------------------------------
SEED = 42
# >>> GENERATE:knobs — hyperparameters / settings the loop will tune <<<
# >>> END GENERATE <<<

# ---------------------------------------------------------------------------
# Approach: {{BASELINE_DESC}}
# ---------------------------------------------------------------------------
# >>> GENERATE:approach — implement the baseline (the simplest reasonable start).
#     For open-ended work, stop at TIME_BUDGET. Call measure() to score; never
#     recompute the metric here. <<<
# >>> END GENERATE <<<


def main():
    t_start = time.time()

    # >>> GENERATE:run — run the approach and populate `results` with every metric
    #     key below. Stop open-ended work when time.time() - t_start >= TIME_BUDGET.
    #     Score with measure(); never recompute the metric here.
    #     Required keys: {{ALL_METRIC_KEYS}} <<<
    results = {}
    raise NotImplementedError("GENERATE must run the approach and populate results")
    # >>> END GENERATE <<<

{{AUTO_RUNTIME}}
    # --- required result block (scaffolded — keep these metric lines exactly) ---
    print("---")
{{RESULT_PRINTS}}


if __name__ == "__main__":
    main()
