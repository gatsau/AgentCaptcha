"""numpy-based cross-session statistical analysis for Stage 4."""
import json
import numpy as np


def analyze_sessions(sessions: list[dict]) -> dict:
    """
    Analyse timing patterns across sessions for an agent_id.
    Returns {"consistent": bool, "reason": str, "stats": dict}.
    """
    timestamps = np.array([s["timestamp"] for s in sessions], dtype=float)
    intervals = np.diff(timestamps)

    if len(intervals) == 0:
        return {"consistent": True, "reason": "insufficient_intervals", "stats": {}}

    interval_mean = float(np.mean(intervals))
    interval_std = float(np.std(intervals))
    interval_cv = interval_std / interval_mean if interval_mean > 0 else 0.0

    # Extract per-session timing data (stage1 PoW solve times)
    stage1_times = []
    for s in sessions:
        try:
            t = json.loads(s.get("timings", "{}"))
            if "stage1" in t:
                stage1_times.append(float(t["stage1"]))
        except (json.JSONDecodeError, ValueError):
            pass

    stats = {
        "session_count": len(sessions),
        "interval_cv": interval_cv,
        "interval_mean_s": interval_mean,
    }

    if len(stage1_times) >= 3:
        s1_arr = np.array(stage1_times)
        s1_cv = float(np.std(s1_arr) / np.mean(s1_arr)) if np.mean(s1_arr) > 0 else 0.0
        stats["stage1_timing_cv"] = s1_cv

        # Agents should have very low PoW-solve CV (consistent compute)
        if s1_cv > 0.6:
            return {
                "consistent": False,
                "reason": f"stage1_timing_cv={s1_cv:.3f} > 0.6 (human-like variance)",
                "stats": stats,
            }

    # Check for hour-of-day distribution (agents run 24/7; humans cluster)
    hours = (timestamps % 86400) / 3600  # 0–24
    hour_std = float(np.std(hours))
    stats["hour_std"] = hour_std

    if len(sessions) >= 10 and hour_std < 3.0:
        return {
            "consistent": False,
            "reason": f"hour_std={hour_std:.2f} < 3.0 (sessions clustered in short window)",
            "stats": stats,
        }

    return {"consistent": True, "reason": "ok", "stats": stats}
