# OULAD Early Alert — results summary

All numbers below are copied from `outputs/metrics.json`, written by
`src/02_early_alert.py` on its run of 2026-10-27 (exit 0; a second run
reproduced every metric exactly). Data verification is in
`outputs/data_verification.json`, written by `src/00_verify_data.py`.

## Cohort

- Registrations analysed: **32,593** (7 modules, presentations 2013B–2014J)
- Final results: Pass 12,361 · Withdrawn 10,156 · Fail 7,052 · Distinction 3,024
  — identical to the class distribution printed in the dataset's own
  documentation (OULAD.names §9).
- At-risk (Withdrawn + Fail) share of all registrations: **52.8%**

## The timing problem

- Withdrawals by day 14: **4,457 of 10,156 (43.9%)** — including
  **2,676 before day 0** (registered, then withdrew before the module
  even started).
- Prediction cohort (still enrolled on day 14): **28,128** students,
  of whom 12,743 (45.3%) eventually withdrew or failed.
  (Excluded: the 4,457 above plus 8 students recorded as Fail who also
  unregistered by day 14.)

## Engagement in days 0–13, by final outcome (prediction cohort)

| Outcome | n | Median clicks | Median active days | Zero-activity share |
|---|---|---|---|---|
| Distinction | 3,024 | 144 | 7 | 3.4% |
| Pass | 12,361 | 97 | 5 | 5.4% |
| Withdrawn | 5,699 | 51 | 4 | 13.6% |
| Fail | 7,044 | 37 | 3 | 17.3% |

## Zero-activity signal

- Zero active VLE days in the first 14: **9.8%** of the prediction cohort
- Their eventual at-risk rate: **72.3%**, vs **42.4%** for students with
  any activity — risk ratio **1.71**

## Assessment signal barely exists yet

- Students with any submission by day 14: **12.4%**
- Median first (non-exam) assessment due day: **21.5**
- Prior attempts: students repeating a module ended at-risk **61.2%**
  of the time vs **43.0%** for first attempts

## Model — logistic regression, trained 2013, tested 2014 (n = 16,032)

| | Value |
|---|---|
| AUC (full model) | **0.704** |
| AUC (VLE-engagement features only) | **0.659** |
| Sensitivity @ threshold 0.50 | **52.4%** |
| Specificity @ 0.50 | **76.5%** |
| Precision @ 0.50 | **64.6%** |
| Share flagged @ 0.50 | 36.5% |
| At-risk students captured by flagging the top-risk 20% | **31.3%** |

Confusion matrix @ 0.50 (test): TP 3,782 · FP 2,074 · TN 6,741 · FN 3,435

## Baseline rule — flag zero active VLE days (test set)

Sensitivity **14.4%** · Specificity **95.4%** · Precision **71.7%** ·
flags 9.0% of students. Precise, but it misses most at-risk students:
silence is a strong signal, not a sufficient one.

## Strongest model coefficients (standardised)

active_days_14d −0.74 (protective) · module GGG −0.83 · module DDD +0.68 ·
No Formal quals +0.61 · IMD 0–10% +0.58 · module FFF +0.57 ·
HE Qualification −0.43 — i.e. the model partly learns *which module*
a student is in, not only how the student behaves. See README limitations.
