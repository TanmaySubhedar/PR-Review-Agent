export const colors = {
  bg:            "#08091a",
  surface:       "#0d0b28",
  surface2:      "#12103a",
  surface3:      "#1a1650",
  border:        "rgba(79,182,255,0.1)",
  borderStrong:  "rgba(79,182,255,0.2)",
  text:          "#f0f2ff",
  muted:         "#7a7ea8",
  accent:        "#C301B1",          // Vivid Magenta
  accentDim:     "rgba(195,1,177,0.15)",
  risk: {
    low:       "#4FB6FF",            // Sky Blue — calm/safe
    lowDim:    "rgba(79,182,255,0.15)",
    medium:    "#f59e0b",
    mediumDim: "rgba(245,158,11,0.15)",
    high:      "#ef4444",
    highDim:   "rgba(239,68,68,0.15)",
  },
  status: {
    pending:    "#475569",
    running:    "#C301B1",           // Magenta — active
    runningDim: "rgba(195,1,177,0.15)",
    done:       "#4FB6FF",           // Sky Blue — complete
    failed:     "#ef4444",
  },
  severity: {
    info:     "#4FB6FF",
    minor:    "#f59e0b",
    major:    "#f97316",
    blocking: "#ef4444",
  },
  dim: {
    info:     "rgba(79,182,255,0.15)",
    minor:    "rgba(245,158,11,0.15)",
    major:    "rgba(249,115,22,0.15)",
    blocking: "rgba(239,68,68,0.15)",
  },
  medium: "#f59e0b",
  // legacy aliases
  ink:  "#f0f2ff",
  line: "rgba(79,182,255,0.1)",
  soft: "#12103a",
};

export const brand = {
  name:    "Sentinel PR",
  tagline: "Catches what a quick glance misses — before it ships.",
  team:    "AutomatonsX",
};
