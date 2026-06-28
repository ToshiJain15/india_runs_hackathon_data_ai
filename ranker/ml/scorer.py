"""
Redrob AI Candidate Scoring Engine
===================================
Multi-factor scoring pipeline for intelligent candidate discovery and ranking.

Scoring components:
  1. Skill Match Score    (40%) — AI/ML core skills with proficiency + endorsement trust
  2. Title + Career Score (25%) — Semantic title relevance + career progression
  3. Experience Score     (15%) — Years of experience with optimal range bonus
  4. Education Score      (10%) — Institution tier + field relevance + degree level
  5. Signal Modifier      (10%) — Redrob platform behavioral signals

Final score ∈ [0.0, 1.0], non-increasing by rank.
"""

import math
import time
from datetime import datetime
from typing import Optional

# ─────────────────────────────────────────────
# Job Description Context
# ─────────────────────────────────────────────
DEFAULT_JOB = {
    "title": "Senior AI Engineer",
    "core_skills": [
        "python", "machine learning", "deep learning", "tensorflow", "pytorch",
        "scikit-learn", "nlp", "natural language processing", "computer vision",
        "data science", "sql", "pandas", "numpy", "statistics", "algorithms",
        "neural networks", "transformers", "llm", "large language models",
        "generative ai", "mlops", "docker", "kubernetes", "aws", "gcp", "azure",
        "spark", "hadoop", "feature engineering", "model deployment", "api",
        "fastapi", "flask", "git", "agile", "data engineering", "etl", "dbt",
        "airflow", "kafka", "redis", "mongodb", "postgresql", "r",
    ],
    "bonus_skills": [
        "reinforcement learning", "gans", "bert", "gpt", "langchain",
        "hugging face", "vector database", "pinecone", "weaviate", "qdrant",
        "ray", "dask", "xgboost", "lightgbm", "catboost", "automl",
        "responsible ai", "explainability", "shap", "lime",
    ],
    "relevant_titles": [
        "senior ai engineer", "senior machine learning engineer", "senior ml engineer",
        "ai engineer", "machine learning engineer", "ml engineer",
        "applied scientist", "ai researcher", "research scientist",
        "data scientist", "senior data scientist",
        "data engineer", "mlops engineer", "software engineer",
    ],
    "relevant_industries": [
        "technology", "software", "fintech", "edtech", "healthtech",
        "artificial intelligence", "data", "saas", "cloud",
    ],
    "preferred_experience_range": (5, 9),  # JD: 5-9 years, ideal 6-8
    "preferred_education_fields": [
        "computer science", "data science", "statistics", "mathematics",
        "electrical engineering", "information technology", "engineering",
    ],
}

PROFICIENCY_WEIGHTS = {
    "beginner": 0.25,
    "intermediate": 0.55,
    "advanced": 0.80,
    "expert": 1.00,
}

TIER_WEIGHTS = {
    "tier_1": 1.00,
    "tier_2": 0.80,
    "tier_3": 0.60,
    "tier_4": 0.40,
    "unknown": 0.50,
}

DEGREE_WEIGHTS = {
    "phd": 1.00,
    "m.tech": 0.90, "m.e.": 0.90, "m.s.": 0.90, "mtech": 0.90,
    "mba": 0.80, "m.b.a": 0.80,
    "b.tech": 0.75, "btech": 0.75, "b.e.": 0.75,
    "msc": 0.85, "m.sc.": 0.85, "b.sc.": 0.65, "bsc": 0.65,
    "bachelor": 0.65, "b.a.": 0.55, "ba": 0.55,
    "diploma": 0.40,
}

CONSULTING_COMPANIES = [
    "tcs", "tata consultancy services", "infosys", "wipro", "accenture",
    "cognizant", "capgemini", "tech mahindra", "hcl", "mindtree", "mphasis",
    "l&t", "lnt", "larsen & toubro"
]

NLP_BOOST_KEYWORDS = [
    "vector search", "vector database", "embeddings", "dense retrieval",
    "hybrid search", "pinecone", "weaviate", "qdrant", "milvus",
    "opensearch", "elasticsearch", "faiss", "rag", "retrieval-augmented generation",
    "sentence-transformers", "bge", "cohere", "embedding"
]

