# {{NAME}}

An autonomous research experiment. The goal is to **{{GOAL_LINE}}** ({{DIRECTION_WORD}} `{{METRIC}}` is better).

- **What is optimized:** the approach and training recipe in `{{EDITABLE}}`.
- **The measure:** `{{METRIC}}`, computed by the fixed scorer in `{{READONLY}}`.
- **Fixed:** the measure and the data/benchmark are off-limits (read-only).
- **Per run:** a compute budget of {{COMPUTE_SECONDS}}s; the loop hard-kills at {{TIMEOUT_MINUTES}} minute(s).

## Run one experiment

```bash
python {{READONLY}}     # one-time: prepare data/benchmark (if any)
{{RUNNER_COMMAND}}       # run within the budget; prints  {{RESULT_LINE}}
```

## Quick start (autonomous research)

1. `/autoresearch-setup` — creates the experiment branch and checks the data.
2. `/autoresearch-loop` — lets the loop iterate: change `{{EDITABLE}}`, run, keep if `{{METRIC}}` improves, else revert.
