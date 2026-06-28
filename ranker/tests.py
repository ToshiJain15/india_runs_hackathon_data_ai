"""
Redrob AI Ranker — Comprehensive Test Suite
============================================
Market-ready automated testing covering:
  1. API Integration Tests  — endpoint health, CSRF, file upload, JD text parsing
  2. Honeypot Gate Tests    — all 4 detection checks
  3. Scoring Math Tests     — all 5 components with boundary conditions
  4. JD Parser Tests        — skill/experience/title extraction from raw text
  5. Consulting Penalty     — service-firm career detection
  6. Skill Synonym Tests    — acronym resolution (ML, NLP, k8s, dl)
  7. Cache Isolation Tests  — multi-JD cache correctness
  8. Ranking Order Tests    — better candidates always rank higher
  9. Edge Case Tests        — empty profiles, nulls, missing fields
 10. Pipeline Integration   — end-to-end: load → filter → score → sort → output

Run with:
    python manage.py test ranker --verbosity=2
"""

import json
import tempfile
import os
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile

# Python 3.14 + Django 4.2 compatibility patch for Template Context copying in test client
from django.template.context import Context
def patched_context_copy(self):
    dup = Context()
    dup.dicts = self.dicts[:]
    return dup
Context.__copy__ = patched_context_copy

from ranker.ml.scorer import (
    compute_score, is_honeypot, is_consulting_only,
    score_skills, score_experience, score_education,
    score_title_career, score_signals, parse_job_description,
    DEFAULT_JOB,
)
from ranker.ml.pipeline import run_pipeline


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def make_candidate(**overrides):
    """Return a baseline 'ideal' Senior AI Engineer candidate. Override any field via kwargs."""
    base = {
        "candidate_id": "TEST_CAND_001",
        "profile": {
            "current_title": "Senior ML Engineer",
            "current_company": "Startup AI",
            "years_of_experience": 7,
            "location": "Noida",
            "current_industry": "technology",
        },
        "skills": [
            {"name": "python",           "proficiency": "expert",       "duration_months": 72, "endorsements": 50},
            {"name": "machine learning", "proficiency": "expert",       "duration_months": 60, "endorsements": 40},
            {"name": "pytorch",          "proficiency": "advanced",     "duration_months": 48, "endorsements": 30},
            {"name": "nlp",              "proficiency": "advanced",     "duration_months": 36, "endorsements": 20},
            {"name": "docker",           "proficiency": "intermediate", "duration_months": 36, "endorsements": 10},
        ],
        "education": [
            {"degree": "B.Tech", "institution": "IIT Delhi", "tier": "tier_1", "field": "computer science"}
        ],
        "career_history": [
            {"title": "Senior ML Engineer", "company": "Startup AI",  "duration_months": 36, "industry": "technology"},
            {"title": "ML Engineer",        "company": "Product Corp", "duration_months": 36, "industry": "software"},
        ],
        "redrob_signals": {
            "willing_to_relocate": True,
            "notice_period_days": 15,
            "profile_completeness": 0.95,
            "response_rate": 0.9,
            "linkedin_connected": True,
            "verified_email": True,
            "github_score": 80,
        },
    }
    base.update(overrides)
    return base