PREFERRED_LOCATIONS = [
    "pune", "noida", "delhi", "ncr", "hyderabad", "mumbai", "gurgaon", 
    "ghaziabad", "faridabad", "bangalore", "bengaluru"
]

SYNONYMS_MAP = {
    "ml": "machine learning",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "llm": "large language models",
    "genai": "generative ai",
    "k8s": "kubernetes",
    "dl": "deep learning",
    "rl": "reinforcement learning",
}

# Known skill tokens for JD parsing
_ALL_KNOWN_SKILLS = set(DEFAULT_JOB["core_skills"] + DEFAULT_JOB["bonus_skills"] + [
    "java", "c++", "scala", "go", "rust", "javascript", "typescript", "node.js",
    "react", "vue", "angular", "django", "spring", "graphql", "rest", "grpc",
    "terraform", "ansible", "linux", "bash", "hadoop", "spark", "flink",
    "snowflake", "databricks", "powerbi", "tableau", "excel",
])

_TITLE_PATTERNS = [
    "senior", "lead", "principal", "staff", "head of", "director", "vp of",
    "engineer", "scientist", "analyst", "architect", "developer", "manager",
    "ml engineer", "ai engineer", "data scientist", "data engineer",
    "mlops", "devops", "backend", "frontend", "fullstack",
]


_cached_config = None
_cached_config_time = 0

def get_db_config():
    global _cached_config, _cached_config_time
    if time.time() - _cached_config_time < 60 and _cached_config:
        return _cached_config
        
    try:
        from .models import SystemConfig, LocationTier, DegreeWeight, TierWeight
        conf = SystemConfig.objects.first()
        if not conf:
            conf = SystemConfig()
            
        weights = {
            "skills": conf.skills_weight,
            "title_career": conf.title_career_weight,
            "experience": conf.experience_weight,
            "education": conf.education_weight,
            "signals": conf.signals_weight,
        }
        
        tw = {t.tier_key: t.weight for t in TierWeight.objects.all()}
        tier_weights = tw if tw else TIER_WEIGHTS
            
        dw = {d.degree_key: d.weight for d in DegreeWeight.objects.all()}
        degree_weights = dw if dw else DEGREE_WEIGHTS
            
        location_tiers = {l.city_name.lower(): l.tier for l in LocationTier.objects.all()}
        
        _cached_config = (weights, tier_weights, degree_weights, location_tiers)
        _cached_config_time = time.time()
        return _cached_config
    except Exception:
        return None, TIER_WEIGHTS, DEGREE_WEIGHTS, {}


def parse_job_description(jd_text: str) -> dict:
    """
    Parse a raw Job Description text block and extract a structured JD dict
    compatible with the scoring engine. Enables true multi-tenant, dynamic JD support.

    Args:
        jd_text: Raw JD text string (copied from a job posting).

    Returns:
        A dict with keys: title, core_skills, bonus_skills, relevant_titles,
        relevant_industries, preferred_experience_range, preferred_education_fields.
    """
    text = jd_text.lower()
    words = set(text.split())

    # Extract skills by matching known tokens against jd text
    core_found = []
    bonus_found = []
    for skill in DEFAULT_JOB["core_skills"]:
        if skill in text:
            core_found.append(skill)
    for skill in DEFAULT_JOB["bonus_skills"]:
        if skill in text:
            bonus_found.append(skill)

    # Supplement with any extra known skills found in text
    for skill in _ALL_KNOWN_SKILLS:
        if skill in text and skill not in core_found and skill not in bonus_found:
            core_found.append(skill)

    # Extract experience requirement
    exp_range = (3, 10)  # default
    import re
    exp_matches = re.findall(r'(\d+)\s*(?:\-|to)\s*(\d+)\s*years?', text)
    if exp_matches:
        lo, hi = int(exp_matches[0][0]), int(exp_matches[0][1])
        exp_range = (lo, hi)
    else:
        single_exp = re.findall(r'(\d+)\+?\s*years?\s*(?:of\s*)?experience', text)
        if single_exp:
            yoe = int(single_exp[0])
            exp_range = (max(0, yoe - 2), yoe + 3)

    # Extract title (look for Senior/Lead/Principal near role keyword in first 3 lines)
    first_lines = jd_text.strip().split('\n')[:5]
    extracted_title = "Senior AI Engineer"
    for line in first_lines:
        ll = line.lower().strip()
        if any(t in ll for t in ["engineer", "scientist", "analyst", "developer", "architect", "manager"]):
            extracted_title = line.strip()[:80]
            break

    # Relevant titles heuristic
    relevant_titles = list(DEFAULT_JOB["relevant_titles"])
    if extracted_title.lower() not in relevant_titles:
        relevant_titles.insert(0, extracted_title.lower())

    return {
        "title": extracted_title,
        "core_skills": core_found if core_found else DEFAULT_JOB["core_skills"],
        "bonus_skills": bonus_found if bonus_found else DEFAULT_JOB["bonus_skills"],
        "relevant_titles": relevant_titles,
        "relevant_industries": DEFAULT_JOB["relevant_industries"],
        "preferred_experience_range": exp_range,
        "preferred_education_fields": DEFAULT_JOB["preferred_education_fields"],
    }


