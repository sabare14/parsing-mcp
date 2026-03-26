# Autonomous Heuristic Optimizer

## Objective

Improve detection accuracy for:

- sheet
- header_row
- data_row

Maximize `overall_score` across the full dataset.

The dataset is small, so changes must generalize across templates instead of exploiting one-off quirks.

You may change aggressively if needed, including:

- weights
- feature contributions
- thresholds
- feature extraction logic
- scoring logic
- ranking logic
- heuristic behavior
- logic addition or logic replacement

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
- score breakdowns for failed cases

Use this to understand why the current logic made the wrong decision.

---

## Primary Rule

Do not make vague global tuning changes unless clearly justified.

Each iteration:

1. pick 1 or 2 failed cases
2. compare the predicted candidate against the correct candidate
3. identify why the wrong candidate won
4. make the smallest strong change likely to flip at least one failed ranking
5. preserve generalization across the rest of the dataset

The goal is not to “smooth” the system.  
The goal is to make the correct candidate beat the wrong candidate on real failures.

---

## Allowed Changes

You may:

- adjust weights
- add or remove feature contributions
- change thresholds
- alter penalties and bonuses
- change how row features are derived
- change how candidate scores are computed
- change how rows are ranked
- change selection logic if current logic is structurally wrong
- add a new general-purpose feature if needed
- replace flawed heuristics with better general heuristics

You are not limited to small tuning edits.  
If current logic is wrong, fix the logic.

---

## Forbidden Changes

Do NOT:

- hardcode file names
- hardcode template-specific values
- add rules tied to one workbook or sheet
- create hacks that solve only one sample
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

### 2. Compare why wrong candidate won
Ask:

- which feature was over-rewarded?
- which penalty was too weak?
- which useful signal was ignored?
- is feature extraction missing an important signal?
- is ranking logic fundamentally wrong for this case?

### 3. Choose the intervention
Prefer this order:

1. fix a clearly wrong contribution
2. add a missing general feature contribution
3. fix a bad threshold
4. change feature extraction
5. change scoring or ranking logic
6. change core heuristic behavior

### 4. Make the change strong enough to matter
Avoid tiny edits that are unlikely to change any ranking.

A change is useful only if it is likely to alter at least one failed decision.

---

## Candidate-Flip Focus

Think like this:

- “Predicted row X beat correct row Y because component A contributed too much.”
- “Correct row Y had useful signal B that is underweighted.”
- “I will reduce A or increase B enough to make Y competitive.”

Do not make edits that sound reasonable but are unlikely to change candidate ordering.

Repeated tiny no-op weight tweaks are bad optimization behavior.

---

## When to Change Core Logic

You are allowed to change core logic when:

- feature weights alone are insufficient
- ranking behavior is structurally biased
- feature computation is missing an important general signal
- candidate selection depends on a flawed assumption
- repeated small adjustments do not move failed cases

Aggressive changes are allowed.  
Overfitted changes are not.

---

## Overfitting Control

Dataset is small, so overfitting risk is high.

Do NOT:

- optimize only the single lowest-scoring case
- rely on exact tokens from one workbook
- create narrow rules that only match one pattern

Prefer:

- structural signals
- row-shape signals
- feature distributions
- generalized token categories like id / name / date / code
- ranking logic that can transfer to unseen templates

Before changing logic, ask:

- would this still make sense on a different workbook with similar structure?
- is this a pattern or just a memorized example?

---

## Iteration Strategy

Each iteration should make 1 or 2 focused changes.

Good iteration behavior:

- target a real failure
- compare predicted vs correct candidate
- make one meaningful fix
- avoid touching many unrelated areas

If previous iterations made no improvement:

- do not repeat the same tiny tweak
- review the last 2-3 failed Pi outputs
- if your planned change is similar to those failed attempts, do not repeat it
- try a different approach
- switch strategy
- consider stronger contribution changes
- consider threshold changes
- consider feature extraction changes
- consider logic changes

If multiple recent attempts fail with similar reasoning:

- do NOT just tweak weights
- identify the shared assumption behind those attempts
- ask: what belief about the data caused these changes?
- ask: is that belief incorrect?
- if a pattern repeatedly fails (for example, penalizing empty rows), test the opposite hypothesis

You are allowed to reverse assumptions, not just adjust parameters.

If the system is stuck, break the tie with a meaningful change.

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

---

## Output

Directly modify `config_auto_finder.py`.

Do not output tool calls.

Return only strict JSON in this format:

{
  "changed": true,
  "summary": "what changed",
  "why": "one line reason"
}

If no useful change is found, return:

{
  "changed": false,
  "summary": "no change made",
  "why": "one line reason"
}

No markdown.  
No extra commentary.

---

## Final Principle

You are not just tuning weights.

You are improving a feature-based ranking system.

Your job is to identify why the wrong candidate wins, then change the logic strongly enough to let the correct candidate win, while keeping the rule general enough to transfer across the dataset.
