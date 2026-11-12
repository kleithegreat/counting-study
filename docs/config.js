// ============================================================
//  STUDY SETTINGS - the only file you need to edit before launch
// ============================================================
window.STUDY_CONFIG = {
  // From your DataPipe experiment dashboard (pipe.jspsych.org).
  // Leave as "REPLACE_ME" to run in local test mode (nothing is saved;
  // you get a download button with the data at the end instead).
  DATAPIPE_EXPERIMENT_ID: "REPLACE_ME",

  // From Prolific: Study setup -> Study completion -> completion code.
  PROLIFIC_COMPLETION_CODE: "REPLACE_ME",

  // Task parameters (keep in sync with the proposal / Prolific listing).
  SECONDS_PER_GRID: 25,
  ATTENTION_SECONDS: 10,       // the easy attention-check grid
  READY_MS: 800,               // "Get ready" pause between grids
  BONUS_THRESHOLD: 8,          // out of the 10 scored grids
  N_SCORED: 10,
  FIXED_BONUS: "$0.25",
  LOTTERY_PRIZE: "$4",
  PARTICIPANTS_PER_CONDITION: 30,
  BASE_PAY: "$0.67",
  EST_MINUTES: 5,
  CONTACT: "the CS 5306 Project 3 team (Kevin Lei, Kyungmin Nam, Brittany Sun) via Prolific's message system",

  // DataPipe condition number -> condition name.
  CONDITIONS: ["fixed", "lottery"],
};