def is_honeypot(candidate: dict) -> bool:
    """
    Programmatically flags candidate profiles containing impossible data (honeypots).
    Identifies 4 physical profile contradictions:
      1. Expert skills with 0 months of duration (>= 3 occurrences).
      2. Profile years of experience is significantly larger than cumulative career history.
      3. Any single career job duration is longer than the listed total years of experience.
      4. Single job listed duration exceeds calendar months between start and end (using June 10, 2026 reference).
    """
    profile = candidate.get("profile", {}) or {}
    yoe = float(profile.get("years_of_experience") or 0)
    career = candidate.get("career_history", []) or []
    skills = candidate.get("skills", []) or []

    # 1. Expert Zero Duration: >= 3 expert skills with 0 months duration
    expert_zero = [s for s in skills if s.get("proficiency") == "expert" and s.get("duration_months", 0) == 0]
    if len(expert_zero) >= 3:
        return True

    # 2. YOE mismatch: Profile YOE exceeds the sum of career history job durations by 2+ years (for experience > 2 years)
    total_months = sum(float(job.get("duration_months") or 0) for job in career)
    if yoe > (total_months / 12) + 2.0 and yoe > 2.0:
        return True

    # 3. Job longer than YOE: Any single job listed duration is longer than the profile total YOE
    for job in career:
        listed_dur_years = float(job.get("duration_months") or 0) / 12
        if listed_dur_years > yoe + 0.5:
            return True

        # 4. Job calendar mismatch: Job duration is physically longer than calendar months (3 months buffer)
        sd_str = job.get("start_date") or ""
        ed_str = job.get("end_date") or ""
        listed_dur_months = float(job.get("duration_months") or 0)
        if sd_str and len(sd_str) >= 7:
            try:
                sd_yr, sd_mo = int(sd_str[:4]), int(sd_str[5:7])
                if ed_str and len(ed_str) >= 7:
                    ed_yr, ed_mo = int(ed_str[:4]), int(ed_str[5:7])
                else:
                    ed_yr, ed_mo = 2026, 6
                
                cal_months = (ed_yr - sd_yr) * 12 + (ed_mo - sd_mo)
                if listed_dur_months > cal_months + 3:
                    return True
            except:
                pass

    return False


def is_consulting_only(candidate: dict) -> bool:
    """Check if all companies in the candidate's career history are service firms."""
    career = candidate.get("career_history", []) or []
    if not career:
        curr_co = (candidate.get("profile", {}) or {}).get("current_company") or ""
        curr_co = curr_co.lower()
        if not curr_co:
            return False
        return any(c in curr_co for c in CONSULTING_COMPANIES)

    for job in career:
        co = (job.get("company") or "").lower()
        if not any(c in co for c in CONSULTING_COMPANIES):
            return False  # worked at at least one non-service company
    return True


_fuzzy_match_cache = {}
def _fuzzy_match(a: str, b: str) -> float:
    """Simple substring / token overlap for skill matching with memoization cache."""
    key = (a, b)
    if key in _fuzzy_match_cache:
        return _fuzzy_match_cache[key]
    
    a_clean, b_clean = a.lower().strip(), b.lower().strip()
    if a_clean == b_clean:
        res = 1.0
    elif a_clean in b_clean or b_clean in a_clean:
        res = 0.85
    else:
        ta, tb = set(a_clean.split()), set(b_clean.split())
        if ta and tb:
            overlap = len(ta & tb) / len(ta | tb)
            if overlap > 0.5:
                res = overlap
            else:
                res = 0.0
        else:
            res = 0.0
            
    _fuzzy_match_cache[key] = res
    return res


