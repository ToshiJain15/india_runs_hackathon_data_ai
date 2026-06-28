import re
import warnings
from .scorer import CONSULTING_COMPANIES

class RobustPDFExtractor:
    """
    Modular, robust extractor for PDFs.
    Designed to fall back to a stubbed LLM if Regex parsing yields low confidence.
    """
    
    def __init__(self, jd=None):
        self.jd = jd or {}
        
    def extract(self, tmp_path: str) -> dict:
        import PyPDF2
        import json
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reader = PyPDF2.PdfReader(tmp_path)
            text = "".join(page.extract_text() or "" for page in reader.pages).lower()
            
        # Basic keyword extraction
        found_skills = []
        for skill in self.jd.get("core_skills", []) + self.jd.get("bonus_skills", []):
            if skill.lower() in text:
                found_skills.append({"name": skill, "proficiency": "expert", "duration_months": 36})
                
        # Initial Extraction via Regex
        yoe, notice_period, title = self._regex_extract(text)
        
        # Heuristic: If we relied on fallbacks entirely (5.0 YOE, 30 days, default title),
        # try the LLM stub (which currently acts as a secondary structural parser).
        if yoe == 5.0 and notice_period == 30 and title == "AI Engineer (From PDF)":
            yoe_llm, notice_llm, title_llm = self._llm_extract_stub(text)
            if yoe_llm is not None: yoe = yoe_llm
            if notice_llm is not None: notice_period = notice_llm
            if title_llm is not None: title = title_llm
            
        mock_cand = [{
            "candidate_id": "UPLOADED_PDF",
            "profile": {
                "current_title": title,
                "years_of_experience": yoe
            },
            "skills": found_skills,
            "career_history": [],
            "redrob_signals": {
                "willing_to_relocate": True, 
                "notice_period_days": notice_period
            }
        }]
        
        return mock_cand, text
        
    def _regex_extract(self, text: str):
        # YOE
        yoe = 5.0
        exp_match = re.search(r'(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?|yearsof|yrsof|experience|yoe)', text)
        if exp_match:
            yoe = float(exp_match.group(1))
        else:
            exp_match_2 = re.search(r'experience\s*[:\-]?\s*(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)?', text)
            if exp_match_2:
                yoe = float(exp_match_2.group(1))
            else:
                exp_match_fallback = re.search(r'with\s*(\d+(?:\.\d+)?)\+?', text)
                if exp_match_fallback:
                    yoe = float(exp_match_fallback.group(1))
                    
        # Notice
        notice_period = 30
        notice_match = re.search(r'(?:notice\s*period|notice|buyout)\s*[:\-]?\s*(\d+)\s*(?:days?|days\b)', text)
        if notice_match:
            notice_period = int(notice_match.group(1))
        else:
            notice_mo_match = re.search(r'(\d+)\s*(?:months?|mo)\s*(?:notice|buyout)', text)
            if notice_mo_match:
                notice_period = int(notice_mo_match.group(1)) * 30
            elif "immediate" in text or "0 days" in text:
                notice_period = 0
            else:
                is_current_consulting = False
                for cc in CONSULTING_COMPANIES:
                    if cc.lower() in text and ("present" in text or "current" in text):
                        is_current_consulting = True
                        break
                if is_current_consulting:
                    notice_period = 90
                    
        # Title
        title = "AI Engineer (From PDF)"
        for t in self.jd.get("relevant_titles", []):
            if t.lower() in text:
                title = t.title()
                break
                
        return yoe, notice_period, title
        
    def _llm_extract_stub(self, text: str):
        """
        Stub for an LLM fallback API call.
        In a production environment with an API key, this would dispatch to 
        GPT-3.5-Turbo or similar to structurally extract YOE, Notice, and Title.
        
        For now, it returns None to keep regex values, but the architecture is ready.
        """
        # Example Implementation:
        # if not settings.OPENAI_API_KEY: return None, None, None
        # response = openai.ChatCompletion.create(...)
        return None, None, None
