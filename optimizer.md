# optimizer

This is an autonomous optimization loop for improving a rule-based Excel template parser.

You modify `config_auto_finder.py` to improve evaluation score.

---

## Objective

The system predicts:

- `sheet_name`
- `header_row`
- `data_row`

Evaluation is hierarchical:

- If `sheet_name` is wrong → score = 0
- If correct sheet:
  - `header_row` is scored by distance
  - `data_row` is scored asymmetrically:
    - predicting ABOVE GT is heavily penalized
    - predicting BELOW GT is mildly penalized

**Goal: maximize overall_score by improving candidate ranking.**

---

## Core Principle

You are not tuning parameters.

You are fixing a decision system.

Do not assume current logic is correct.

---

## What you CAN do

You may modify anything inside `config_auto_finder.py`:

- change logic
- tune weights
- add/remove heuristics
- rewrite ranking
- replace assumptions
- simplify logic
- introduce new signals

All changes must improve ranking behavior.

---

## What you MUST NOT do

- do not modify other files
- do not add irrelevant code
- do not make cosmetic changes
- do not add complexity without benefit
- do not hardcode for specific examples

---

## Hypothesis-driven optimization

Each iteration MUST follow this structure:

### 1. Choose ONE hypothesis

A hypothesis is a short explanation of failure.

Examples:
- `early_row_bias`
- `dense_row_overweight`
- `blank_row_misclassification`
- `weak_table_boundary`
- `header_numeric_bias`
- `fixed_offset_bias`

Rules:
- Use 1–3 words
- Only ONE hypothesis per iteration
- All changes must directly test this hypothesis

---

### 2. Analyze failures

You will be given failed examples.

For each:

- identify which candidate won
- identify which should have won
- identify WHY the wrong candidate outranked the correct one

Focus on ranking mechanism, not surface traits.

---

### 3. Identify mechanism

Classify the issue:

- wrong sheet selection
- wrong header ranking
- wrong data-row ranking
- bias toward early rows
- bias toward filled rows
- bias toward sparse rows
- bias toward long-text/title rows
- weak boundary detection
- weak block-start detection

Do NOT assume all failures share the same cause.

---

### 4. Decide change type

Choose ONE:

- weight/threshold tuning (only if clearly sufficient)
- logic correction (bias fix, rule removal)
- structural improvement (new signal, new ranking logic)

If recent attempts failed with similar tuning → DO NOT repeat → choose structural change.

---

### 5. Make 1–2 focused changes

Good changes:

- flip a wrong bias
- remove misleading signal
- introduce missing structural cue
- improve relative ranking
- simplify conflicting logic

Bad changes:

- random tweaks
- many simultaneous edits
- weak changes unlikely to affect ranking
- patching symptoms without fixing cause

---

## Learning from past failures

You will be given recent failed attempts.

You MUST:

- extract their hypotheses
- detect repetition
- avoid repeating the same idea

Important rules:

- changing a threshold is NOT a new idea
- making a penalty stronger is NOT a new idea
- rephrasing logic is NOT a new idea

If a direction failed, abandon it.

---

## Anti-repetition rules

Do NOT repeat:

- long-text penalty tuning
- blank-row suppression tweaks
- early-row bias nudging
- small weight adjustments

If these appeared in recent failures, choose a DIFFERENT hypothesis.

---

## Ranking-first mindset

Always think in pairwise comparisons:

- why did wrong candidate beat correct one?
- which signals caused that?
- what change would flip that ordering?

Your job is to flip incorrect rankings.

---

## Plateau handling

If improvements stall:

- stop tuning weights
- stop refining failed ideas
- question assumptions
- introduce new signals or logic

Plateau means current abstraction is limiting performance.

Change the abstraction.

---

## Sheet/header/data dependency

Respect structure:

- wrong sheet → everything fails
- row logic only matters within correct sheet
- do not treat row indices globally
- do not optimize row logic ignoring sheet selection

---

## Simplicity rule

Prefer:

- fewer heuristics
- cleaner logic
- interpretable ranking
- fewer special cases

Reject:

- complex hacks for tiny gains

---

## Decision rule

Keep a change only if:

- it improves score
- or simplifies logic without hurting score

Reject if:

- no meaningful ranking change
- overfits to few examples
- increases complexity without benefit

---

## Output requirements

Return:

```json
{
  "changed": true|false,
  "hypothesis": "short_name",
  "change_type": "tuning|logic|structural",
  "summary": "what changed",
  "why": "why this fixes ranking"
}