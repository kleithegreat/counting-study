"""Score the study, work out bonuses, draw the lottery winner, and run the stats.

Usage:
    python analyze.py DATA_DIR [--prolific-export submissions.csv] [--seed 20261215] [--out results]

DATA_DIR is the folder of .json files DataPipe saved (one per participant).
Files starting with TEST_ are ignored.

Writes to --out (default: results/):
    participants.csv     one row per participant, with exclusion + bonus columns
    trials.csv           one row per grid answered
    bonuses_prolific.txt paste into Prolific "Bulk bonus payment" (<submission ID>,<amount> per line)
    bonuses_review.csv   who gets what, with Prolific IDs, to check before paying
    lottery_draw.txt     how the lottery winner was drawn (reproducible from the seed)
    report.md            descriptive stats + tests, ready to paste into the report
    fig_correct.png, fig_time.png
"""
import argparse
import json
import warnings
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

warnings.filterwarnings("ignore")  # statsmodels convergence chatter on small samples

FIXED_AMOUNT = 0.25
LOTTERY_AMOUNT = 4.00
COND_ORDER = ["fixed", "lottery"]
COLORS = {"fixed": "#2a6fdb", "lottery": "#e8a400"}


def load(data_dir: Path):
    rows, trials, skipped = [], [], []
    for f in sorted(data_dir.glob("*.json")):
        if f.name.startswith("TEST_"):
            skipped.append((f.name, "test run"))
            continue
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            skipped.append((f.name, "unreadable JSON"))
            continue
        m = d["meta"]
        if m.get("test_run"):
            skipped.append((f.name, "test run"))
            continue
        pid = m.get("prolific_pid") or m["participant_id"]
        rows.append({**{k: v for k, v in m.items() if k != "grid_order"}, "pid": pid, "file": f.name})
        for t in d["trials"]:
            trials.append({"pid": pid, "condition": m["condition"], "file": f.name, **t})
    return pd.DataFrame(rows), pd.DataFrame(trials), skipped


def score(people: pd.DataFrame, trials: pd.DataFrame) -> pd.DataFrame:
    sc = trials[trials.kind == "scored"]
    per = sc.groupby("file").agg(
        n_correct=("correct", "sum"),
        n_grids=("correct", "size"),
        mean_abs_error=("abs_error", "mean"),
        n_timeouts=("timed_out", "sum"),
        n_blank=("answer", lambda s: s.isna().sum()),
        mean_rt_s=("rt_ms", lambda s: s.mean() / 1000),
        tab_hidden=("tab_hidden_count", "sum"),
    )
    att = trials[trials.kind == "attention"].set_index("file")["correct"].rename("attention_pass")
    out = people.merge(per, left_on="file", right_index=True, how="left").merge(
        att, left_on="file", right_index=True, how="left")
    out["n_correct"] = out["n_correct"].fillna(0).astype(int)
    return out


def apply_exclusions(p: pd.DataFrame) -> pd.DataFrame:
    p = p.sort_values("started_at").copy()
    p["exclusion"] = ""
    dup = p.duplicated("pid", keep="first")
    p.loc[dup, "exclusion"] = "duplicate (kept first attempt)"
    p.loc[(p.exclusion == "") & (p.n_grids < p.n_scored), "exclusion"] = "incomplete"
    p.loc[(p.exclusion == "") & (p.attention_pass != True), "exclusion"] = "failed attention check"  # noqa: E712
    p.loc[(p.exclusion == "") & (p.n_blank >= 5), "exclusion"] = "5+ blank answers"
    p["included"] = p.exclusion == ""
    return p


def bonuses(p: pd.DataFrame, seed: int, out: Path, submission_ids: dict | None) -> pd.DataFrame:
    """Bonus rule is the one shown to participants: >= threshold correct of the scored grids.
    It applies to everyone who completed the task, including people excluded from analysis."""
    p = p.copy()
    first = ~p.duplicated("pid", keep="first")
    p["bonus_eligible"] = first & (p.n_correct >= p.bonus_threshold)
    p["bonus_usd"] = 0.0
    p.loc[p.bonus_eligible & (p.condition == "fixed"), "bonus_usd"] = FIXED_AMOUNT

    eligible = sorted(p.loc[p.bonus_eligible & (p.condition == "lottery"), "pid"])
    lines = [
        f"Lottery draw for one ${LOTTERY_AMOUNT:.2f} prize",
        f"Seed: {seed}  (fixed in advance; re-run with the same seed to verify)",
        f"Eligible lottery participants ({len(eligible)}), sorted by Prolific ID:",
        *[f"  {e}" for e in eligible],
    ]
    if eligible:
        winner = random.Random(seed).choice(eligible)
        p.loc[(p.pid == winner) & (p.condition == "lottery") & first, "bonus_usd"] = LOTTERY_AMOUNT
        lines.append(f"Winner: {winner}")
    else:
        lines.append("No eligible participants: no prize to pay.")
    (out / "lottery_draw.txt").write_text("\n".join(lines) + "\n")

    # Prolific's bulk bonus form needs SUBMISSION IDs (not participant IDs). Take them from the
    # Prolific export when given; otherwise fall back to SESSION_ID, which the page recorded from the URL.
    pay = p[(p.bonus_usd > 0) & p.prolific_pid.notna()].copy()
    pay["submission_id"] = pay.prolific_pid.map(submission_ids or {}).fillna(pay.session_id)
    pay["submission_id_source"] = np.where(pay.prolific_pid.isin((submission_ids or {}).keys()),
                                           "prolific export", "SESSION_ID from page")
    ok = pay[pay.submission_id.notna()]
    (out / "bonuses_prolific.txt").write_text(
        "".join(f"{r.submission_id},{r.bonus_usd:.2f}\n" for r in ok.itertuples()))
    pay[["prolific_pid", "submission_id", "submission_id_source", "condition", "n_correct", "bonus_usd"]].to_csv(
        out / "bonuses_review.csv", index=False)
    return p