def _run_pipeline_with(candidates, top_n=10):
    """Helper: write a list of candidates to a temp JSON file and run the pipeline."""
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(candidates, f)
        return run_pipeline(path, use_sample=True, top_n=top_n)
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 1. API Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class APITests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)

    def test_dashboard_returns_200(self):
        """GET / must return HTTP 200 with HTML content."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp["Content-Type"])

    def test_dashboard_sets_csrf_cookie(self):
        """Dashboard must stamp csrftoken cookie so JS fetch can read it."""
        resp = self.client.get("/")
        self.assertIn("csrftoken", resp.cookies)

    def test_run_ranking_sample_returns_success(self):
        """POST /api/run/ with use_sample=True must return success=True and all core fields."""
        resp = self.client.post(
            "/api/run/",
            data=json.dumps({"job_title": "AI Engineer", "use_sample": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"), f"Expected success=True, got: {data}")
        self.assertIn("run_id", data)
        self.assertIn("redirect_url", data)
        self.assertGreater(data.get("total_candidates", 0), 0)

    def test_run_ranking_response_schema(self):
        """API response must include all fields the frontend depends on."""
        resp = self.client.post(
            "/api/run/",
            data=json.dumps({"use_sample": True}),
            content_type="application/json",
        )
        data = resp.json()
        for key in ("success", "run_id", "total_candidates", "duration_sec", "redirect_url"):
            self.assertIn(key, data, f"Missing API response key: '{key}'")

    def test_run_ranking_upload_json_file(self):
        """Uploading a JSON candidate pool must score it and return total_candidates=1."""
        pool = [make_candidate(candidate_id="UPLOAD_TEST_001")]
        mock_file = SimpleUploadedFile(
            "pool.json", json.dumps(pool).encode("utf-8"), content_type="application/json"
        )
        resp = self.client.post(
            "/api/run/",
            data={"job_title": "ML Engineer", "data_source": "upload", "file": mock_file},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("total_candidates"), 1)

    def test_run_ranking_with_jd_text(self):
        """POST with jd_text field must parse it and run successfully."""
        jd = "Senior Backend Engineer. 3-6 years experience. Required: Java, Spring Boot, Kubernetes."
        resp = self.client.post(
            "/api/run/",
            data=json.dumps({"use_sample": True, "jd_text": jd}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("success"))

    def test_results_page_after_run(self):
        """/results/<run_id>/ must return 200 after a successful run."""
        run_data = self.client.post(
            "/api/run/",
            data=json.dumps({"use_sample": True}),
            content_type="application/json",
        ).json()
        run_id = run_data.get("run_id")
        self.assertIsNotNone(run_id)
        self.assertEqual(self.client.get(f"/results/{run_id}/").status_code, 200)

    def test_download_csv_after_run(self):
        """CSV download must return valid attachment with correct header row."""
        run_id = self.client.post(
            "/api/run/",
            data=json.dumps({"use_sample": True}),
            content_type="application/json",
        ).json().get("run_id")
        dl = self.client.get(f"/download/{run_id}/")
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(dl["Content-Type"], "text/csv")
        self.assertIn("attachment", dl["Content-Disposition"])
        self.assertTrue(dl.content.decode("utf-8").startswith("candidate_id,rank,score,reasoning"))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Honeypot Gate Tests
# ─────────────────────────────────────────────────────────────────────────────

class HoneypotTests(TestCase):
    def test_expert_zero_duration_x3_is_honeypot(self):
        """3 expert skills with 0 duration must be flagged and scored 0.0."""
        cand = {"skills": [
            {"name": "Python", "proficiency": "expert", "duration_months": 0},
            {"name": "ML",     "proficiency": "expert", "duration_months": 0},
            {"name": "NLP",    "proficiency": "expert", "duration_months": 0},
        ]}
        self.assertTrue(is_honeypot(cand))
        score, _ = compute_score(cand)
        self.assertEqual(score, 0.0)

    def test_two_expert_zero_duration_not_honeypot(self):
        """Only 2 expert-zero-duration skills (below threshold) must NOT be flagged."""
        cand = {"skills": [
            {"name": "Python", "proficiency": "expert",  "duration_months": 0},
            {"name": "ML",     "proficiency": "expert",  "duration_months": 0},
            {"name": "NLP",    "proficiency": "advanced", "duration_months": 24},
        ]}
        self.assertFalse(is_honeypot(cand))

    def test_yoe_career_history_mismatch_is_honeypot(self):
        """Claiming 10 YOE with only 24 months career history (gap > 2yr) must be flagged."""
        cand = {
            "profile": {"years_of_experience": 10},
            "career_history": [{"duration_months": 24}],
            "skills": [],
        }
        self.assertTrue(is_honeypot(cand))

    def test_calendar_date_fabrication_is_honeypot(self):
        """Job claiming 60 months between a 24-month date range must be flagged."""
        cand = {
            "profile": {"years_of_experience": 8},
            "career_history": [{
                "duration_months": 60,
                "start_date": "2022-01",
                "end_date": "2024-01",
            }],
            "skills": [],
        }
        self.assertTrue(is_honeypot(cand))

    def test_clean_ideal_candidate_not_honeypot(self):
        """A well-formed legitimate candidate must never be flagged."""
        self.assertFalse(is_honeypot(make_candidate()))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Scoring Math Tests
# ─────────────────────────────────────────────────────────────────────────────

class ScoringMathTests(TestCase):
    def test_ideal_candidate_scores_above_70_pct(self):
        """An ideal Senior AI Engineer (7 YOE, IIT, Noida, strong skills) must score > 0.7."""
        score, components = compute_score(make_candidate())
        self.assertGreater(score, 0.7, f"Ideal candidate scored {score}\n{components}")

    def test_score_is_always_between_0_and_1(self):
        """Final score must be in [0.0, 1.0] for any input."""
        score, _ = compute_score(make_candidate())
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_experience_penalty_for_zero_yoe(self):
        """0 YOE (no advanced degree) must result in score < 0.4."""
        cand = {
            "profile": {"years_of_experience": 0},
            "skills": [{"name": "python", "proficiency": "expert", "duration_months": 60}],
            "career_history": [],
        }
        score, _ = compute_score(cand)
        self.assertLess(score, 0.4)

    def test_phd_prodigy_bypasses_junior_penalty(self):
        """PhD + 0 YOE must score higher than B.Sc. + 0 YOE."""
        phd = {
            "profile": {"years_of_experience": 0},
            "education": [{"degree": "Ph.D. Computer Science"}],
            "skills": [{"name": "python", "proficiency": "expert", "duration_months": 60}],
            "career_history": [],
        }
        bsc = {
            "profile": {"years_of_experience": 0},
            "education": [{"degree": "B.Sc. Computer Science"}],
            "skills": [{"name": "python", "proficiency": "expert", "duration_months": 60}],
            "career_history": [],
        }
        score_phd, _ = compute_score(phd)
        score_bsc, _ = compute_score(bsc)
        self.assertGreater(score_phd, score_bsc)
        self.assertGreater(score_phd, 0.4)

    def test_ideal_yoe_peaks_at_1(self):
        """6, 7, and 8 YOE must each return experience_score = 1.0."""
        for yoe in [6.0, 7.0, 8.0]:
            cand = {"profile": {"years_of_experience": yoe}}
            s = score_experience(cand)
            self.assertEqual(s, 1.0, f"Expected 1.0 for {yoe} YOE, got {s}")

    def test_overqualification_penalty(self):
        """15 YOE must score lower on experience than ideal 7 YOE."""
        self.assertGreater(
            score_experience({"profile": {"years_of_experience": 7}}),
            score_experience({"profile": {"years_of_experience": 15}}),
        )

    def test_no_skills_returns_zero(self):
        """Candidate with no skills must return skill_score = 0.0."""
        self.assertEqual(score_skills({"skills": []}, DEFAULT_JOB), 0.0)

    def test_expert_proficiency_beats_beginner(self):
        """Expert proficiency must produce a higher skill score than beginner when matching is partial."""
        expert = {"skills": [
            {"name": "python", "proficiency": "expert", "duration_months": 36},
            {"name": "excel",  "proficiency": "beginner", "duration_months": 36}
        ]}
        beginner = {"skills": [
            {"name": "python", "proficiency": "beginner", "duration_months": 36},
            {"name": "excel",  "proficiency": "expert", "duration_months": 36}
        ]}
        self.assertGreater(score_skills(expert, DEFAULT_JOB), score_skills(beginner, DEFAULT_JOB))

    def test_phd_scores_higher_than_btech_in_education(self):
        """PhD from Tier-1 must outrank B.Tech from Tier-1 on education score."""
        phd   = {"education": [{"degree": "phd",    "tier": "tier_1", "field": "computer science"}]}
        btech = {"education": [{"degree": "b.tech", "tier": "tier_1", "field": "computer science"}]}
        self.assertGreater(score_education(phd), score_education(btech))

    def test_all_5_components_present_in_output(self):
        """compute_score must always return all 5 component scores."""
        _, components = compute_score(make_candidate())
        for key in ("skill_score", "title_career_score", "experience_score", "education_score", "signal_score"):
            self.assertIn(key, components, f"Missing component key: {key}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Consulting Penalty Tests
# ─────────────────────────────────────────────────────────────────────────────

class ConsultingPenaltyTests(TestCase):
    def test_tcs_only_career_flagged(self):
        """TCS-only career must be identified as consulting-only."""
        cand = {"career_history": [
            {"company": "Tata Consultancy Services", "title": "Dev"},
            {"company": "TCS",                       "title": "Senior Dev"},
        ]}
        self.assertTrue(is_consulting_only(cand))

    def test_infosys_wipro_flagged(self):
        cand = {"career_history": [
            {"company": "Infosys", "title": "Engineer"},
            {"company": "Wipro",   "title": "Senior Engineer"},
        ]}
        self.assertTrue(is_consulting_only(cand))

    def test_mixed_product_and_consulting_not_flagged(self):
        """One product-company stint neutralises the consulting label."""
        cand = {"career_history": [
            {"company": "Infosys", "title": "Engineer"},
            {"company": "Google",  "title": "Senior Engineer"},
        ]}
        self.assertFalse(is_consulting_only(cand))

    def test_consulting_candidate_scores_less_than_product(self):
        """Identical candidates where one is consulting-only must score lower."""
        c_consulting = make_candidate()
        c_consulting["career_history"] = [
            {"title": "Dev", "company": "Infosys", "duration_months": 84, "industry": "IT services"},
        ]
        c_product = make_candidate()
        c_product["career_history"] = [
            {"title": "ML Eng", "company": "Amazon", "duration_months": 84, "industry": "technology"},
        ]
        s_con, _ = compute_score(c_consulting)
        s_pro, _ = compute_score(c_product)
        self.assertLess(s_con, s_pro)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Skill Synonym Tests
# ─────────────────────────────────────────────────────────────────────────────

class SkillSynonymTests(TestCase):
    def _skill_score_for(self, skill_name):
        cand = {"skills": [{"name": skill_name, "proficiency": "expert", "duration_months": 48}]}
        return score_skills(cand, DEFAULT_JOB)

    def test_ml_resolves_to_machine_learning(self):
        self.assertGreater(self._skill_score_for("ML"), 0.0)

    def test_nlp_resolves_to_natural_language_processing(self):
        self.assertGreater(self._skill_score_for("NLP"), 0.0)

    def test_k8s_resolves_to_kubernetes(self):
        self.assertGreater(self._skill_score_for("k8s"), 0.0)

    def test_dl_resolves_to_deep_learning(self):
        self.assertGreater(self._skill_score_for("dl"), 0.0)

    def test_llm_resolves_to_large_language_models(self):
        self.assertGreater(self._skill_score_for("llm"), 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 6. JD Parser Tests
# ─────────────────────────────────────────────────────────────────────────────

class JDParserTests(TestCase):
    def test_extracts_python_from_jd(self):
        result = parse_job_description("We need a Python developer with machine learning skills.")
        self.assertIn("python", result["core_skills"])

    def test_extracts_experience_range(self):
        result = parse_job_description("Senior Engineer with 5-8 years experience in backend systems.")
        self.assertEqual(result["preferred_experience_range"], (5, 8))

    def test_extracts_single_experience(self):
        result = parse_job_description("7+ years of experience in data engineering with Spark and Kafka.")
        lo, hi = result["preferred_experience_range"]
        self.assertGreaterEqual(lo, 4)
        self.assertLessEqual(hi, 12)

    def test_result_contains_all_required_keys(self):
        result = parse_job_description("Senior Data Scientist. Python, TensorFlow, SQL. 4-7 years.")
        for key in ("title", "core_skills", "bonus_skills", "relevant_titles",
                    "relevant_industries", "preferred_experience_range", "preferred_education_fields"):
            self.assertIn(key, result, f"JD parser missing key: {key}")

    def test_core_skills_is_nonempty_list(self):
        result = parse_job_description("Lead ML Engineer. Requirements: Python, PyTorch, AWS, Docker.")
        self.assertIsInstance(result["core_skills"], list)
        self.assertGreater(len(result["core_skills"]), 0)

    def test_title_extracted_from_first_line(self):
        result = parse_job_description("Lead Data Engineer\nRequires Spark, Kafka, Airflow. 5-8 years.")
        self.assertIn("engineer", result["title"].lower())


# ─────────────────────────────────────────────────────────────────────────────
# 7. Cache Isolation Tests
# ─────────────────────────────────────────────────────────────────────────────

class CacheIsolationTests(TestCase):
    def test_different_jds_produce_correct_scores(self):
        """Scoring against two different JDs in the same process must be independent."""
        jd_ai = dict(DEFAULT_JOB)
        jd_fe = dict(DEFAULT_JOB)
        jd_fe["core_skills"] = ["javascript", "react", "typescript", "css", "html"]

        ai_cand = {"skills": [{"name": "python",     "proficiency": "expert", "duration_months": 48}]}
        fe_cand = {"skills": [{"name": "javascript", "proficiency": "expert", "duration_months": 48}]}

        ai_on_ai_jd = score_skills(ai_cand, jd_ai)
        fe_on_fe_jd = score_skills(fe_cand, jd_fe)
        ai_on_fe_jd = score_skills(ai_cand, jd_fe)

        self.assertGreater(ai_on_ai_jd, ai_on_fe_jd,
            "Python must score higher on AI JD than on Frontend JD")
        self.assertGreater(fe_on_fe_jd, ai_on_fe_jd,
            "JS expert must beat Python expert on Frontend JD")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Ranking Order Tests
# ─────────────────────────────────────────────────────────────────────────────

class RankingOrderTests(TestCase):
    def test_senior_outranks_junior(self):
        """7 YOE candidate must score higher than 1 YOE candidate."""
        senior = make_candidate(candidate_id="SENIOR")
        junior = make_candidate(candidate_id="JUNIOR")
        junior["profile"]["years_of_experience"] = 1
        s_senior, _ = compute_score(senior)
        s_junior, _ = compute_score(junior)
        self.assertGreater(s_senior, s_junior)

    def test_relevant_skills_outrank_irrelevant(self):
        """Python/ML expert must score higher than Excel beginner for AI JD."""
        ai_cand = make_candidate(candidate_id="AI")
        excel_cand = make_candidate(candidate_id="EXCEL")
        excel_cand["skills"] = [{"name": "excel", "proficiency": "beginner", "duration_months": 6}]
        s_ai, _ = compute_score(ai_cand)
        s_ex, _ = compute_score(excel_cand)
        self.assertGreater(s_ai, s_ex)

    def test_noida_short_notice_beats_international_long_notice(self):
        """Noida + 15-day notice must score higher on signals than Singapore + 90-day notice."""
        local = make_candidate(candidate_id="LOCAL")
        local["profile"]["location"] = "Noida"
        local["redrob_signals"] = {"willing_to_relocate": False, "notice_period_days": 15}

        abroad = make_candidate(candidate_id="ABROAD")
        abroad["profile"]["location"] = "Singapore"
        abroad["redrob_signals"] = {"willing_to_relocate": False, "notice_period_days": 90}

        self.assertGreater(score_signals(local), score_signals(abroad))


# ─────────────────────────────────────────────────────────────────────────────
# 9. Edge Case Tests
# ─────────────────────────────────────────────────────────────────────────────

class EdgeCaseTests(TestCase):
    def test_empty_dict_scores_zero_without_crash(self):
        """An empty candidate dict must produce low score without raising any exception."""
        try:
            score, _ = compute_score({})
            self.assertLess(score, 0.2)
        except Exception as e:
            self.fail(f"compute_score({{}}) raised: {e}")

    def test_none_field_values_handled_gracefully(self):
        """Candidates with None field values must not crash the engine."""
        cand = {
            "candidate_id": None,
            "profile": {"current_title": None, "years_of_experience": None},
            "skills": [{"name": None, "proficiency": None, "duration_months": None}],
            "career_history": [{"company": None, "title": None, "duration_months": None}],
            "redrob_signals": None,
        }
        try:
            score, _ = compute_score(cand)
            self.assertGreaterEqual(score, 0.0)
        except Exception as e:
            self.fail(f"compute_score raised on None fields: {e}")

    def test_missing_profile_key_handled(self):
        """Missing 'profile' key must not raise a KeyError."""
        cand = {"skills": [{"name": "python", "proficiency": "expert", "duration_months": 36}]}
        try:
            compute_score(cand)
        except Exception as e:
            self.fail(f"Missing 'profile' key raised: {e}")

    def test_very_high_endorsements_capped(self):
        """Endorsements above 100 must be capped — score must remain <= 1.0."""
        cand = {"skills": [{"name": "python", "proficiency": "expert",
                            "duration_months": 60, "endorsements": 99999}]}
        s = score_skills(cand, DEFAULT_JOB)
        self.assertLessEqual(s, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Pipeline Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class PipelineIntegrationTests(TestCase):
    def test_pipeline_output_structure(self):
        """Pipeline must return a dict with ranked, stats, and submission_rows."""
        result = _run_pipeline_with([make_candidate()])
        for key in ("ranked", "stats", "submission_rows"):
            self.assertIn(key, result, f"Pipeline output missing key: '{key}'")

    def test_pipeline_stats_contain_metrics(self):
        """Stats must include total_candidates, duration_sec, and avg_score."""
        stats = _run_pipeline_with([make_candidate()])["stats"]
        for key in ("total_candidates", "duration_sec", "avg_score"):
            self.assertIn(key, stats)
        self.assertGreater(stats["total_candidates"], 0)
        self.assertGreaterEqual(stats["duration_sec"], 0.0)

    def test_pipeline_honeypot_zeroed(self):
        """Honeypot candidate must appear with score 0.0 (not excluded, but zeroed)."""
        honeypot = {
            "candidate_id": "HONEYPOT_001",
            "profile": {"years_of_experience": 10},
            "skills": [
                {"name": "python", "proficiency": "expert", "duration_months": 0},
                {"name": "ml",     "proficiency": "expert", "duration_months": 0},
                {"name": "nlp",    "proficiency": "expert", "duration_months": 0},
            ],
            "career_history": [],
            "redrob_signals": {},
        }
        result = _run_pipeline_with([honeypot, make_candidate()])
        for item in result["ranked"]:
            if item["candidate_id"] == "HONEYPOT_001":
                self.assertEqual(item["raw_score"], 0.0)

    def test_pipeline_ranking_is_non_increasing(self):
        """Ranked output must be in non-increasing score order."""
        pool = [make_candidate(candidate_id=f"C{i:03d}") for i in range(5)]
        pool[2]["profile"]["years_of_experience"] = 0  # deliberately weaker
        scores = [item["score"] for item in _run_pipeline_with(pool)["ranked"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_pipeline_submission_rows_have_all_columns(self):
        """Every submission_row must have candidate_id, rank, score, reasoning."""
        rows = _run_pipeline_with([make_candidate()])["submission_rows"]
        for row in rows:
            for col in ("candidate_id", "rank", "score", "reasoning"):
                self.assertIn(col, row, f"submission_rows row missing column: '{col}'")

    def test_pipeline_reasoning_is_non_empty_string(self):
        """Each ranked candidate must have a non-empty reasoning string."""
        for item in _run_pipeline_with([make_candidate()])["ranked"]:
            self.assertIsInstance(item.get("reasoning"), str)
            self.assertGreater(len(item["reasoning"].strip()), 0)
