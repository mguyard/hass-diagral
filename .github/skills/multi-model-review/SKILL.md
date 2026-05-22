---
name: multi-model-review
description: "Multi-Model Code Review: consensus-based analysis patterns, consolidation methodology, conflict resolution, and false positive triage."
license: "See repository LICENSE"
user-invocable: false
---

# Multi-Model Code Review

## Overview

This skill provides guidance for running code reviews across multiple LLMs in parallel and consolidating findings into a unified, high-confidence report. The core principle is **consensus-based triage** — issues flagged by multiple independent models carry more weight than those flagged by only one.

## When to Use This Skill

- MultiReviewer is performing consensus consolidation
- Evaluating conflicting findings from different models
- Triaging false positives vs. real issues
- Deciding review depth (single-model vs. multi-model)

## When NOT to Use This Skill

- Standard single-model review is sufficient
- Simple or low-risk code changes
- Quick fixes or configuration updates

---

## 1. Consensus Scoring Model

### Confidence Levels

| Score | Models Agreeing | Confidence | Action                                                                            |
| ----- | --------------- | ---------- | --------------------------------------------------------------------------------- |
| 3/3   | All models      | **High**   | Must fix — independent convergence confirms the issue                             |
| 2/3   | Majority        | **Medium** | Should fix — likely real, review the dissenting model's reasoning                 |
| 1/3   | Single model    | **Low**    | Evaluate — may be false positive, model-specific pattern, or legitimate edge case |

### Interpreting 1/3 Findings

Not all 1/3 findings are false positives. Some deserve attention:

**Likely false positive:**

- Style preference rather than correctness issue
- Model misunderstands framework conventions
- Suggestion contradicts established codebase patterns

**Likely real despite single model:**

- Security vulnerability with clear exploit path
- Data loss scenario with concrete reproduction
- Race condition with timing-dependent behavior
- Edge case that requires domain-specific knowledge one model happens to have

**Rule of thumb:** If a 1/3 finding has a concrete, verifiable failure scenario, treat it as medium confidence regardless of consensus.

---

## 2. Consolidation Methodology

### Step 1: Normalize Findings

Map each model's findings to the standard severity format:

```
🔴 BLOCKER  → Must fix before shipping
🟡 WARNING  → Should fix to avoid future problems
🔵 SUGGESTION → Consider for improvement
✅ POSITIVE  → Good patterns to preserve
```

### Step 2: Match & De-duplicate

Compare findings across all models:

**Exact match:** Same file, same line, same issue → merge with full consensus score.

**Semantic match:** Different wording, same underlying issue → merge, note the different perspectives.

**Partial overlap:** Related but distinct observations → keep separate, note the relationship.

**Unique finding:** Only one model flags it → keep with 1/3 score, evaluate independently.

### Step 3: Resolve Severity Conflicts

When models assign different severities to the same issue:

```
Model A: 🔴 BLOCKER — SQL injection in user input
Model B: 🟡 WARNING — Unsanitized input in query
Model C: (not flagged)
```

**Resolution rules:**

1. Highest severity wins for security issues
2. Majority severity wins for non-security issues
3. If split 1/1/1, consolidator makes the judgment call with reasoning

### Step 4: Assess Disagreements

When models explicitly disagree:

```
Model A: 🟡 WARNING — useEffect missing dependency
Model B: ✅ POSITIVE — correctly excluded dependency (intentional)
```

**Resolution:** The consolidator must investigate by reading the code and determining which model is correct. Document the reasoning.

---

## 3. Multi-Model Review Patterns

### Pattern A: Breadth-Optimized Review

Different review models often surface different classes of issues. Treat this as a source of broader coverage, not as a fixed stereotype or a guarantee about any specific model family.

### Pattern B: Adversarial Validation

Use one model's findings to challenge another:

- If Model A flags a potential race condition, check if Model B's review considered the same code path
- If no other model noticed it, investigate whether the issue is real or a misinterpretation

### Pattern C: Confidence Calibration

Over time, track which models produce more false positives in specific domains:

- Adjust weighting if one model consistently over-reports in a category
- Note patterns in model disagreements for future reference

---

## 4. When to Escalate to Multi-Model

### Use Multi-Model When:

- Changes touch authentication, authorization, or payment logic
- Refactoring core architecture or shared utilities
- Introducing new external dependencies or APIs
- Changes affect data persistence or migration
- Code handles sensitive user data (PII, credentials)
- Large-scale changes (>5 files, >200 lines)

### Use Single-Model When:

- Minor bug fixes with clear scope
- Configuration or environment changes
- Documentation-only updates
- Style/formatting changes
- Adding simple tests

---

## 5. Output Quality Checklist

Before delivering the consolidated report, verify:

- [ ] All findings have consensus scores assigned
- [ ] Duplicate findings are merged (not listed separately per model)
- [ ] Severity conflicts are resolved with reasoning
- [ ] Model disagreements are explicitly documented
- [ ] 1/3 findings are evaluated for false positive likelihood
- [ ] Positive findings are included (not just problems)
- [ ] Consensus summary table is populated
- [ ] Overall assessment reflects the aggregated picture