_match_skill_cache = {}
def _match_skill(skill_name: str, job_skills: list[str]) -> float:
    """Return best match score of a skill against job skill list, using a cache and synonym map.
    Cache is keyed by (skill_name, job_skills_tuple) to avoid cross-JD cache corruption."""
    skill_name_clean = skill_name.lower().strip()
    skill_name_clean = SYNONYMS_MAP.get(skill_name_clean, skill_name_clean)
    
    job_skills_tuple = tuple(job_skills)  # hashable key
    cache_key = (skill_name_clean, job_skills_tuple)
    
    if cache_key in _match_skill_cache:
        return _match_skill_cache[cache_key]
        
    job_skills_set = set(js.lower().strip() for js in job_skills)
        
    if skill_name_clean in job_skills_set:
        _match_skill_cache[cache_key] = 1.0
        return 1.0
        
    best = 0.0
    for js in job_skills:
        score = _fuzzy_match(skill_name_clean, js)
        if score > best:
            best = score
        if best == 1.0:
            break
            
    _match_skill_cache[cache_key] = best
    return best


def score_skills(candidate: dict, job: dict = DEFAULT_JOB) -> float:
    """
    Skill match score [0, 1].
    Weights: proficiency level × endorsement trust multiplier × match quality.
    Bonus for bonus_skills and NLP/IR specific keywords.
    """
    skills = candidate.get("skills", [])
    if not skills:
        return 0.0

    core_skills = job["core_skills"]
    bonus_skills = job.get("bonus_skills", [])

    total_weight = 0.0
    matched_weight = 0.0
    bonus_score = 0.0

    # Boost for NLP / vector database experience
    nlp_skills_found = 0
    for skill in skills:
        name = (skill.get("name") or "").lower()
        if any(keyword in name for keyword in NLP_BOOST_KEYWORDS):
            nlp_skills_found += 1

    for skill in skills:
        name = skill.get("name") or ""
        proficiency = skill.get("proficiency") or "beginner"
        endorsements = min(float(skill.get("endorsements") or 0), 100)
        duration_months = float(skill.get("duration_months") or 0)

        prof_w = PROFICIENCY_WEIGHTS.get(proficiency, 0.25)
        endorse_trust = 0.5 + 0.5 * math.tanh(endorsements / 20)

        if duration_months > 0:
            dur_trust = min(1.0, 0.4 + 0.6 * math.tanh(duration_months / 18))
        else:
            dur_trust = 0.65

        skill_weight = prof_w * endorse_trust * dur_trust

        # Core match
        core_match = _match_skill(name, core_skills)
        if core_match > 0.0:
            matched_weight += skill_weight * core_match

        # Bonus match
        bonus_match = _match_skill(name, bonus_skills)
        if bonus_match > 0.5:
            bonus_score += 0.03 * bonus_match

        total_weight += skill_weight

    if total_weight == 0:
        return 0.0

    base = min(1.0, matched_weight / (total_weight * 0.45 + 1e-9))
    bonus = min(0.20, bonus_score + (0.05 * nlp_skills_found))
    return min(1.0, base + bonus * (1 - base))


