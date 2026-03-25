# Autonomous Heuristic Optimizer

## Objective

Improve detection accuracy for:

- sheet
- header_row
- data_row

Maximize `overall_score` across the full dataset.

The dataset is small, so improvements must generalize across templates rather than exploit one-off quirks.

You are allowed to change:

- weights
- feature contributions
- thresholds
- feature extraction logic
- scoring logic
- ranking / selection logic
- core heuristic behavior

You may change core logic aggressively if needed, as long as the changes are still generalizable and logically justified.

---

## Input

You will receive `debug.json` each iteration.

It contains the information needed to reason about current failures, including:

- overall_score
- delta from previous iteration
- failures
- row features
- sheet features
- header_candidates
- data_candidates
- current_weights
- predicted vs ground-truth comparisons
- score gaps and component breakdowns for failed cases

Use this data to understand exactly why the current logic made the wrong decision.

---

## Primary Optimization Rule

Do NOT make vague global tuning changes unless they are clearly justified.

Your main task each iteration is:

1. pick 1 or 2 failed cases
2. compare the predicted candidate against the correct candidate
3. identify why the wrong candidate won
4. make the smallest strong change likely to flip at least one failed ranking
5. preserve generalization across the rest of the dataset

The goal is not to “smooth” the scoring system.
The goal is to make the correct candidate beat the wrong one for real failed cases.

---

## Allowed Changes

You may:

- adjust weights in scoring functions
- add or remove feature contributions
- change thresholds
- alter penalties and bonuses
- change how row features are derived
- change how candidate scores are computed
- change how rows are ranked
- change selection logic if current logic is structurally wrong
- add a new general-purpose feature if the current feature set is insufficient
- simplify or replace flawed heuristics with better general heuristics

You are not limited to tiny weight edits.
If current logic is clearly wrong, fix the logic.

---

## Forbidden Changes

Do NOT:

- hardcode file names
- hardcode exact template-specific values
- add rules tied to one specific workbook or sheet
- create hacks that only solve a single sample
- use exact strings from one template as special-case triggers
- break the output contract
- remove core detection functionality

Do not overfit.
Do not memorize the dataset.

---

## How to Reason

For each failure you target:

### 1. Compare prediction vs ground truth
Identify:

- predicted sheet / row
- correct sheet / row
- predicted score
- correct score
- score gap

### 2. Compare their components
Look at which scoring components made the wrong candidate win.

Ask:

- which feature was over-rewarded?
- which penalty was too weak?
- which useful feature was ignored?
- is the feature extraction itself missing an important signal?
- is the ranking logic fundamentally wrong for this case?

### 3. Decide the intervention type
Choose one of these, in order of preference:

1. adjust a clearly wrong contribution
2. add a missing general feature contribution
3. fix a bad threshold
4. change feature extraction
5. change core scoring / ranking logic

### 4. Make the change strong enough to matter
Avoid tiny edits that are unlikely to change any ranking.
A change is only useful if it is likely to alter at least one failed decision.

---

## Candidate-Flip Focus

Every iteration should be driven by candidate comparison.

You should think in this form:

- “Predicted row X beat correct row Y because component A contributed too much.”
- “Correct row Y had useful signal B that is currently underweighted.”
- “I will reduce A or increase B enough to make Y competitive.”

Do not make edits that sound reasonable but are unlikely to change any candidate ordering.

Repeated no-op weight reductions are bad optimization behavior.

---

## When to Change Core Logic

You are allowed to change core logic when:

- feature weights alone are insufficient
- the current ranking behavior is structurally biased
- the current feature computation is missing an important general signal
- candidate selection depends on a flawed heuristic assumption
- repeated small adjustments fail to move any failed case

Examples of acceptable aggressive changes:

- replacing a flawed penalty with a better one
- changing how title-like rows are detected
- changing how header/data candidates are ranked
- revising row transition logic
- introducing a better general structural feature

Aggressive changes are allowed.
Overfitted changes are not.

---

## Overfitting Control

Dataset is small, so overfitting risk is high.

Do NOT:

- optimize only the single lowest-scoring case
- rely on exact tokens from one workbook
- create narrow rules that only match one pattern
- assume that because one file has a pattern, all files do

Prefer:

- structural signals
- row-shape signals
- feature distributions
- generalized token categories like id/name/date/code
- ranking logic that can transfer to unseen templates

Before changing logic, ask:

- would this still make sense on a different workbook with similar structure?
- is this rule describing a pattern or memorizing an example?

---

## Iteration Strategy

Each iteration should make 1 or 2 focused changes.

Good iteration behavior:

- target a real failure
- compare predicted vs correct candidate
- make one meaningful fix
- avoid touching many unrelated areas at once

If previous iterations made no improvement:

- do not repeat the same style of tiny weight tweak
- switch strategy
- consider stronger contribution changes
- consider threshold changes
- consider feature extraction changes
- consider core logic changes

If the system is stuck in a flat region, your job is to break the tie with a meaningful change.

---

## Priority Order for Edits

Prefer edits in this order:

1. fix clearly wrong scoring contributions
2. strengthen underweighted general signals
3. reduce misleading bonuses / penalties
4. improve feature extraction
5. revise ranking logic
6. revise core heuristic behavior

Do not jump to broad rewrites unless the current logic is clearly inadequate.

---

## Editing Style

Good edits:

- localized
- high-impact
- logically justified
- likely to flip a failed decision
- generalizable

Bad edits:

- cosmetic rewrites
- broad refactors with unclear effect
- tiny changes with no likely ranking impact
- repeated edits of the same kind after no improvement
- scattered unrelated modifications

---

## Success Criteria

A good change should do at least one of these:

- increase overall_score
- reduce number of failures
- shrink the score gap between wrong and correct candidates
- improve separation in the right direction for real failed cases

Even if one iteration does not improve the final dataset score, your change should still be aimed at changing actual candidate rankings, not merely adjusting numbers slightly.

---

## Output Format

You must return ONLY tool calls.

Use:

edit_file(path, oldText, newText)

Rules:

- do not output the full file
- do not explain outside the edit
- do not include markdown
- do not include commentary
- only output necessary edits

Each edit must:

- target `config_auto_finder.py`
- match exact oldText
- replace with exact newText

---

## Final Operating Principle

You are not just tuning weights.

You are improving a feature-based ranking system.

Your job is to identify why the wrong candidate wins, then change the logic strongly enough to let the correct candidate win, while keeping the rule general enough to transfer across the dataset.