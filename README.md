# Lottery vs. fixed bonus: counting study (CS 5306 Project 3)

Team Katseye: Kevin Lei (kl2344), Kyungmin Nam (kn467), Brittany Sun (bs835)

Workers count the 7s in 10 grids of digits (25 s per grid) plus one easy attention-check grid.
Half get a fixed $0.25 bonus for 8+ correct; half get entered into a draw for one $4 prize.
Prolific recruits and pays. The task itself is a static web page on GitHub Pages, and data is
saved through DataPipe to Google Drive.

```
docs/        the study page (GitHub Pages serves this folder)
  config.js  <- the ONLY file to edit before launch
stimuli/     grid generator, answer key, preview PNGs
analysis/    scoring, bonuses, lottery draw, stats, figures
tests/       browser test + fake-data generator
```

## Launch checklist

### 1. DataPipe: saves the data (about 10 min, one person)
1. Sign in at https://pipe.jspsych.org.
2. **Account settings -> Connect** next to **Google Drive** and sign in with the Google account that should hold the data.
3. **New Experiment**: title "CS5306 counting study", provider Google Drive.
4. On the experiment dashboard:
   - turn **Accept new data** ON,
   - turn **Condition assignment** ON and set the number of conditions to **2**
     (0 = fixed, 1 = lottery; DataPipe alternates 0, 1, 0, 1 so groups stay balanced).
5. Copy the **experiment ID** into `docs/config.js` -> `DATAPIPE_EXPERIMENT_ID`.

### 2. GitHub Pages: hosts the page (about 5 min)
1. Create a **public** GitHub repo (for example `cs5306-counting`) and push this folder to it.
2. Repo **Settings -> Pages**. Source: *Deploy from a branch*, branch `main`, folder **`/docs`**.
3. After a minute the page is live at `https://<username>.github.io/cs5306-counting/`.

### 3. Prolific (teammate)
| Setting | Value |
| --- | --- |
| Study URL | the GitHub Pages link above; choose **"I'll use URL parameters"** so Prolific appends `PROLIFIC_PID`, `STUDY_ID`, `SESSION_ID` |
| Study completion | **"I'll redirect them using a URL"**; copy the code into `docs/config.js` -> `PROLIFIC_COMPLETION_CODE`, then push |
| Devices | Desktop only |
| Estimated time | 5 minutes |
| Reward | $0.67 (= $8.04/hr, Prolific's minimum) |
| Places | **10** first (soft launch), then raise to **60** |
| Suggested filters | approval rate >= 95%, fluent English |

Suggested listing text:
> **Count the 7s (about 5 minutes)**. Count how many times the digit 7 appears in a series of grids of
> digits. Each grid has a 25-second time limit. You can earn a bonus for accurate counting; the details
> are shown at the start. Please use a laptop or desktop computer.

Don't describe the two bonus versions in the listing. Each person should only see their own.

### 4. Test before launch
- Open `https://<username>.github.io/cs5306-counting/?test=1` and run through it. Test runs are saved as `TEST_...json`
  and don't use up DataPipe's condition counter. Add `&condition=lottery` or `&condition=fixed` to see each version.
  Check that the file shows up in Google Drive.
- Use Prolific's **Preview** to check the redirect back to Prolific.
- Each teammate should do one full run and note their time and how many grids they got right. If careful
  people can't finish a grid in 25 s, raise `SECONDS_PER_GRID` (and the time estimate and pay to match).
- If `DATAPIPE_EXPERIMENT_ID` is still `REPLACE_ME`, the page runs in **local mode**. It saves nothing and shows
  your data at the end. You can open `docs/index.html` directly in a browser to try it.

### 5. Soft launch, then full launch
Publish with 10 places. When they finish, check:
- median completion time on Prolific is 5 minutes or less. Worst case, if someone uses every second, is about 5.5 minutes.
  If the median runs over, Prolific will ask for top-up payments;
- the score spread: run the analysis (below) and look at `bonus_rate`. Roughly 30-70% should qualify.
  If almost nobody or almost everybody qualifies, change the threshold **before** adding places.

If nothing changes, keep those 10 in the data and raise places to 60.

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
   - Bonus rule is exactly what participants were told: 8+ of 10 counting grids correct. It also applies to people
     excluded from the analysis, such as those who failed the attention check.
   - The lottery winner is drawn with fixed seed **20261215**, written in the proposal ahead of time.
     `results/lottery_draw.txt` lists everyone eligible and the winner, so anyone can re-run and check it.

### What the analysis does
- **Exclusions** (from the analysis, not from pay): failed attention-check grid, duplicate attempts (first kept),
  incomplete, or 5+ blank answers.
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
