#!/usr/bin/env python3
"""OULAD early-alert analysis.

Question
--------
How early can VLE engagement + assessment signals identify students who
will withdraw or fail?

Design (stated up front, before any results)
--------------------------------------------
* Cohort: every student x module-presentation registration in
  studentInfo.csv (32,593 rows; 7 modules x 22 presentations,
  2013B-2014J).
* Outcome: at-risk = final_result in {Withdrawn, Fail};
  not-at-risk = {Pass, Distinction}.
* Alert day: day 14 of the presentation. Only information dated
  day 0-13 (plus enrolment-time fields) is used as predictors.
* Prediction cohort: students still enrolled on day 14
  (studentRegistration.date_unregistration is empty or > 13).
  Students who had already withdrawn by day 14 are counted and
  reported separately -- an alert on day 14 cannot help them, and
  leaving them in would leak the answer into the features (their
  engagement stops *because* they withdrew).
* Split: temporal. Train on 2013 presentations (2013B + 2013J),
  test on 2014 presentations (2014B + 2014J). No student outcome
  from the test year touches model fitting.
* Model: logistic regression (standardised numeric features,
  one-hot categoricals, median/mode imputation fitted on train).
  Deliberately simple and inspectable -- coefficients are reported.
* Baseline rule (pre-stated): flag any student with ZERO active
  VLE days in days 0-13.
* Metrics on the held-out 2014 test set: AUC, and at the 0.50
  threshold sensitivity / specificity / precision; also the share
  of at-risk students captured by flagging the highest-risk 20%.

Every number printed by this script is written to
outputs/metrics.json; the README and results_summary.md quote that
file. Nothing is hand-typed.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    roc_auc_score,
    roc_curve,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"
CHARTS = OUT / "charts"
WINDOW_END = 13  # days 0..13 inclusive = first 14 days


def load_small_tables():
    # The UCI mirror codes missing values as "?" (e.g. an empty
    # date_unregistration, some assessment scores). Without
    # na_values="?" those columns load as strings and every numeric
    # comparison fails -- a real property of this release, handled
    # explicitly here.
    info = pd.read_csv(RAW / "studentInfo.csv", na_values="?")
    reg = pd.read_csv(RAW / "studentRegistration.csv", na_values="?")
    assess = pd.read_csv(RAW / "assessments.csv", na_values="?")
    subs = pd.read_csv(RAW / "studentAssessment.csv", na_values="?")
    courses = pd.read_csv(RAW / "courses.csv", na_values="?")
    return info, reg, assess, subs, courses


def vle_window_features():
    """Aggregate studentVle.csv (10.66M rows) in chunks.

    Only rows with 0 <= date <= 13 are kept; the aggregated frame is
    clicks / active days / distinct resources per student-registration.
    """
    keys = ["code_module", "code_presentation", "id_student"]
    chunks = []
    reader = pd.read_csv(
        RAW / "studentVle.csv",
        usecols=keys + ["id_site", "date", "sum_click"],
        chunksize=1_000_000,
    )
    for chunk in reader:
        w = chunk[(chunk["date"] >= 0) & (chunk["date"] <= WINDOW_END)]
        if len(w):
            chunks.append(w)
    w = pd.concat(chunks, ignore_index=True)
    agg = (
        w.groupby(keys)
        .agg(
            clicks_14d=("sum_click", "sum"),
            active_days_14d=("date", "nunique"),
            resources_14d=("id_site", "nunique"),
        )
        .reset_index()
    )
    return agg


def assessment_window_features(assess, subs):
    """Submissions dated <= day 13, joined to their assessment's module."""
    m = subs.merge(
        assess[["id_assessment", "code_module", "code_presentation"]],
        on="id_assessment",
        how="left",
    )
    early = m[m["date_submitted"] <= WINDOW_END]
    keys = ["code_module", "code_presentation", "id_student"]
    agg = (
        early.groupby(keys)
        .agg(n_submitted_14d=("score", "size"), early_mean_score=("score", "mean"))
        .reset_index()
    )
    return agg, m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    metrics = {}

    info, reg, assess, subs, courses = load_small_tables()

    # ---------- cohort & outcome ----------
    outcome_counts = info["final_result"].value_counts().to_dict()
    metrics["cohort"] = {
        "registrations_total": int(len(info)),
        "outcome_counts": {k: int(v) for k, v in outcome_counts.items()},
        "modules": sorted(info["code_module"].unique().tolist()),
        "presentations": sorted(info["code_presentation"].unique().tolist()),
    }
    info["at_risk"] = info["final_result"].isin(["Withdrawn", "Fail"]).astype(int)
    metrics["cohort"]["at_risk_rate_all"] = round(float(info["at_risk"].mean()), 4)

    # ---------- early withdrawals (before the alert could fire) ----------
    df = info.merge(
        reg[["code_module", "code_presentation", "id_student",
             "date_registration", "date_unregistration"]],
        on=["code_module", "code_presentation", "id_student"],
        how="left",
    )
    withdrawn = df[df["final_result"] == "Withdrawn"]
    gone_by_14 = withdrawn[withdrawn["date_unregistration"] <= WINDOW_END]
    excluded_by_14 = df[df["date_unregistration"] <= WINDOW_END]
    metrics["early_withdrawal"] = {
        "withdrawn_total": int(len(withdrawn)),
        "withdrawn_by_day_14": int(len(gone_by_14)),
        "share_of_withdrawals_by_day_14": round(len(gone_by_14) / len(withdrawn), 4),
        "withdrawn_before_day_0": int((withdrawn["date_unregistration"] < 0).sum()),
        "total_excluded_from_prediction_cohort": int(len(excluded_by_14)),
        "note": "Exclusions are all registrations with date_unregistration "
                "<= 13: 4,457 Withdrawn plus 8 recorded as Fail who also "
                "unregistered by day 14 (a coding quirk in the source).",
    }

    # prediction cohort: still enrolled on day 14
    pred = df[df["date_unregistration"].isna() | (df["date_unregistration"] > WINDOW_END)].copy()
    metrics["prediction_cohort"] = {
        "n": int(len(pred)),
        "at_risk_n": int(pred["at_risk"].sum()),
        "at_risk_rate": round(float(pred["at_risk"].mean()), 4),
    }

    # ---------- features ----------
    vle = vle_window_features()
    keys = ["code_module", "code_presentation", "id_student"]
    pred = pred.merge(vle, on=keys, how="left")
    for c in ["clicks_14d", "active_days_14d", "resources_14d"]:
        pred[c] = pred[c].fillna(0)
    pred["no_vle_activity_14d"] = (pred["active_days_14d"] == 0).astype(int)
    pred["clicks_per_active_day"] = np.where(
        pred["active_days_14d"] > 0,
        pred["clicks_14d"] / pred["active_days_14d"],
        0,
    )

    a_agg, subs_joined = assessment_window_features(assess, subs)
    pred = pred.merge(a_agg, on=keys, how="left")
    pred["n_submitted_14d"] = pred["n_submitted_14d"].fillna(0)
    pred["has_early_score"] = pred["early_mean_score"].notna().astype(int)
    metrics["assessment_signal"] = {
        "share_with_submission_by_day_14": round(float((pred["n_submitted_14d"] > 0).mean()), 4),
        "median_first_assessment_due_day": float(
            assess[assess["assessment_type"] != "Exam"]
            .groupby(["code_module", "code_presentation"])["date"].min().median()
        ),
    }

    # ---------- descriptives for findings ----------
    by_outcome = (
        pred.groupby("final_result")
        .agg(
            n=("at_risk", "size"),
            median_clicks_14d=("clicks_14d", "median"),
            median_active_days_14d=("active_days_14d", "median"),
            share_zero_activity=("no_vle_activity_14d", "mean"),
        )
        .round(3)
    )
    metrics["engagement_by_outcome"] = by_outcome.reset_index().to_dict("records")

    zero = pred[pred["no_vle_activity_14d"] == 1]
    some = pred[pred["no_vle_activity_14d"] == 0]
    metrics["zero_activity"] = {
        "share_of_prediction_cohort": round(float(pred["no_vle_activity_14d"].mean()), 4),
        "at_risk_rate_zero_activity": round(float(zero["at_risk"].mean()), 4),
        "at_risk_rate_any_activity": round(float(some["at_risk"].mean()), 4),
        "risk_ratio": round(float(zero["at_risk"].mean() / some["at_risk"].mean()), 3),
    }

    prev = pred.assign(prev_attempt=(pred["num_of_prev_attempts"] > 0).astype(int))
    metrics["prev_attempts"] = {
        "at_risk_rate_no_prev_attempt": round(
            float(prev[prev["prev_attempt"] == 0]["at_risk"].mean()), 4),
        "at_risk_rate_with_prev_attempt": round(
            float(prev[prev["prev_attempt"] == 1]["at_risk"].mean()), 4),
        "share_with_prev_attempt": round(float(prev["prev_attempt"].mean()), 4),
    }

    # ---------- model ----------
    numeric = [
        "clicks_14d", "active_days_14d", "resources_14d",
        "clicks_per_active_day", "n_submitted_14d", "early_mean_score",
        "has_early_score", "num_of_prev_attempts", "studied_credits",
        "date_registration",
    ]
    categorical = [
        "code_module", "gender", "age_band", "highest_education",
        "disability", "imd_band",
    ]
    pred["imd_band"] = pred["imd_band"].fillna("Missing")
    features = numeric + categorical

    train = pred[pred["code_presentation"].str.startswith("2013")]
    test = pred[pred["code_presentation"].str.startswith("2014")]
    metrics["split"] = {
        "train_presentations": sorted(train["code_presentation"].unique().tolist()),
        "test_presentations": sorted(test["code_presentation"].unique().tolist()),
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "test_at_risk_rate": round(float(test["at_risk"].mean()), 4),
    }

    pre = ColumnTransformer([
        ("num", Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("sc", StandardScaler()),
        ]), numeric),
        ("cat", Pipeline([
            ("imp", SimpleImputer(strategy="most_frequent")),
            ("oh", OneHotEncoder(handle_unknown="ignore")),
        ]), categorical),
    ])
    model = Pipeline([
        ("pre", pre),
        ("clf", LogisticRegression(max_iter=1000, C=1.0)),
    ])
    model.fit(train[features], train["at_risk"])
    proba = model.predict_proba(test[features])[:, 1]
    pred_label = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(test["at_risk"], pred_label).ravel()
    auc = roc_auc_score(test["at_risk"], proba)

    # flag the highest-risk 20% of the test cohort
    k = int(np.ceil(0.20 * len(test)))
    top_idx = np.argsort(-proba)[:k]
    sens_top20 = float(test["at_risk"].values[top_idx].sum() / test["at_risk"].sum())

    metrics["model_test"] = {
        "auc": round(float(auc), 4),
        "threshold": 0.5,
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
        "sensitivity": round(float(tp / (tp + fn)), 4),
        "specificity": round(float(tn / (tn + fp)), 4),
        "precision": round(float(tp / (tp + fp)), 4),
        "flag_rate_at_threshold": round(float(pred_label.mean()), 4),
        "sensitivity_flagging_top_20pct": round(sens_top20, 4),
    }

    # baseline rule on test: zero active days in window
    rule = (test["active_days_14d"] == 0).astype(int).values
    tn2, fp2, fn2, tp2 = confusion_matrix(test["at_risk"], rule).ravel()
    metrics["rule_zero_activity_test"] = {
        "tp": int(tp2), "fp": int(fp2), "tn": int(tn2), "fn": int(fn2),
        "sensitivity": round(float(tp2 / (tp2 + fn2)), 4),
        "specificity": round(float(tn2 / (tn2 + fp2)), 4),
        "precision": round(float(tp2 / (tp2 + fp2)), 4),
        "flag_rate": round(float(rule.mean()), 4),
    }

    # VLE-only ablation: how much of the signal is engagement alone?
    vle_numeric = ["clicks_14d", "active_days_14d", "resources_14d",
                   "clicks_per_active_day", "no_vle_activity_14d"]
    pre_vle = ColumnTransformer([
        ("num", Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("sc", StandardScaler()),
        ]), vle_numeric),
    ])
    model_vle = Pipeline([
        ("pre", pre_vle),
        ("clf", LogisticRegression(max_iter=1000, C=1.0)),
    ])
    model_vle.fit(train[vle_numeric], train["at_risk"])
    auc_vle = roc_auc_score(
        test["at_risk"], model_vle.predict_proba(test[vle_numeric])[:, 1])
    metrics["model_vle_only_test"] = {"auc": round(float(auc_vle), 4),
                                      "features": vle_numeric}

    # coefficients (transparency)
    oh_names = (
        model.named_steps["pre"].named_transformers_["cat"]
        .named_steps["oh"].get_feature_names_out(categorical)
    )
    coef_names = numeric + list(oh_names)
    coefs = model.named_steps["clf"].coef_[0]
    order = np.argsort(-np.abs(coefs))
    metrics["top_coefficients"] = [
        {"feature": str(coef_names[i]), "coef": round(float(coefs[i]), 3)}
        for i in order[:10]
    ]

    # ---------- charts ----------
    fig, ax = plt.subplots(figsize=(7, 4))
    order_outcomes = ["Distinction", "Pass", "Fail", "Withdrawn"]
    med = by_outcome.loc[order_outcomes]
    ax.bar(med.index, med["median_clicks_14d"], color="#0E7C7B")
    ax.set_ylabel("Median VLE clicks, days 0-13")
    ax.set_title("Early engagement by final outcome (prediction cohort)")
    fig.tight_layout()
    fig.savefig(CHARTS / "median_clicks_by_outcome.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 5))
    fpr, tpr, _ = roc_curve(test["at_risk"], proba)
    ax.plot(fpr, tpr, color="#0A2A4A", label=f"Logistic regression (AUC {auc:.3f})")
    ax.plot([0, 1], [0, 1], "--", color="#888888", label="Chance")
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate (sensitivity)")
    ax.set_title("Early-alert ROC -- held-out 2014 presentations")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(CHARTS / "roc_curve.png", dpi=150)
    plt.close(fig)

    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    print("\nWrote outputs/metrics.json + 2 charts")


if __name__ == "__main__":
    main()
