---
name: persona-eval
description: Rerun and evaluate matchmaking persona benchmark sets, including batch persona search regression, hard-mode checks, result summary, and agent-feedback metrics for dating search quality.
---

# Persona Eval

Use this skill when the user wants to judge whether the current matchmaking search quality is good enough across many personas, such as:

- "把这批 persona 再跑一遍看看效果"
- "做一轮回归测试"
- "看看 hard mode 这一版有没有退化"
- "把 agent 反馈汇总成分数"
- "对比 v10 和 v11 哪版更好"

This skill is for evaluation, not live matchmaking. If the user wants to actually find candidates in the database, use `partner-search`. If the user wants to persist new persona memory into MySQL, use `persona-memory-sync`.

## Workflow

1. Pick the evaluation input.
   Use a JSON file whose items contain at least `id`, `name`, and `command`.
2. Prefer the bundle runner when you want the standard artifact trio.
   Run `python3 scripts/run_persona_eval_bundle.py --input ... --results-output ... --packets-output ... --metrics-output ...`.
3. Rerun only the search batch when you do not need packets yet.
   Run `python3 scripts/run_persona_eval.py --input ... --results-output ...`.
4. Inspect the result JSON.
   Check `returncode`, `has_match`, `candidate_count`, and `output`.
5. Generate reviewer packets separately when needed.
   Run `python3 scripts/generate_persona_packets.py --input ... --output ... --section-label ...`.
6. If agent or human review feedback exists, summarize it.
   Run `python3 scripts/summarize_agent_feedback.py --input ... --output ...`.
7. Report the conclusion.
   Separate:
   - command health
   - match coverage
   - qualitative problems
   - score changes versus the prior version

## Expected Artifacts

Typical artifact flow:

- `persona_experiment_input_*.json`: evaluation input set
- `persona_experiment_results_*.json`: rerun outputs
- `persona_agent_feedback_*.json`: agent or reviewer scoring
- `persona_agent_metrics_*.json`: aggregated feedback metrics
- `persona_agent_packets_*.md`: human-readable packets for review

Use the existing files in the repo as templates when the user wants to continue an existing benchmark line instead of inventing a new format.

## Run The Scripts

Run the standard trio in one command:

```bash
python3 scripts/run_persona_eval_bundle.py \
  --input /path/to/persona_experiment_input_v11_2026-04-29.json \
  --results-output /path/to/persona_experiment_results_v12_2026-04-30.json \
  --packets-output /path/to/persona_agent_packets_v7_2026-04-30.md \
  --metrics-output /path/to/persona_experiment_metrics_v12_2026-04-30.json \
  --section-label round7 \
  --label v12
```

Rerun a standard persona batch:

```bash
python3 scripts/run_persona_eval.py \
  --input /path/to/persona_experiment_input_v11_2026-04-29.json \
  --results-output /path/to/persona_experiment_results_v12_2026-04-30.json \
  --metrics-output /path/to/persona_experiment_metrics_v12_2026-04-30.json
```

Rerun a hard-mode batch:

```bash
python3 scripts/run_persona_eval.py \
  --input /path/to/persona_experiment_hard_mode_input_v12_2026-04-29.json \
  --results-output /path/to/persona_experiment_hard_mode_results_v13_2026-04-30.json \
  --metrics-output /path/to/persona_experiment_hard_mode_metrics_v13_2026-04-30.json
```

Summarize review feedback:

```bash
python3 scripts/summarize_agent_feedback.py \
  --input /path/to/persona_agent_feedback_v11_2026-04-29.json \
  --output /path/to/persona_agent_metrics_v12_2026-04-30.json
```

Generate markdown review packets:

```bash
python3 scripts/generate_persona_packets.py \
  --input /path/to/persona_experiment_results_v11_2026-04-29.json \
  --output /path/to/persona_agent_packets_v7_2026-04-30.md \
  --section-label round7
```

## Interpretation Rules

- Treat non-zero `returncode` as an execution problem first, not a ranking problem.
- Treat `has_match=false` as a coverage issue, then inspect whether the persona is intentionally strict.
- Read `candidate_count` as a weak signal only. More candidates does not mean better candidates.
- When comparing versions, prefer absolute dates and filenames in the conclusion so the benchmark lineage is clear.
- When score summaries are available, separate top-1 quality from overall average quality.
- Call out benchmark blind spots plainly. Example: if all reviews are "愿意继续聊", say the set may not be discriminative enough.

## Resources

- If the input commands call `local-skills/partner-search/scripts/search_candidates.py`, that is expected. This skill evaluates the search system; it does not replace it.
- When the repo already has prior benchmark artifacts, read only the specific version files you need for the current comparison.