def read_export(export: Path) -> tuple[pd.DataFrame, str | None, str | None]:
    sub = pd.read_csv(export)
    norm = {c: c.strip().lower().replace("_", " ") for c in sub.columns}
    pcol = next((c for c, n in norm.items() if n in ("participant id", "participant", "prolific pid")), None)
    scol = next((c for c, n in norm.items() if n in ("submission id", "session id")), None)
    return sub, pcol, scol


def cross_check(p: pd.DataFrame, export: Path) -> list[str]:
    sub, col, _ = read_export(export)
    if col is None:
        return [f"Could not find a participant ID column in {export.name}; columns: {list(sub.columns)}"]
    on_prolific = set(sub[col].astype(str))
    have_data = set(p.prolific_pid.dropna().astype(str))
    msgs = []
    missing = sorted(on_prolific - have_data)
    extra = sorted(have_data - on_prolific)
    if missing:
        msgs.append(f"{len(missing)} Prolific submission(s) with NO data file (review before approving): " + ", ".join(missing))
    if extra:
        msgs.append(f"{len(extra)} data file(s) with no matching Prolific submission: " + ", ".join(extra))
    if not msgs:
        msgs.append("Every Prolific submission has a matching data file.")
    return msgs


def cohens_d(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    sp = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
    return (b.mean() - a.mean()) / sp if sp > 0 else float("nan")


def fmt_p(x):
    return "p = n/a" if x is None or np.isnan(x) else ("p < 0.001" if x < 0.001 else f"p = {x:.3f}")


def run_stats(p: pd.DataFrame, trials: pd.DataFrame) -> list[str]:
    inc = p[p.included]
    t = trials[trials.file.isin(inc.file) & (trials.kind == "scored")].copy()
    t["lottery"] = (t.condition == "lottery").astype(int)
    t["correct_i"] = t.correct.astype(int)
    md = []

    # Descriptives
    desc = inc.groupby("condition").agg(
        n=("pid", "size"),
        grids_correct_mean=("n_correct", "mean"),
        grids_correct_sd=("n_correct", "std"),
        abs_error_mean=("mean_abs_error", "mean"),
        seconds_per_grid=("mean_rt_s", "mean"),
        timeouts_per_person=("n_timeouts", "mean"),
        bonus_rate=("n_correct", lambda s: (s >= inc.bonus_threshold.iloc[0]).mean()),
        effort_rating=("effort_rating", "mean"),
    ).reindex(COND_ORDER)
    md += ["## Descriptives (included participants)", "", desc.round(2).to_markdown(), ""]

    a = inc.loc[inc.condition == "fixed", "n_correct"]
    b = inc.loc[inc.condition == "lottery", "n_correct"]
    md.append("## Tests")
    md.append("")
    if len(a) >= 2 and len(b) >= 2:
        w = stats.ttest_ind(b, a, equal_var=False)
        u = stats.mannwhitneyu(b, a, alternative="two-sided")
        md.append(f"- Grids correct per person, lottery - fixed: {b.mean() - a.mean():+.2f} "
                  f"(Welch t = {w.statistic:.2f}, {fmt_p(w.pvalue)}; Mann-Whitney {fmt_p(u.pvalue)}; "
                  f"Cohen's d = {cohens_d(a, b):.2f})")

    def fit(label, fn):
        try:
            r = fn()
            coef, pv = r.params["lottery"], r.pvalues["lottery"]
            ci = r.conf_int().loc["lottery"]
            md.append(f"- {label}: lottery coefficient {coef:+.3f} [95% CI {ci[0]:+.3f}, {ci[1]:+.3f}], {fmt_p(pv)}")
        except Exception as e:  # small or degenerate samples
            md.append(f"- {label}: model did not fit ({type(e).__name__}: {e})")

    if t.lottery.nunique() == 2:
        fit("Per-grid correct (logistic GEE, clustered by participant; coefficient is log-odds)",
            lambda: smf.gee("correct_i ~ lottery + C(grid_id)", groups="pid", data=t,
                            family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable()).fit())
        ans = t[t.abs_error.notna()]
        fit("Per-grid absolute error (linear mixed model, random intercept per participant)",
            lambda: smf.mixedlm("abs_error ~ lottery + C(grid_id)", ans, groups=ans["pid"]).fit())
        sub = t[~t.timed_out].copy()
        sub["rt_s"] = sub.rt_ms / 1000
        fit("Seconds per grid, grids answered before the timer (linear mixed model)",
            lambda: smf.mixedlm("rt_s ~ lottery + C(grid_id)", sub, groups=sub["pid"]).fit())
        to = t.groupby(["pid", "condition"]).timed_out.mean().reset_index()
        md.append(f"- Share of grids that hit the time limit: fixed {to[to.condition=='fixed'].timed_out.mean():.1%}, "
                  f"lottery {to[to.condition=='lottery'].timed_out.mean():.1%}")
    md.append("")
    return md


def figures(p: pd.DataFrame, trials: pd.DataFrame, out: Path):
    inc = p[p.included]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    xs = np.arange(0, 11)
    for k, c in enumerate(COND_ORDER):
        counts = inc.loc[inc.condition == c, "n_correct"].value_counts().reindex(xs, fill_value=0)
        ax.bar(xs + (k - 0.5) * 0.4, counts.values, width=0.4, label=c, color=COLORS[c])
    ax.set_xticks(xs)
    ax.axvline(inc.bonus_threshold.iloc[0] - 0.5, color="#555", ls="--", lw=1)
    ax.text(inc.bonus_threshold.iloc[0] - 0.4, ax.get_ylim()[1] * 0.92, "bonus threshold", fontsize=9, color="#555")
    ax.set_xlabel("Grids counted exactly right (of 10)")
    ax.set_ylabel("Participants")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "fig_correct.png", dpi=160)
    plt.close(fig)

    t = trials[trials.file.isin(inc.file) & (trials.kind == "scored")]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    data = [t.loc[t.condition == c, "rt_ms"] / 1000 for c in COND_ORDER]
    ax.boxplot(data, tick_labels=COND_ORDER, widths=0.5)
    ax.set_ylabel("Seconds spent per grid")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "fig_time.png", dpi=160)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--prolific-export", type=Path)
    ap.add_argument("--seed", type=int, default=20261215,
                    help="lottery seed; state it in the report so the draw can be checked")
    ap.add_argument("--out", type=Path, default=Path("results"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    people, trials, skipped = load(args.data_dir)
    if people.empty:
        raise SystemExit(f"No usable data files in {args.data_dir}")
    p = apply_exclusions(score(people, trials))
    submission_ids = None
    if args.prolific_export:
        sub, pcol, scol = read_export(args.prolific_export)
        if pcol and scol:
            submission_ids = dict(zip(sub[pcol].astype(str), sub[scol].astype(str)))
    p = bonuses(p, args.seed, args.out, submission_ids)

    keep = ["pid", "condition", "condition_source", "n_correct", "n_grids", "mean_abs_error", "mean_rt_s",
            "n_timeouts", "n_blank", "attention_pass", "comprehension_attempts", "effort_rating",
            "tab_hidden", "included", "exclusion", "bonus_eligible", "bonus_usd", "started_at", "file", "comment"]
    p[keep].to_csv(args.out / "participants.csv", index=False)
    trials.to_csv(args.out / "trials.csv", index=False)

    md = ["# Results", ""]
    counts = p.groupby("condition").agg(total=("pid", "size"), included=("included", "sum")).reindex(COND_ORDER)
    md += ["## Sample", "", counts.to_markdown(), ""]
    excl = p.loc[~p.included, "exclusion"].value_counts()
    if len(excl):
        md += ["Exclusions: " + "; ".join(f"{k} ({v})" for k, v in excl.items()), ""]
    if skipped:
        md += [f"Ignored files: {len(skipped)} ({', '.join(sorted(set(r for _, r in skipped)))})", ""]
    if (p.condition_source == "random_fallback").any():
        md += [f"Note: {int((p.condition_source == 'random_fallback').sum())} participant(s) were assigned by "
               "coin flip because DataPipe was unreachable.", ""]
    md += run_stats(p, trials)
    paid = p[p.bonus_usd > 0]
    md += ["## Bonuses", "",
           f"- Fixed: {int((paid.condition == 'fixed').sum())} x ${FIXED_AMOUNT:.2f}",
           f"- Lottery: {int((paid.condition == 'lottery').sum())} winner(s) x ${LOTTERY_AMOUNT:.2f} "
           f"(seed {args.seed}; see lottery_draw.txt)",
           f"- Total bonuses: ${paid.bonus_usd.sum():.2f} (plus Prolific's fee)", ""]
    if args.prolific_export:
        md += ["## Prolific cross-check", "", *[f"- {m}" for m in cross_check(p, args.prolific_export)], ""]
    (args.out / "report.md").write_text("\n".join(md))
    figures(p, trials, args.out)
    print("\n".join(md))
    print(f"\nWrote outputs to {args.out}/")


if __name__ == "__main__":
    main()
