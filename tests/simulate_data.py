"""Make fake participant files in the same format the page saves, to test analyze.py.

    python tests/simulate_data.py OUT_DIR [--n 30] [--effect 0.08]

Also writes OUT_DIR/../prolific_export.csv with one extra submission that has no
data file, so the Prolific cross-check has something to catch.
"""
import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_grids():
    src = (ROOT / "docs" / "grids.js").read_text()
    return json.loads(src[src.index("["): src.rindex("]") + 1])


def person(rng, grids, pid, condition, effect, t0):
    p_correct = min(0.95, max(0.05, rng.gauss(0.72, 0.12) + (effect if condition == "lottery" else 0)))
    order = grids[:]
    rng.shuffle(order)
    trials = []
    for i, g in enumerate(order):
        limit = 10000 if g["kind"] == "attention" else 25000
        if g["kind"] == "attention":
            ok = rng.random() < 0.95
        else:
            ok = rng.random() < p_correct
        timed_out = rng.random() < 0.06
        ans = None if (timed_out and rng.random() < 0.5) else (
            g["answer"] if ok else max(0, g["answer"] + rng.choice([-2, -1, 1, 2])))
        rt = limit if timed_out else int(min(limit - 1, rng.gauss(17000 if condition == "lottery" else 15500, 3500)))
        trials.append({
            "position": i + 1, "grid_id": g["id"], "kind": g["kind"], "answer": ans,
            "raw_input": "" if ans is None else str(ans), "correct_answer": g["answer"],
            "correct": ans == g["answer"], "abs_error": None if ans is None else abs(ans - g["answer"]),
            "rt_ms": max(1500, rt), "timed_out": timed_out, "first_input_ms": None,
            "n_edits": 2, "tab_hidden_count": 0,
        })
    meta = {
        "version": "1.0.0", "prolific_pid": pid, "study_id": "sim", "session_id": "sim",
        "participant_id": pid, "test_run": False, "local_mode": False, "condition": condition,
        "condition_source": "datapipe", "started_at": t0.isoformat(),
        "finished_at": (t0 + timedelta(minutes=5)).isoformat(), "user_agent": "sim", "screen": "1920x1080",
        "viewport": "1400x900", "seconds_per_grid": 25, "bonus_threshold": 8, "n_scored": 10,
        "fixed_bonus": "$0.25", "lottery_prize": "$4", "comprehension_attempts": rng.choice([1, 1, 1, 2]),
        "instructions_ms": 20000, "effort_rating": rng.randint(4, 7), "comment": None,
        "grid_order": [g["id"] for g in order],
    }
    return {"meta": meta, "trials": trials}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--effect", type=float, default=0.08)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    grids = load_grids()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)
    pids = []
    for i in range(2 * args.n):
        cond = ["fixed", "lottery"][i % 2]
        pid = f"sim{i:03d}" + "0" * 18
        pids.append(pid)
        d = person(rng, grids, pid, cond, args.effect, t0 + timedelta(minutes=i))
        (args.out / f"{pid}_{i}.json").write_text(json.dumps(d))
    # a duplicate attempt and a test file, both of which analyze.py should skip/flag
    dup = person(rng, grids, pids[0], "fixed", 0, t0 + timedelta(hours=3))
    (args.out / f"{pids[0]}_dup.json").write_text(json.dumps(dup))
    test = person(rng, grids, "TESTER", "lottery", 0, t0)
    test["meta"]["test_run"] = True
    (args.out / "TEST_TESTER_x.json").write_text(json.dumps(test))
    export = args.out.parent / "prolific_export.csv"
    export.write_text("Submission id,Participant id,Status\n" +
                      "".join(f"s{i},{p},APPROVED\n" for i, p in enumerate(pids + ["nodata00000000000000000x"])))
    print(f"Wrote {2 * args.n} participants (+1 duplicate, +1 test file) to {args.out}")


if __name__ == "__main__":
    main()
