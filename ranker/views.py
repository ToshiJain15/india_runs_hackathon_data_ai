import json
import csv
import io
from pathlib import Path
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .models import RankingRun, RankedCandidate
from .ml.pipeline import run_pipeline, write_submission_csv
from .ml.scorer import DEFAULT_JOB, parse_job_description, strip_html


@ensure_csrf_cookie
def dashboard(request):
    """Main dashboard view."""
    runs = RankingRun.objects.all()[:10]
    latest_run = runs.first()

    # Stats
    total_runs = RankingRun.objects.count()
    latest_stats = latest_run.get_stats() if latest_run else {}

    context = {
        "runs": runs,
        "latest_run": latest_run,
        "total_runs": total_runs,
        "latest_stats": latest_stats,
        "candidates_path": str(settings.CANDIDATES_JSONL),
        "sample_path": str(settings.SAMPLE_CANDIDATES_JSON),
        "candidates_exist": Path(settings.CANDIDATES_JSONL).exists(),
        "sample_exist": Path(settings.SAMPLE_CANDIDATES_JSON).exists(),
    }
    return render(request, "ranker/dashboard.html", context)


def results_view(request, run_id=None):
    """Ranked results view."""
    if run_id:
        run = get_object_or_404(RankingRun, pk=run_id)
    else:
        run = RankingRun.objects.first()
        if not run:
            return redirect("dashboard")

    candidates = run.candidates.all().order_by("rank")
    stats = run.get_stats()

    context = {
        "run": run,
        "candidates": candidates,
        "stats": stats,
        "total": candidates.count(),
    }
    return render(request, "ranker/results.html", context)


def analytics_view(request, run_id=None):
    """Analytics dashboard view."""
    if run_id:
        run = get_object_or_404(RankingRun, pk=run_id)
    else:
        run = RankingRun.objects.first()
        if not run:
            return redirect("dashboard")

    stats = run.get_stats()
    candidates = run.candidates.all()

    # Build chart data
    component_avgs = {}
    for c in candidates:
        comps = c.get_components()
        for k, v in comps.items():
            if k != "final_score":
                component_avgs.setdefault(k, []).append(v)

    avg_components = {
        k: round(sum(v) / len(v), 3)
        for k, v in component_avgs.items()
        if v
    }

    context = {
        "run": run,
        "stats": stats,
        "candidates": candidates,
        "avg_components": avg_components,
        "score_dist_json": json.dumps(stats.get("score_distribution", [])),
        "top_skills_json": json.dumps(stats.get("top_skills", [])),
        "top_industries_json": json.dumps(stats.get("top_industries", [])),
        "avg_components_json": json.dumps(avg_components),
    }
    return render(request, "ranker/analytics.html", context)


