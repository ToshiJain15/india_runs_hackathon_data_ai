# Redrob Intelligent Candidate Discovery & Ranking System

Proof of Concept (POC) system for candidate discovery and ranking, developed for the **Redrob India Runs Data & AI Challenge**. 

This repository implements a rule-based, multi-factor candidate scoring engine designed to rank a pool of 100,000 candidates against a **Senior AI Engineer** Job Description in under 50 seconds on a single CPU core, using less than 500MB of memory.

---

## Key Features & Methodology

The system decomposes the candidate-JD fit into **5 independent dimensions** with transparent weights, followed by tie-breaking, score normalization, and programmatic reasoning generation.

### 1. 5-Factor Weighted Scoring Engine
> [!IMPORTANT]
> **Architectural Trade-Off: Rules over Vectors**
> While modern AI systems heavily utilize dense vector embeddings (e.g. FAISS/Pinecone) for semantic matching, we deliberately chose a deterministic, CPU-bound string matching engine augmented with a Semantic Synonym Map. This architectural trade-off was necessary to satisfy the strict hackathon constraint of scoring 100,000 candidates in under 50 seconds on a single offline CPU core.

- **Skill Match (40% Weight)**: Matches candidate skills against the JD's core and bonus skills using fuzzy token-overlap (Jaccard similarity) and a `SYNONYMS_MAP` to resolve common acronyms. Individual skill scores are modulated by:
  - **Proficiency weights** (expert = 1.0, beginner = 0.25).
  - **Endorsement trust curve** ($0.5 + 0.5 \times \tanh(\text{endorsements}/20)$).
  - **Duration trust curve** ($0.4 + 0.6 \times \tanh(\text{duration}/18)$).
  - **NLP/Vector DB Boost**: Additional score bonus for skills matching specific keywords (e.g. Pinecone, Weaviate, BGE, dense retrieval, sentence-transformers) as preferred by the JD.
- **Title & Career (25% Weight)**: Scores the current role title and career history. Applies a **recency decay** ($1/\text{position\_index}$) to emphasize recent job roles.
  - **Consulting Service Firm Penalty**: Candidates who have worked *exclusively* at major IT consulting/service firms (TCS, Infosys, Wipro, Accenture, Cognizant, etc.) receive a **0.2× multiplier** to align with the JD's preference for product-company experience.
- **Experience (15% Weight)**: Piecewise linear function that peaks (1.0) at the ideal **6–8 years of experience (YOE)** range. 
  - **Non-Linear Penalty:** Candidates with critically low experience (<20% of ideal) receive a harsh, non-linear 40% reduction to their final score to prevent unqualified candidates from ranking high through sheer skill matching.
- **Education (10% Weight)**: Combines institution tier, degree level (PhD, M.Tech, B.Tech), and field of study relevance (CS, Stats, Math, IT).
- **Behavioral Signals (10% Weight)**: Aggregates Redrob platform signals:
  - **Location Alignment (40%)**: नोएडा (Noida)/पुणे (Pune) hybrid preference gets 1.0, India relocation gets 0.85, non-India non-relocating profiles get 0.2.
  - **Notice Period (30%)**: Notice periods ≤30 days get 1.0; notice periods ≥90 days get 0.25.
  - **Platform Engagement (30%)**: Combines profile completeness, response rate, responsiveness, GitHub activity score, verified contacts, and skill assessment completion.

### 2. Honeypot Disqualification Gate
To prevent "keyword stuffers" and impossible candidate profiles from ranking, a dedicated disqualification step runs **4 physical profile checks** and sets the candidate's score to `0.0` if any are triggered:
1. **Expert Zero-Duration**: $\ge 3$ expert skills listed with 0 months of duration.
2. **Experience Mismatch**: Total years of experience exceeds total career history duration by $> 2$ years.
3. **Job Longer than YOE**: Any single career job's duration exceeds the candidate's total profile YOE.
4. **Calendar Mismatch**: A single job's listed duration exceeds the actual calendar months between the start and end dates (with a 3-month buffer).

### 3. Programmatic, Fact-Based Reasoning
To prevent hallucinations and satisfy manual review parameters, a reasoning generator drafts a UI-ready HTML summary citing **only verified profile attributes**:
- Current job title and employer.
- Years of experience.
- Specific matching skills (e.g. NLP, Pinecone, PyTorch).
- Location alignment and notice period days.
- GitHub activity score.

---

## File Structure

```
├── rank.py                 # CLI entry point for the ranking pipeline
├── submission.csv          # Output CSV containing top-100 ranked candidates
├── requirements.txt        # Project dependencies (Django, WhiteNoise, etc.)
├── submission_metadata.yaml# Submission metadata for challenge organizers
├── slide_assets/           # Extracted background slides for presentation
├── presentation.html       # HTML source of the presentation deck
├── presentation.pdf        # PDF compiled copy of the presentation deck
└── redrob_ranker/          # Django sandbox project
    ├── db.sqlite3          # Pre-populated local database
    ├── manage.py           # Django manager
    └── ranker/             # Core Django app (views, templates, static)
├── tests/                  # Automated unit test suite
│   └── test_scorer.py      # Test cases for honeypots, penalties, and acronym matching
```

---

## Installation & Setup

Ensure you have **Python 3.14** (or Python 3.8+) installed.

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Ranking Pipeline (CLI)
To run the end-to-end candidate ranking on the pool of 100,000 candidates and output the top-100:
```bash
python rank.py --candidates ./India_runs_data_and_ai_challenge/candidates.jsonl --out ./submission.csv
```

### 3. Run the Sandbox Web Dashboard (Django)
A local hosted sandbox dashboard allows you to visualize metrics, search through candidate profiles, adjust factor weights, and trigger ranking runs on candidate subsets.
```bash
cd redrob_ranker
python manage.py runserver
```
Visit `http://localhost:8000` in your browser.

- **`/` (Dashboard)**: Run ranking jobs on the sample or full pool. Shows statistics for previous runs.
- **`/results/<run_id>/`**: Interactive table of the top-100 list containing sub-scorer details, profile highlights, and generated reasoning.
- **`/analytics/<run_id>/`**: Interactive analytics charts visualizing score distribution histograms, top skills, top industries, and average weights.

---

## Compute Performance

The entire CLI ranking pipeline runs under the following limits:
- **Runtime**: **~50 seconds** to stream, filter, score, sort, and save 100,000 candidates.
- **Memory**: **<500MB RAM** (utilizes file streaming and caches Jaccard computations).
- **GPU**: **None** (100% CPU-only logic).
- **Network**: **None** (zero external API dependencies, offline-first execution).
