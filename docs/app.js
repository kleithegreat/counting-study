/* Counting study: lottery vs fixed bonus.
 *
 * Flow: consent -> condition assignment -> instructions -> comprehension check
 *       -> timed grids in random order (scored grids + one unannounced easy attention grid)
 *       -> effort question -> save to DataPipe -> redirect to Prolific.
 *
 * URL parameters:
 *   PROLIFIC_PID, STUDY_ID, SESSION_ID   filled in by Prolific
 *   test=1                               test run: file saved with TEST_ prefix,
 *                                        does not use DataPipe's condition counter
 *   condition=fixed|lottery              force a condition (test runs only)
 */
(function () {
  "use strict";

  const CFG = window.STUDY_CONFIG;
  const VERSION = "1.0.0";
  const params = new URLSearchParams(window.location.search);
  const app = document.getElementById("app");

  const LOCAL_MODE = !CFG.DATAPIPE_EXPERIMENT_ID || CFG.DATAPIPE_EXPERIMENT_ID === "REPLACE_ME";
  const TEST_RUN = LOCAL_MODE || params.get("test") === "1";

  const state = {
    meta: {
      version: VERSION,
      prolific_pid: params.get("PROLIFIC_PID") || null,
      study_id: params.get("STUDY_ID") || null,
      session_id: params.get("SESSION_ID") || null,
      participant_id: params.get("PROLIFIC_PID") || "anon-" + randomId(10),
      test_run: TEST_RUN,
      local_mode: LOCAL_MODE,
      condition: null,
      condition_source: null,
      started_at: new Date().toISOString(),
      finished_at: null,
      user_agent: navigator.userAgent,
      screen: `${window.screen.width}x${window.screen.height}`,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      seconds_per_grid: CFG.SECONDS_PER_GRID,
      bonus_threshold: CFG.BONUS_THRESHOLD,
      fixed_bonus: CFG.FIXED_BONUS,
      lottery_prize: CFG.LOTTERY_PRIZE,
      comprehension_attempts: 0,
      instructions_ms: null,
      effort_rating: null,
      comment: null,
      grid_order: null,
    },
    trials: [],
  };

  // ---------- helpers ----------
  function randomId(n) {
    const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    let s = "";
    const buf = new Uint32Array(n);
    crypto.getRandomValues(buf);
    for (let i = 0; i < n; i++) s += chars[buf[i] % chars.length];
    return s;
  }
  function shuffle(a) {
    const arr = a.slice();
    const buf = new Uint32Array(arr.length);
    crypto.getRandomValues(buf);
    for (let i = arr.length - 1; i > 0; i--) {
      const j = buf[i] % (i + 1);
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function render(html) {
    app.innerHTML = html;
    window.scrollTo(0, 0);
  }
  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
  function completionUrl() {
    return "https://app.prolific.com/submissions/complete?cc=" + encodeURIComponent(CFG.PROLIFIC_COMPLETION_CODE);
  }
  const nTotal = window.GRIDS.length;

  function bonusText(compact) {
    const t = CFG.BONUS_THRESHOLD, n = nTotal;
    if (state.meta.condition === "fixed") {
      return compact
        ? `<b>Bonus:</b> count at least ${t} of ${n} grids exactly right &rarr; you receive <b>${CFG.FIXED_BONUS}</b>.`
        : `If you count at least <b>${t} of the ${n}</b> grids exactly right, you will receive a <b>${CFG.FIXED_BONUS} bonus</b>.`;
    }
    return compact
      ? `<b>Bonus:</b> count at least ${t} of ${n} grids exactly right &rarr; you enter a draw for one <b>${CFG.LOTTERY_PRIZE}</b> prize.`
      : `If you count at least <b>${t} of the ${n}</b> grids exactly right, you will be entered into a <b>prize draw</b>. ` +
        `One <b>${CFG.LOTTERY_PRIZE} prize</b> will be drawn at random from all qualifying participants in this version of the study ` +
        `(about ${CFG.PARTICIPANTS_PER_CONDITION} people take part in it).`;
  }

  // ---------- screens ----------
  function screenDeviceCheck() {
    if (window.innerWidth < 600) {
      render(`<h1>Please use a computer</h1>
        <p>This study needs a laptop or desktop screen. Please return the study on Prolific and take it on a computer.</p>`);
      return false;
    }
    return true;
  }

  function screenConsent() {
    render(`
      <h1>Counting study</h1>
      <p>This is a short research study. You will count how many times a digit appears in a series of grids. It takes about ${CFG.EST_MINUTES} minutes.</p>
      <ul>
        <li>Base payment is made through Prolific. Some participants can also earn a bonus, explained on the next page.</li>
        <li>We record your answers, how long you take, and your Prolific ID (used only to pay bonuses). We do not collect your name or contact details.</li>
        <li>Taking part is voluntary. You may stop at any time by closing this page and returning the study on Prolific.
        Please note that you will only be paid if you complete the entire task.</li>
        <li>Questions: please message us through Prolific's message system.</li>
      </ul>
      <p>Do you agree to take part?</p>
      <div class="row">
        <button class="btn" id="agree">I agree</button>
        <button class="btn secondary" id="decline">I do not agree</button>
      </div>`);
    document.getElementById("agree").onclick = startAfterConsent;
    document.getElementById("decline").onclick = () =>
      render(`<h1>Thank you</h1><p>You chose not to take part. Please return the study on Prolific. No data was recorded.</p>`);
  }

  async function startAfterConsent() {
    render(`<p class="muted">Setting up&hellip;</p>`);
    await assignCondition();
    window.addEventListener("beforeunload", warnOnLeave);
    screenInstructions();
  }

  async function assignCondition() {
    const forced = params.get("condition");
    if (TEST_RUN) {
      if (CFG.CONDITIONS.includes(forced)) {
        state.meta.condition = forced;
        state.meta.condition_source = "url";
      } else {
        state.meta.condition = CFG.CONDITIONS[Math.random() < 0.5 ? 0 : 1];
        state.meta.condition_source = "random_test";
      }
      return;
    }
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const res = await fetch("https://pipe.jspsych.org/api/condition/", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "*/*" },
          body: JSON.stringify({ experimentID: CFG.DATAPIPE_EXPERIMENT_ID }),
        });
        const body = await res.json();
        if (res.ok && Number.isInteger(body.condition) && CFG.CONDITIONS[body.condition]) {
          state.meta.condition = CFG.CONDITIONS[body.condition];
          state.meta.condition_source = "datapipe";
          return;
        }
      } catch (e) { /* retry */ }
      await sleep(800 * (attempt + 1));
    }
    // DataPipe unreachable: fall back to a coin flip so the participant can continue.
    state.meta.condition = CFG.CONDITIONS[Math.random() < 0.5 ? 0 : 1];
    state.meta.condition_source = "random_fallback";
  }

  function warnOnLeave(e) {
    e.preventDefault();
    e.returnValue = "";
  }

  function screenInstructions() {
    const tInstr = performance.now();
    render(`
      <h1>Instructions</h1>
      <p>You will see <b>${nTotal} grids</b> of digits, one at a time. For each grid, count how many times the digit
      <b>7</b> appears, type the number, and press <b>Enter</b> (or click Submit).</p>
      <p>Each grid has a <b>${CFG.SECONDS_PER_GRID}-second</b> time limit (shown at the top right). When time runs out,
      whatever you have typed is submitted automatically and the next grid appears.</p>
      <div class="bonus">${bonusText(false)}</div>
      <p class="muted">Bonuses are paid through Prolific within a week after the study closes.</p>
      <div class="row"><button class="btn" id="next">Continue</button></div>`);
    document.getElementById("next").onclick = () => {
      state.meta.instructions_ms = Math.round(performance.now() - tInstr);
      screenComprehension();
    };
  }

  function screenComprehension(wrongBefore) {
    // Options mention only this participant's own bonus, never the other condition's.
    const options = shuffle(state.meta.condition === "fixed"
      ? [
          { key: "correct", text: `I receive a ${CFG.FIXED_BONUS} bonus.` },
          { key: "wrong", text: `I receive ${CFG.FIXED_BONUS} for each grid I count exactly right.` },
          { key: "none", text: "Nothing extra happens." },
        ]
      : [
          { key: "correct", text: `I am entered into a draw for one ${CFG.LOTTERY_PRIZE} prize.` },
          { key: "wrong", text: `I receive ${CFG.LOTTERY_PRIZE}.` },
          { key: "none", text: "Nothing extra happens." },
        ]);
    render(`
      <h1>Quick check</h1>
      ${wrongBefore ? `<p class="error">That's not right. Please read the bonus rule again:</p><div class="bonus">${bonusText(false)}</div>` : ""}
      <p>What happens if you count at least ${CFG.BONUS_THRESHOLD} of the ${nTotal} grids exactly right?</p>
      ${options.map((o) => `<label class="choice"><input type="radio" name="cq" value="${o.key}"> ${esc(o.text)}</label>`).join("")}
      <div class="row"><button class="btn" id="next" disabled>Start counting</button></div>`);
    const btn = document.getElementById("next");
    app.querySelectorAll('input[name="cq"]').forEach((el) => (el.onchange = () => (btn.disabled = false)));
    btn.onclick = () => {
      state.meta.comprehension_attempts += 1;
      const val = app.querySelector('input[name="cq"]:checked').value;
      if (val === "correct") runTrials();
      else screenComprehension(true);
    };
  }

  // ---------- trials ----------
  async function runTrials() {
    const order = shuffle(window.GRIDS);
    state.meta.grid_order = order.map((g) => g.id);
    for (let i = 0; i < order.length; i++) {
      render(`<div class="center"><p class="muted">Grid ${i + 1} of ${order.length}</p><h1>Get ready&hellip;</h1></div>`);
      await sleep(CFG.READY_MS);
      const result = await runOneTrial(order[i], i);
      state.trials.push(result);
    }
    screenEffort();
  }

  function drawGrid(canvas, cells) {
    const rows = cells.length, cols = cells[0].length;
    const cell = Math.min(40, Math.floor((Math.min(app.clientWidth, 640) - 20) / cols));
    const dpr = window.devicePixelRatio || 1;
    canvas.width = cols * cell * dpr;
    canvas.height = rows * cell * dpr;
    canvas.style.width = cols * cell + "px";
    canvas.style.height = rows * cell + "px";
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, cols * cell, rows * cell);
    ctx.fillStyle = "#1d1d1f";
    ctx.font = `${Math.round(cell * 0.6)}px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++)
        ctx.fillText(String(cells[r][c]), c * cell + cell / 2, r * cell + cell / 2 + 1);
  }

  function runOneTrial(grid, position) {
    return new Promise((resolve) => {
      const limitSec = CFG.SECONDS_PER_GRID;
      const limitMs = limitSec * 1000;
      render(`
        <div class="bonus compact">${bonusText(true)}</div>
        <div class="trial-head">
          <span class="muted">Grid ${position + 1} of ${nTotal} &middot; count the <b>7</b>s</span>
          <span class="timer" id="timer">${limitSec}s</span>
        </div>
        <div class="bar"><div id="bar" style="width:100%"></div></div>
        <canvas id="grid" aria-label="grid of digits"></canvas>
        <form class="answer" id="form" autocomplete="off">
          <label for="ans">Number of 7s:</label>
          <input id="ans" type="number" inputmode="numeric" min="0" max="100" step="1">
          <button class="btn" id="submit" type="submit" disabled>Submit</button>
        </form>`);
      const canvas = document.getElementById("grid");
      drawGrid(canvas, grid.cells);
      const input = document.getElementById("ans");
      const submitBtn = document.getElementById("submit");
      const timerEl = document.getElementById("timer");
      const barEl = document.getElementById("bar");
      input.focus();

      const t0 = performance.now();
      let firstInputMs = null, nEdits = 0, hiddenCount = 0, done = false;
      input.addEventListener("input", () => {
        nEdits += 1;
        submitBtn.disabled = !/^\d+$/.test(input.value.trim());
        if (firstInputMs === null) firstInputMs = Math.round(performance.now() - t0);
      });
      const onVis = () => { if (document.hidden) hiddenCount += 1; };
      document.addEventListener("visibilitychange", onVis);

      function finish(timedOut) {
        if (done) return;
        done = true;
        clearInterval(tick);
        document.removeEventListener("visibilitychange", onVis);
        const rtMs = Math.min(Math.round(performance.now() - t0), limitMs);
        const raw = input.value.trim();
        const parsed = /^\d+$/.test(raw) ? parseInt(raw, 10) : null;
        resolve({
          position: position + 1,
          grid_id: grid.id,
          kind: grid.kind,
          answer: parsed,
          raw_input: raw,
          correct_answer: grid.answer,
          correct: parsed === grid.answer,
          abs_error: parsed === null ? null : Math.abs(parsed - grid.answer),
          rt_ms: rtMs,
          timed_out: timedOut,
          first_input_ms: firstInputMs,
          n_edits: nEdits,
          tab_hidden_count: hiddenCount,
        });
      }

      const tick = setInterval(() => {
        const elapsed = performance.now() - t0;
        const left = Math.max(0, limitMs - elapsed);
        timerEl.textContent = Math.ceil(left / 1000) + "s";
        timerEl.classList.toggle("low", left <= 5000);
        barEl.style.width = (100 * left) / limitMs + "%";
        if (left <= 0) finish(true);
      }, 100);

      document.getElementById("form").onsubmit = (e) => {
        e.preventDefault();
        if (submitBtn.disabled) { input.focus(); return; }
        finish(false);
      };
    });
  }

  // ---------- end ----------
  function screenEffort() {
    render(`
      <h1>Almost done</h1>
      <p>How much effort did you put into counting accurately? (This does not affect your payment.)</p>
      <div class="scale">${[1, 2, 3, 4, 5, 6, 7].map((v) => `<label><input type="radio" name="eff" value="${v}"> ${v}</label>`).join("")}</div>
      <p class="muted">1 = very little effort, 7 = as much as I could</p>
      <p>Any comments? (optional)</p>
      <textarea id="comment" rows="3" maxlength="1000"></textarea>
      <div class="row"><button class="btn" id="next" disabled>Finish</button></div>`);
    const btn = document.getElementById("next");
    app.querySelectorAll('input[name="eff"]').forEach((el) => (el.onchange = () => (btn.disabled = false)));
    btn.onclick = () => {
      state.meta.effort_rating = parseInt(app.querySelector('input[name="eff"]:checked').value, 10);
      state.meta.comment = document.getElementById("comment").value.trim() || null;
      state.meta.finished_at = new Date().toISOString();
      saveAndFinish();
    };
  }

  function dataFilename() {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    return `${TEST_RUN ? "TEST_" : ""}${state.meta.participant_id}_${stamp}.json`;
  }

  async function saveAndFinish() {
    window.removeEventListener("beforeunload", warnOnLeave);
    const payload = JSON.stringify(state);
    window.__STUDY_DATA__ = state; // for automated tests

    if (LOCAL_MODE) return screenLocalDone(payload);

    render(`<p class="muted">Saving your answers&hellip; please don't close this page.</p>`);
    const filename = dataFilename();
    let saved = false;
    for (let attempt = 0; attempt < 4 && !saved; attempt++) {
      try {
        const res = await fetch("https://pipe.jspsych.org/api/data/", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "*/*" },
          body: JSON.stringify({ experimentID: CFG.DATAPIPE_EXPERIMENT_ID, filename, data: payload }),
        });
        if (res.status === 201 || res.status === 202) saved = true;
        else {
          const body = await res.json().catch(() => ({}));
          if (body.error === "FILE_EXISTS") saved = true; // an earlier retry already landed
        }
      } catch (e) { /* network error: retry */ }
      if (!saved) await sleep(1000 * (attempt + 1));
    }
    if (saved) {
      render(`<h1>Thank you!</h1><p>Your answers are saved. Returning you to Prolific&hellip;</p>
        <p class="muted">If nothing happens, <a href="${completionUrl()}">click here</a>.</p>`);
      setTimeout(() => (window.location.href = completionUrl()), 1500);
    } else {
      screenSaveFailed(payload, filename);
    }
  }

  function downloadButton(payload, filename) {
    const blob = new Blob([payload], { type: "application/json" });
    return `<a class="btn secondary" download="${esc(filename)}" href="${URL.createObjectURL(blob)}">Download my answers</a>`;
  }

  function screenSaveFailed(payload, filename) {
    render(`<h1>Thank you!</h1>
      <p class="error">We couldn't reach our data server. You will still be paid.</p>
      <p>Your Prolific completion code is:</p><p class="code">${esc(CFG.PROLIFIC_COMPLETION_CODE)}</p>
      <p>To help us keep your answers (and pay any bonus), please download the file below and send it to us
      through Prolific's message system.</p>
      <div class="row">${downloadButton(payload, filename)}<a class="btn" href="${completionUrl()}">Return to Prolific</a></div>`);
  }

  function screenLocalDone(payload) {
    const nCorrect = state.trials.filter((t) => t.correct).length;
    render(`<h1>Local test finished</h1>
      <p class="muted">DATAPIPE_EXPERIMENT_ID is not set, so nothing was saved. This screen is only shown in local test mode.</p>
      <p>Condition: <b>${esc(state.meta.condition)}</b> &middot; grids correct: <b>${nCorrect}/${state.trials.length}</b> (bonus needs ${CFG.BONUS_THRESHOLD})</p>
      <div class="row">${downloadButton(payload, dataFilename())}</div>
      <pre style="white-space:pre-wrap;font-size:12px;max-height:300px;overflow:auto">${esc(JSON.stringify(state, null, 2))}</pre>`);
  }

  // ---------- go ----------
  if (screenDeviceCheck()) screenConsent();
})();