def score_title_career(candidate: dict, job: dict = DEFAULT_JOB) -> float:
    """
    Title + career relevance score [0, 1].
    Checks current title, career history, and industry alignment.
    Applies a consulting firm penalty.
    """
    relevant_titles = job["relevant_titles"]
    relevant_industries = job.get("relevant_industries", [])

    profile = candidate.get("profile", {}) or {}
    current_title = (profile.get("current_title") or "").lower()
    current_industry = (profile.get("current_industry") or "").lower()

    # Current title match (most important)
    title_score = 0.0
    for rt in relevant_titles:
        m = _fuzzy_match(current_title, rt)
        if m > title_score:
            title_score = m
    title_score = min(1.0, title_score * 1.1)

    # Industry alignment
    industry_score = 0.0
    for ri in relevant_industries:
        if ri in current_industry or current_industry in ri:
            industry_score = 1.0
            break
        m = _fuzzy_match(current_industry, ri)
        if m > industry_score:
            industry_score = m

    # Career history scan
    career = candidate.get("career_history", [])
    career_title_score = 0.0
    career_industry_score = 0.0
    recent_relevance = []
    has_nlp_desc = False

    for i, job_entry in enumerate(career):
        t = (job_entry.get("title") or "").lower()
        ind = (job_entry.get("industry") or "").lower()
        desc = (job_entry.get("description") or "").lower()
        recency_w = 1.0 / (i + 1)

        # Check description for NLP/Vector search keywords
        if any(keyword in desc for keyword in NLP_BOOST_KEYWORDS):
            has_nlp_desc = True

        for rt in relevant_titles:
            m = _fuzzy_match(t, rt) * recency_w
            if m > career_title_score:
                career_title_score = m

        for ri in relevant_industries:
            if ri in ind or ind in ri:
                career_industry_score = max(career_industry_score, 0.9 * recency_w)
            else:
                m = _fuzzy_match(ind, ri) * recency_w
                if m > career_industry_score:
                    career_industry_score = m

        recent_relevance.append(_match_skill(t, relevant_titles) * recency_w)

    progression_bonus = min(0.12, sum(recent_relevance) * 0.04)
    if has_nlp_desc:
        progression_bonus += 0.05

    combined = (
        0.50 * title_score +
        0.20 * career_title_score +
        0.15 * industry_score +
        0.10 * career_industry_score +
        0.05 * progression_bonus
    )

    # IT Consulting Service Firm Penalty: apply severe 0.2x multiplier if entire career at services
    if is_consulting_only(candidate):
        combined *= 0.2

    return min(1.0, combined)


def score_experience(candidate: dict, job: dict = DEFAULT_JOB) -> float:
    """
    Experience score [0, 1].
    Peaks at 6-8 years (ideal). Outside 5-9 is penalized.
    Under-experienced (< 3) is penalized heavily; over-experienced (> 12) penalized for overqualification.
    """
    yoe = float((candidate.get("profile", {}) or {}).get("years_of_experience") or 0)
    
    if 6.0 <= yoe <= 8.0:
        return 1.0
    elif 5.0 <= yoe <= 9.0:
        return 0.90
    elif 3.0 <= yoe <= 10.0:
        return 0.70
    elif yoe < 3.0:
        return max(0.1, (yoe / 3.0) * 0.5)
    else:  # yoe > 10.0
        excess = yoe - 10.0
        return max(0.3, 0.70 - excess * 0.05)


def score_education(candidate: dict, job: dict = DEFAULT_JOB) -> float:
    """
    Education score [0, 1].
    Institution tier + degree level + field relevance.
    """
    _, tier_weights, degree_weights, _ = get_db_config()
    
    education = candidate.get("education", [])
    if not education:
        return 0.3

    preferred_fields = [f.lower() for f in job.get("preferred_education_fields", [])]
    best_score = 0.0

    for edu in education:
        tier = (edu.get("tier") or "unknown").lower()
        degree = (edu.get("degree") or "").lower()
        field = (edu.get("field_of_study") or "").lower()

        tier_score = tier_weights.get(tier, 0.5)

        degree_score = 0.5
        for deg_key, deg_val in degree_weights.items():
            if deg_key in degree:
                degree_score = deg_val
                break

        field_score = 0.4
        for pf in preferred_fields:
            if pf in field or field in pf:
                field_score = 1.0
                break
            m = _fuzzy_match(field, pf)
            if m > field_score:
                field_score = m

        combined = 0.4 * tier_score + 0.35 * degree_score + 0.25 * field_score
        if combined > best_score:
            best_score = combined

    return min(1.0, best_score)


