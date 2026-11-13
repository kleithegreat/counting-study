# Lottery vs. fixed bonus: counting study (CS 5306 Project 3)

Team Katseye: Kevin Lei (kl2344), Kyungmin Nam (kn467), Brittany Sun (bs835)

Workers count the 7s in 9 grids of digits (25 s per grid): 8 counting grids plus one easy attention-check
grid that is mixed in unannounced. The bonus needs 7+ of the 9 correct. Half get a fixed $0.25 bonus;
half get entered into a draw for one $3 prize.
Prolific recruits and pays. The task itself is a static web page on GitHub Pages
(https://kleithegreat.github.io/counting-study/), and data is saved through DataPipe to Google Drive.

```
docs/        the study page (GitHub Pages serves this folder)
  config.js  <- the ONLY file to edit before launch
stimuli/     grid generator, answer key, preview PNGs
analysis/    scoring, bonuses, lottery draw, stats, figures
tests/       browser test + fake-data generator
```

## Launch checklist

### 1. DataPipe: saves the data (done)
Experiment `counting-study` at https://pipe.jspsych.org (ID `3NXc8KaTmRbg`, already in `docs/config.js`), saving to
Google Drive. Dashboard settings:
- **Accept new data**: ON.
- **Assign conditions in sequence**: ON, 2 conditions (0 = fixed, 1 = lottery; DataPipe alternates 0, 1, 0, 1).
- **Stop after a set number of sessions**: OFF (test runs count as sessions too).
- **Check submissions before storing them**: JSON allowed, **no required fields**. The default `trial_type` field
  is for jsPsych and would reject every submission.

### 2. GitHub Pages: hosts the page (done)
Pages serves `/docs` from `main` at https://kleithegreat.github.io/counting-study/. Every push to `main` redeploys it within a minute or so.
The repo name is deliberately neutral, because participants can see the URL.

### 3. Prolific (teammate)
| Setting | Value |
| --- | --- |
| Study URL | the GitHub Pages link above; choose **"I'll use URL parameters"** so Prolific appends `PROLIFIC_PID`, `STUDY_ID`, `SESSION_ID` |
| Study completion | **"I'll redirect them using a URL"**. The page sends people to `https://app.prolific.com/submissions/complete?cc=C12XGGIW`; if Prolific's completion code ever changes, update `PROLIFIC_COMPLETION_CODE` in `docs/config.js` and push |
| Devices | Desktop only |
| Estimated time | 4 minutes |
| Reward | $0.54 (= $8.10/hr, Prolific's minimum) |
| Places | **10** first (soft launch), then raise to **50** |
| Suggested filters | approval rate >= 95%, fluent English |

Title: **Count the 7s (about 4 minutes)**

Description:
> In this short study you will see 9 grids of digits, one at a time, and count how many times the digit 7
> appears in each. Each grid has a 25-second time limit, shown on screen.
>
> You can earn a bonus for accurate counting. The details are shown at the start of the study.
>
> Please use a laptop or desktop computer and complete the study in one sitting. You will only be paid if
> you complete the entire task. We record your answers, response times and Prolific ID; we do not collect
> your name or contact details. If you have questions, please message us through Prolific.

Don't describe the two bonus versions in the listing. Each person should only see their own.

### 4. Test before launch
**Any run without `?test=1` is saved as a real participant and uses up a condition slot.** So:
- To try the study yourself, always use `https://kleithegreat.github.io/counting-study/?test=1`. Test runs are saved as
  `TEST_...json`, which the analysis ignores. Add `&condition=lottery` or `&condition=fixed` to see each version.
- Prolific's **Preview** checks the redirect back to Prolific, but it opens the plain study URL, so the run is saved as
  real data. Afterwards, delete that file from the Google Drive folder. It has the newest timestamp and the
  previewer's Prolific ID.

### 5. Soft launch, then full launch
Publish with 10 places. When they finish, check:
- median completion time on Prolific is 4 minutes or less. Worst case, if someone uses every second, is about 5 minutes.
  If the median runs over, Prolific will ask for top-up payments;
- the score spread: run the analysis (below) and look at `bonus_rate`. Roughly 30-70% should qualify.
  If almost nobody or almost everybody qualifies, change the threshold **before** adding places.

If nothing changes, keep those 10 in the data and raise places to 50.

## After data collection

1. In Google Drive, download the DataPipe folder and unzip it into `data/`.
2. On Prolific, export the submissions CSV (Submissions -> download).
3. Run:
   ```
   pip install pandas numpy scipy statsmodels matplotlib tabulate
   python analysis/analyze.py data --prolific-export prolific_export.csv --out results
   ```
4. Read `results/report.md`, especially the **Prolific cross-check** section. Any submission with **no data file**
   didn't do the task. Review or reject it before approving.
5. Approve submissions, then pay bonuses. Check `results/bonuses_review.csv` first. Then go to Prolific -> your study's
   submissions -> **Bulk actions -> Bulk bonus payment** and paste `results/bonuses_prolific.txt`.
   Prolific requires **Submission IDs**, not Participant IDs; the script takes them from the Prolific export, so always
   pass `--prolific-export`. Bonuses carry the same 33.3% platform fee, so top up the balance by about $10 first.
   - Bonus rule is exactly what participants were told: 7+ of the 9 grids shown correct, the easy attention grid
     included. It also applies to people excluded from the analysis, such as those who failed the attention check.
   - The lottery winner is drawn with fixed seed **20261215**, committed to this repo before data collection.
     `results/lottery_draw.txt` lists everyone eligible and the winner, so anyone can re-run and check it.

### What the analysis does
- **Exclusions** (from the analysis, not from pay): failed attention-check grid, duplicate attempts (first kept),
  or 5+ blank answers. Outcomes use only the 8 counting grids.
- **Outcomes**: grids correct per person (Welch t-test, Mann-Whitney, Cohen's d); per-grid correctness (logistic GEE
  clustered by participant, with grid fixed effects); absolute error and seconds per grid (linear mixed models,
  random intercept per participant); share of grids that hit the timer.
- **Figures**: `fig_correct.png` (grids correct by condition, with the bonus threshold marked), `fig_time.png`.

## Re-running the tests
```
python stimuli/make_grids.py          # regenerate grids (fixed seed: identical output)
python tests/e2e_test.py              # headless Chrome run-through of both conditions, save failure, phone block
python tests/simulate_data.py tests/sim/data && \
python analysis/analyze.py tests/sim/data --prolific-export tests/sim/prolific_export.csv --out tests/sim/results
```

## Data recorded per participant
`meta`: Prolific IDs, condition and how it was assigned, comprehension-check attempts, time on instructions, effort
rating (1-7), comment, grid order, browser and screen size, start and finish times.
`trials` (one per grid): answer, correct answer, correct?, absolute error, time taken (ms, capped at the limit),
timed out?, time to first keystroke, number of edits, and how many times the tab was hidden.