@require_http_methods(["POST"])
def run_ranking(request):
    """API endpoint: trigger a new ranking run."""
    import json
    import os
    import tempfile
    from pathlib import Path

    # Handle standard JSON vs FormData
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        job_title = request.POST.get("job_title", "AI/ML Engineer")
        data_source = request.POST.get("data_source", "sample")
        weights_str = request.POST.get("weights")
        weights = json.loads(weights_str) if weights_str else None
        uploaded_file = request.FILES.get("file")
        max_candidates = int(request.POST.get("max_candidates", 0))
    else:
        try:
            body = json.loads(request.body) if request.body else {}
        except Exception:
            body = {}
        job_title = body.get("job_title", "AI/ML Engineer")
        data_source = "sample" if body.get("use_sample", True) else "full"
        weights = body.get("weights", None)
        uploaded_file = None
        max_candidates = int(body.get("max_candidates", 0))

    jd = dict(DEFAULT_JOB)  # copy to avoid mutating the module-level default
    
    # If user pasted a raw JD, parse it dynamically
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        jd_text = request.POST.get("jd_text", "").strip()
    else:
        jd_text = body.get("jd_text", "").strip() if 'body' in locals() else ""
    
    if jd_text and len(jd_text) > 50:
        jd = parse_job_description(jd_text)
    elif job_title:
        jd["title"] = job_title

    # Determine candidates path based on data source
    if data_source == "sample":
        candidates_path = settings.SAMPLE_CANDIDATES_JSON
    elif data_source == "upload" and uploaded_file:
        suffix = Path(uploaded_file.name).suffix.lower()
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)
                
        if suffix == ".pdf":
            try:
                from .ml.extraction import RobustPDFExtractor
                import json
                
                extractor = RobustPDFExtractor(jd=jd)
                mock_cand, text = extractor.extract(tmp_path)
                
                # Write text to a file safely to avoid Windows console charmap encoding exceptions
                debug_txt_path = settings.BASE_DIR.parent / "extracted_pdf_text.txt"
                with open(debug_txt_path, "w", encoding="utf-8", errors="replace") as df:
                    df.write(text)
                
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(mock_cand, f)
            except Exception as e:
                import traceback
                traceback.print_exc()
                return JsonResponse({"error": f"Failed to parse PDF: {str(e)}"}, status=400)
                
        candidates_path = tmp_path
    else:
        candidates_path = settings.CANDIDATES_JSONL

    # Determine if it's a JSON array (use_sample=True) or JSONL (use_sample=False)
    if data_source == "sample":
        use_sample_flag = True
    elif data_source == "upload" and uploaded_file:
        suffix = Path(uploaded_file.name).suffix.lower()
        use_sample_flag = suffix in [".json", ".pdf", ".txt"]
    else:
        use_sample_flag = False

    tmp_path_to_clean = None
    try:
        result = run_pipeline(
            candidates_path=candidates_path,
            job=jd,
            weights=weights,
            max_candidates=max_candidates,
            top_n=100,
            use_sample=use_sample_flag,
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    finally:
        # Always clean up temp uploaded files to prevent disk leak
        if data_source == "upload" and 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    if "error" in result:
        return JsonResponse(result, status=400)

    stats = result["stats"]
    ranked = result["ranked"]

    # Save run to DB
    run = RankingRun(
        job_title=job_title,
        total_candidates=stats["total_candidates"],
        duration_sec=stats["duration_sec"],
        avg_score=stats["avg_score"],
        max_score=stats["max_score"],
        status="completed",
    )
    run.set_stats(stats)
    run.save()

    # Save CSV to media
    csv_path = Path(settings.MEDIA_ROOT) / "submissions" / f"submission_{run.pk}.csv"
    write_submission_csv(result["submission_rows"], csv_path)
    run.submission_csv.name = f"submissions/submission_{run.pk}.csv"
    run.save()

    # Save top-100 candidates
    for item in ranked:
        RankedCandidate.objects.create(
            run=run,
            rank=item["rank"],
            candidate_id=item["candidate_id"],
            score=item["score"],
            raw_score=item.get("raw_score", item["score"]),
            reasoning=item["reasoning"],
            profile_json=json.dumps(item.get("profile", {})),
            components_json=json.dumps(item.get("components", {})),
            signals_json=json.dumps(item.get("signals", {})),
        )

    return JsonResponse({
        "success": True,
        "run_id": run.pk,
        "total_candidates": stats["total_candidates"],
        "duration_sec": stats["duration_sec"],
        "top_candidate": ranked[0]["candidate_id"] if ranked else None,
        "redirect_url": f"/results/{run.pk}/",
    })


def download_submission(request, run_id):
    """Download submission CSV for a run."""
    run = get_object_or_404(RankingRun, pk=run_id)
    candidates = run.candidates.all().order_by("rank")

    # Generate CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["candidate_id", "rank", "score", "reasoning"])
    for c in candidates:
        writer.writerow([c.candidate_id, c.rank, c.score, strip_html(c.reasoning)])

    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="submission_run{run_id}.csv"'
    return response


def candidate_detail_api(request, candidate_id):
    """API: get candidate detail."""
    run = RankingRun.objects.first()
    if not run:
        return JsonResponse({"error": "No runs yet"}, status=404)

    try:
        cand = RankedCandidate.objects.filter(candidate_id=candidate_id).latest("run__created_at")
    except RankedCandidate.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    return JsonResponse({
        "candidate_id": cand.candidate_id,
        "rank": cand.rank,
        "score": cand.score,
        "reasoning": cand.reasoning,
        "profile": cand.get_profile(),
        "components": cand.get_components(),
        "signals": cand.get_signals(),
    })


def api_stats(request):
    """API: get stats for latest run."""
    run = RankingRun.objects.first()
    if not run:
        return JsonResponse({"runs": 0})
    return JsonResponse({
        "run_id": run.pk,
        "stats": run.get_stats(),
        "created_at": run.created_at.isoformat(),
    })