def score_signals(candidate: dict) -> float:
    """
    Behavioral signal score [0, 1].
    Evaluates:
      - Relocation (Dynamic Tiered India-based logic)
      - Notice Period (sub-30 day bonus, 90+ day penalty)
      - Platform Activity (login, responsiveness, GitHub activity)
    """
    _, _, _, location_tiers = get_db_config()
    
    signals = candidate.get("redrob_signals", {}) or {}
    profile = candidate.get("profile", {}) or {}
    
    loc = (profile.get("location") or "").lower()
    country = (profile.get("country") or "").lower()
    relocate = signals.get("willing_to_relocate", False)

    # 1. Location alignment using dynamic tiers
    loc_score = 0.5  # default neutral
    if country == "india":
        if location_tiers:
            # Check if any location in profile matches a tier
            matched_tier = 3
            for city, tier in location_tiers.items():
                if city in loc:
                    matched_tier = min(matched_tier, tier)
                    
            if matched_tier == 1:
                loc_score = 1.0
            elif matched_tier == 2:
                loc_score = 0.85
            elif relocate:
                loc_score = 0.85
            else:
                loc_score = 0.65
        else:
            # Fallback
            if any(l in loc for l in PREFERRED_LOCATIONS):
                loc_score = 1.0
            elif relocate:
                loc_score = 0.85
            else:
                loc_score = 0.65
    else:  # outside India
        if relocate:
            loc_score = 0.5
        else:
            loc_score = 0.2

    # 2. Notice period score
    np = signals.get("notice_period_days", 90)
    if np <= 30:
        np_score = 1.0  # highly preferred sub-30
    elif np <= 60:
        np_score = 0.75
    elif np <= 90:
        np_score = 0.5
    else:  # np > 90
        np_score = 0.25

    # 3. Platform activity
    completeness = float(signals.get("profile_completeness_score") or 50) / 100
    response_rate = float(signals.get("recruiter_response_rate") or 0.5)
    avg_resp_hours = float(signals.get("avg_response_time_hours") or 48)
    resp_time_score = max(0.0, 1.0 - avg_resp_hours / 96)
    responsiveness = 0.6 * response_rate + 0.4 * resp_time_score

    open_to_work = 1.0 if signals.get("open_to_work_flag", False) else 0.6
    interview_rate = signals.get("interview_completion_rate", 0.5)
    offer_acc = signals.get("offer_acceptance_rate", 0.0)
    offer_acc_norm = (offer_acc + 1) / 2

    github = signals.get("github_activity_score", -1)
    github_score = (github / 100) if github >= 0 else 0.35

    views_30d = min(signals.get("profile_views_received_30d", 0), 200)
    saved_30d = min(signals.get("saved_by_recruiters_30d", 0), 50)
    visibility = (views_30d / 200 * 0.5 + saved_30d / 50 * 0.5)

    verified = (
        (0.4 if signals.get("verified_email", False) else 0.0) +
        (0.3 if signals.get("verified_phone", False) else 0.0) +
        (0.3 if signals.get("linkedin_connected", False) else 0.0)
    )

    assessment_scores = signals.get("skill_assessment_scores", {}) or {}
    if assessment_scores:
        avg_assessment = sum(float(v) for v in assessment_scores.values()) / len(assessment_scores) / 100
    else:
        avg_assessment = 0.5

    combined_activity = (
        0.15 * completeness +
        0.20 * responsiveness +
        0.10 * open_to_work +
        0.10 * interview_rate +
        0.05 * offer_acc_norm +
        0.15 * github_score +
        0.10 * visibility +
        0.10 * verified +
        0.05 * avg_assessment
    )

    # Final Signals aggregation
    final_signals = 0.4 * loc_score + 0.3 * np_score + 0.3 * combined_activity
    return min(1.0, max(0.0, final_signals))


def compute_score(
    candidate: dict,
    job: dict = DEFAULT_JOB,
    weights: Optional[dict] = None,
) -> tuple[float, dict]:
    """
    Compute final weighted score for a candidate.
    Disqualifies honeypots to 0.0.
    """
    # Programmatic Honeypot Disqualification
    if is_honeypot(candidate):
        components = {
            "skill_score": 0.0,
            "title_career_score": 0.0,
            "experience_score": 0.0,
            "education_score": 0.0,
            "signal_score": 0.0,
            "final_score": 0.0,
        }
        return 0.0, components

    db_weights, _, _, _ = get_db_config()
    
    if weights is None:
        if db_weights:
            weights = db_weights
        else:
            weights = {
                "skills": 0.40,
                "title_career": 0.25,
                "experience": 0.15,
                "education": 0.10,
                "signals": 0.10,
            }

    s_skill = score_skills(candidate, job)
    s_title = score_title_career(candidate, job)
    s_exp = score_experience(candidate, job)
    s_edu = score_education(candidate, job)
    s_sig = score_signals(candidate)

    final = (
        weights["skills"] * s_skill +
        weights["title_career"] * s_title +
        weights["experience"] * s_exp +
        weights["education"] * s_edu +
        weights["signals"] * s_sig
    )

    # Prodigy-Aware Logic: Detect advanced degrees to mitigate experience penalties
    has_advanced_degree = False
    for edu in candidate.get("education", []) or []:
        deg = (edu.get("degree") or "").lower()
        if any(token in deg for token in ["phd", "ph.d", "master", "m.s.", "m.s ", "ms "]):
            has_advanced_degree = True
            break

    # Non-linear penalty for critical missing experience
    # If the candidate has effectively 0 experience, their score should drop drastically
    if s_exp < 0.2:
        if has_advanced_degree:
            final *= 0.9  # Mild penalty for prodigy (advanced degree with 0 years exp)
        else:
            final *= 0.6  # Apply a 40% penalty on the final additive score for juniors

    components = {
        "skill_score": round(s_skill, 4),
        "title_career_score": round(s_title, 4),
        "experience_score": round(s_exp, 4),
        "education_score": round(s_edu, 4),
        "signal_score": round(s_sig, 4),
        "final_score": round(final, 4),
    }
    return round(final, 4), components


