"""
Redrob Ranking Pipeline
========================
Orchestrates loading, scoring, and ranking of all candidates from JSONL.
Produces a top-100 submission CSV.
"""
import csv
import json
import time
from pathlib import Path
from typing import Optional
from .scorer import compute_score, generate_reasoning, strip_html, DEFAULT_JOB


def load_candidates_jsonl(path: str | Path, max_candidates: int = 0) -> list[dict]:
    """Stream candidates from JSONL file."""
    candidates = []
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if max_candidates and len(candidates) >= max_candidates:
                break
    return candidates


def load_candidates_json(path: str | Path) -> list[dict]:
    """Load from sample JSON file (array format)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return [data]


def run_pipeline(
    candidates_path: str | Path,
    job: dict = DEFAULT_JOB,
    weights: Optional[dict] = None,
    max_candidates: int = 0,
    top_n: int = 100,
    use_sample: bool = False,
    progress_callback=None,
) -> dict:
    """
    Full ranking pipeline.

    Returns:
        {
          "ranked": [{"rank", "candidate_id", "score", "reasoning", "components", "profile"}],
          "stats": {total, duration_sec, avg_score, ...},
          "submission_rows": [{"candidate_id", "rank", "score", "reasoning"}],
        }
    """
    start = time.time()

    # Load candidates
    p = Path(candidates_path)
    if use_sample:
        if p.exists():
            candidates = load_candidates_json(p)
        else:
            candidates = []
    else:
        if p.exists():
            candidates = load_candidates_jsonl(p, max_candidates=max_candidates)
        else:
            candidates = []

    total = len(candidates)
    if total == 0:
        return {"error": "No candidates loaded", "ranked": [], "stats": {}}

    # Score all
    scored = []
    for i, cand in enumerate(candidates):
        if progress_callback and i % 500 == 0:
            progress_callback(i, total)
        try:
            final_score, components = compute_score(cand, job, weights)
            scored.append({
                "candidate_id": cand.get("candidate_id", f"CAND_{i:07d}"),
                "final_score": final_score,
                "components": components,
                "candidate": cand,
            })
        except Exception:
            continue

    # Sort descending by score, tie-break by candidate_id ascending
    scored.sort(key=lambda x: (-x["final_score"], x["candidate_id"]))

    # Top-N
    top = scored[:top_n]

    # Normalize scores to [0, 1] within top-N for submission
    if top:
        max_s = top[0]["final_score"]
        min_s = top[-1]["final_score"]
        score_range = max_s - min_s if max_s != min_s else 1.0
    else:
        max_s, min_s, score_range = 1.0, 0.0, 1.0

    ranked = []
    submission_rows = []
    for rank, item in enumerate(top, 1):
        cand = item["candidate"]
        raw_score = item["final_score"]
        components = item["components"]

        # Normalize to [0.2, 1.0] range for submission
        if max_s == min_s:
            norm_score = 1.0
        else:
            norm_score = round(0.2 + 0.8 * (raw_score - min_s) / score_range, 4)

        reasoning = generate_reasoning(cand, components, rank)

        ranked.append({
            "rank": rank,
            "candidate_id": item["candidate_id"],
            "score": norm_score,
            "raw_score": raw_score,
            "reasoning": reasoning,
            "components": components,
            "profile": cand.get("profile", {}),
            "skills": cand.get("skills", []),
            "signals": cand.get("redrob_signals", {}),
            "education": cand.get("education", []),
        })
        submission_rows.append({
            "candidate_id": item["candidate_id"],
            "rank": rank,
            "score": norm_score,
            "reasoning": strip_html(reasoning),
        })

    duration = round(time.time() - start, 2)

    # Stats
    all_scores = [s["final_score"] for s in scored]
    avg_score = round(sum(all_scores) / len(all_scores), 4) if all_scores else 0

    # Skill distribution
    skill_counts: dict[str, int] = {}
    for s in scored[:500]:  # sample first 500 for speed
        for sk in s["candidate"].get("skills", []):
            name = sk.get("name", "").strip()
            if name:
                skill_counts[name] = skill_counts.get(name, 0) + 1

    top_skills = sorted(skill_counts.items(), key=lambda x: -x[1])[:20]

    # Industry distribution
    industry_counts: dict[str, int] = {}
    for s in scored[:500]:
        ind = s["candidate"].get("profile", {}).get("current_industry", "Unknown")
        industry_counts[ind] = industry_counts.get(ind, 0) + 1

    top_industries = sorted(industry_counts.items(), key=lambda x: -x[1])[:10]

    stats = {
        "total_candidates": total,
        "scored_candidates": len(scored),
        "duration_sec": duration,
        "avg_score": avg_score,
        "max_score": round(max(all_scores), 4) if all_scores else 0,
        "min_score": round(min(all_scores), 4) if all_scores else 0,
        "top_skills": top_skills,
        "top_industries": top_industries,
        "score_distribution": _score_histogram(all_scores),
    }

    return {
        "ranked": ranked,
        "stats": stats,
        "submission_rows": submission_rows,
    }


def _score_histogram(scores: list[float], bins: int = 10) -> list[dict]:
    """Generate score histogram data for charting."""
    if not scores:
        return []
    buckets = [0] * bins
    for s in scores:
        idx = min(int(s * bins), bins - 1)
        buckets[idx] += 1
    total = len(scores)
    return [
        {
            "label": f"{i/bins:.1f}–{(i+1)/bins:.1f}",
            "count": buckets[i],
            "pct": round(buckets[i] / total * 100, 1),
        }
        for i in range(bins)
    ]


def write_submission_csv(rows: list[dict], output_path: str | Path) -> None:
    """Write ranked rows to submission CSV."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["candidate_id", "rank", "score", "reasoning"])
        writer.writeheader()
        writer.writerows(rows)
