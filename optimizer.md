# Autonomous Heuristic Optimizer

## Objective

Improve detection accuracy for:

- sheet
- header_row
- data_row

Maximize `overall_score` across the full dataset (12–15 templates).

Do NOT optimize for a single file. Improvements must generalize.

---

## Input

You will receive `debug.json` each iteration.

It contains:

- overall_score
- delta (previous vs current score)
- failures (top incorrect cases)
- row features (structured signals, not raw text)
- header_candidates and data_candidates
- sheet_features
- current_weights

Use this to understand why the system failed.

---

## Allowed Changes

You may:

- adjust weights in scoring functions
- increase or decrease importance of features
- add new feature contributions (e.g., id_token weight)
- modify thresholds
- improve feature extraction logic (e.g., detect better signals)
- change scoring logic if clearly incorrect

Changes can be aggressive, but must remain **logical and generalizable**.

---

## Forbidden Changes

Do NOT:

- rewrite the entire file
- change file structure significantly
- modify Excel parsing/loading logic
- hardcode dataset-specific values (file names, exact strings)
- introduce hacks specific to one template
- remove core functionality

Avoid breaking the system.

---

## How to Reason

For each failure:

1. Compare predicted vs ground truth:
   - Which row was selected incorrectly?
   - What was the correct row?

2. Compare their features:
   - occupancy (non_empty_count)
   - string_ratio / numeric_ratio
   - short_text_ratio
   - average_text_length
   - token signals (id, name, date, etc.)
   - title-like patterns

3. Analyze candidates:
   - Why did wrong row win?
   - Which component contributed too much?
   - Which important signal was underweighted?

4. Decide what to change:
   - increase useful signals
   - reduce misleading signals
   - fix scoring imbalance

---

## Key Patterns to Learn

Header rows typically:
- have high string_ratio
- have short text labels
- contain identifier-like tokens (id, name, code)
- are followed by tabular rows

Bad header candidates:
- title rows (long text, low column count)
- sparse rows
- instruction-like rows

---

## Avoid Overfitting

Dataset is small (12–15 templates).

Do NOT:
- create rules based on specific words in one file
- rely on exact string matches
- optimize only one failure

Prefer:
- structural patterns
- ratios and distributions
- generalized token categories

---

## Iteration Strategy

- Make 1–2 focused changes per iteration
- Prefer meaningful changes over random tweaks
- If score improves → continue direction
- If no improvement → try different feature emphasis

Track what you change mentally:
- which feature
- which weight
- expected effect

---

## Output Format

You MUST return ONLY tool calls.

Use:

edit_file(path, oldText, newText)

Rules:

- DO NOT output full file
- DO NOT explain
- DO NOT include commentary
- ONLY include necessary edits

Each edit must:
- match exact oldText
- replace with improved newText

---

## Editing Guidelines

Good edits:

- small weight adjustments
- adding a new feature contribution
- fixing incorrect penalty
- improving feature detection

Bad edits:

- rewriting entire scoring function
- large refactors
- unrelated changes

---

## Goal Each Iteration

Given failures:

- make the correct row score higher than incorrect ones
- without breaking correct cases

---

## Success Criteria

- overall_score increases
- fewer failures
- better separation between correct vs incorrect candidates

---

## Summary

You are optimizing a **feature-based scoring system**.

Focus on:
- feature importance
- scoring balance
- generalizable patterns

Avoid:
- hacks
- overfitting
- unnecessary complexity