def generate_reasoning(candidate: dict, components: dict, rank: int) -> str:
    """
    Generate detailed, non-templated, fact-based reasoning for the candidate.
    Cites specific experience, titles, skills, location, notice period, and indicators.
    """
    profile = candidate.get("profile", {}) or {}
    title = profile.get("current_title") or "Candidate"
    company = profile.get("current_company") or ""
    yoe = float(profile.get("years_of_experience") or 0)
    loc = profile.get("location") or "India"
    
    signals = candidate.get("redrob_signals", {}) or {}
    notice = float(signals.get("notice_period_days") or 90)
    github = float(signals.get("github_activity_score") or -1)
    
    # Extract matching skills
    skills_list = [s.get("name", "") for s in candidate.get("skills", [])]
    core_matching = [s for s in skills_list if _match_skill(s, DEFAULT_JOB["core_skills"]) > 0.6]
    nlp_matching = [s for s in skills_list if any(kw in s.lower() for kw in NLP_BOOST_KEYWORDS)]
    
    skills_str = ""
    if nlp_matching:
        skills_str = f"strong NLP/Vector search skills ({', '.join(nlp_matching[:3])})"
    elif core_matching:
        skills_str = f"proficiency in key ML skills ({', '.join(core_matching[:3])})"
    else:
        skills_str = "general backend and data science skills"

    # Construct facts
    role_info = f"{title}"
    if company:
        role_info += f" at {company}"
    role_info += f" with {yoe:.1f} years of experience"

    # Location alignment
    loc_clean = loc.split(",")[0].strip()
    loc_alignment = f"Based in {loc_clean}"
    if any(l in loc.lower() for l in ["noida", "pune"]):
        loc_alignment += " (direct hybrid match)"
    elif signals.get("willing_to_relocate", False):
        loc_alignment += " (willing to relocate)"

    # notice period buyout info
    notice = int(float(signals.get("notice_period_days") or 90))
    notice_str = f"{notice}-day notice"
    if notice <= 30:
        notice_str += " (highly immediate availability)"

    # github indicators
    github_str = ""
    if github >= 60:
        github_str = f"strong GitHub portfolio (score {int(github)})"
    elif github >= 0:
        github_str = f"active GitHub (score {int(github)})"

    # IT Consulting Service check for reasoning
    is_consulting = is_consulting_only(candidate)

    # Build reasoning in HTML format for beautiful UI rendering without extra dependencies
    s1 = f"<strong>Current Role</strong>: {role_info}."
    s2 = f"<strong>Skill Alignment</strong>: Demonstrates {skills_str} matching the JD."
    
    extra_details = [loc_alignment, notice_str]
    if github_str:
        extra_details.append(github_str)
    if is_consulting:
        extra_details.append("exclusively consulting firm background")
        
    s3 = f"<strong>Platform Signals</strong>: {'; '.join(extra_details)}."

    return f"{s1}<br>{s2}<br>{s3}"


def strip_html(text: str) -> str:
    """Strip HTML tags from reasoning text for CSV serialization."""
    if not text:
        return ""
    import re
    # Replace <br> and variants with space
    clean = re.sub(r'<br\s*/?>', ' ', text)
    # Strip all other HTML tags
    clean = re.sub(r'<[^>]+>', '', clean)
    # Normalize whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean
