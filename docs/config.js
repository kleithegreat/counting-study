// ============================================================
//  STUDY SETTINGS - the only file you need to edit before launch
// ============================================================
window.STUDY_CONFIG = {
  // From your DataPipe experiment dashboard (pipe.jspsych.org).
  // Leave as "REPLACE_ME" to run in local test mode (nothing is saved;
  // you get a download button with the data at the end instead).
  DATAPIPE_EXPERIMENT_ID: "REPLACE_ME",

  // From Prolific: Study setup -> Study completion -> completion code.
  PROLIFIC_COMPLETION_CODE: "C12XGGIW",

  // Task parameters (keep in sync with the Prolific listing).
  SECONDS_PER_GRID: 25,
  READY_MS: 800,               // "Get ready" pause between grids
  BONUS_THRESHOLD: 7,          // out of all grids shown, the easy attention grid included
  FIXED_BONUS: "$0.25",
  LOTTERY_PRIZE: "$3",
  PARTICIPANTS_PER_CONDITION: 25,
  EST_MINUTES: 4,

  // DataPipe condition number -> condition name.
  CONDITIONS: ["fixed", "lottery"],
};
