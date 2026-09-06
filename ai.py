import os
import json
import re
import google.generativeai as genai


def analyze_resume(resume_text, target_role="Software Developer", language="en", **kwargs):
    role = kwargs.get("role", target_role) or "Software Developer"

    raw_keys = os.getenv("GEMINI_API_KEY", "").strip()
    if not raw_keys:
        raise ValueError("GEMINI_API_KEY is not set in Render environment.")

    api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

    # Language toggle instruction
    lang_rule = (
        "Respond in clear Hindi (Devanagari script), keeping core technical terms in English."
        if language == "hi"
        else "Respond in crisp, professional English."
    )

    prompt = f"""
You are an expert ATS auditor, senior corporate technical recruiter, and government exam counselor.
Target Role / Examination: {role}
Language Instruction: {lang_rule}

Analyze the resume or candidate details below. Return ONLY a valid JSON object matching exactly this schema:
{{
  "ats_score": 78,
  "pay_scale": {{
    "category": "Corporate / Government / PSU",
    "salary_range": "e.g. ₹6.5 - ₹10.0 LPA or 7th CPC Level 7 (₹44,900 - ₹1,42,400)",
    "in_hand_monthly": "e.g. ₹50,000 - ₹72,000 / month",
    "career_growth": "Next level promotion or salary jump in 2-3 years"
  }},
  "eligibility": {{
    "status": "Eligible / Partial Verification Needed / Not Eligible",
    "required_qualification": "Standard qualification required for this role",
    "matched_qualification": "What candidate holds",
    "age_or_experience_fit": "Fits criteria or details missing"
  }},
  "profile_summary": "2-3 crisp sentences evaluating candidate fit for {role}.",
  "matched_skills": ["Skill1", "Skill2", "Skill3"],
  "missing_skills": ["SkillA", "SkillB"],
  "roadmap": [
    {{"phase": "Phase 1 (Week 1-2)", "tasks": "Foundational topics and missing core tools"}},
    {{"phase": "Phase 2 (Week 3-4)", "tasks": "Real-world projects or high-weightage mock drills"}}
  ],
  "interview_questions": [
    {{"q": "Technical / CBT Question 1", "tip": "What interviewer or examiner looks for"}},
    {{"q": "Technical / CBT Question 2", "tip": "What interviewer or examiner looks for"}},
    {{"q": "Technical / CBT Question 3", "tip": "What interviewer or examiner looks for"}},
    {{"q": "Technical / CBT Question 4", "tip": "What interviewer or examiner looks for"}},
    {{"q": "Technical / CBT Question 5", "tip": "What interviewer or examiner looks for"}}
  ]
}}

Resume / Profile Details:
{resume_text}
"""

    models_to_try = [
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-flash-latest"
    ]

    last_error = None

    for key in api_keys:
        try:
            genai.configure(api_key=key, transport="rest")
        except Exception as e:
            last_error = e
            continue

        for m_name in models_to_try:
            try:
                model = genai.GenerativeModel(
                    model_name=m_name,
                    system_instruction=f"You are a strict ATS and exam career evaluator. Output only valid JSON. {lang_rule}"
                )
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.2,
                        "response_mime_type": "application/json"
                    }
                )

                raw_text = response.text.strip()
                raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.MULTILINE)
                raw_text = re.sub(r"^```\s*", "", raw_text, flags=re.MULTILINE)

                start = raw_text.find("{")
                end = raw_text.rfind("}")
                if start != -1 and end != -1:
                    raw_text = raw_text[start : end + 1]

                return json.loads(raw_text)

            except Exception as e:
                last_error = e
                continue

    raise Exception(f"All models failed for resume analysis. Last error: {last_error}")


def get_comprehensive_drill(user_query):
    raw_keys = os.getenv("GEMINI_API_KEY", "").strip()
    if not raw_keys:
        raise ValueError("GEMINI_API_KEY is not set in Render environment.")

    api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

    prompt = f"""
You are an expert exam mentor and academic strategist.
Analyze this user query: "{user_query}"

Determine whether it is a competitive exam (JEE, NEET, SSC, GATE, RRB) or a subject topic (DSA, DBMS, Physics).
Return ONLY a valid JSON object matching this schema:

{{
  "query_title": "{user_query}",
  "category_type": "Competitive Exam or Academic Topic",
  "summary": "2-3 crisp sentences explaining this exam or topic.",
  "key_stats": {{
    "eligibility_or_prereq": "Eligibility or basic requirements",
    "difficulty_rating": "Moderate / High / Extreme",
    "recommended_timeline": "Estimated prep duration"
  }},
  "syllabus_units": [
    {{
      "unit_name": "Unit or Section Name",
      "weightage": "High / Medium / Low",
      "must_cover_topics": "Key chapters or subtopics"
    }}
  ],
  "high_yield_questions": [
    {{
      "q": "Real exam or interview pattern question",
      "approach": "Clear step-by-step logic or solution approach"
    }}
  ],
  "strategy_and_mistakes": [
    "Pro Tip: Recommended book or preparation tip",
    "Pitfall: Common mistake where students lose marks"
  ]
}}
"""

    models_to_try = [
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-flash-latest"
    ]

    for key in api_keys:
        try:
            genai.configure(api_key=key, transport="rest")
        except Exception:
            continue

        for m_name in models_to_try:
            try:
                model = genai.GenerativeModel(
                    model_name=m_name,
                    system_instruction="You are an exam and subject expert. Output only valid JSON."
                )
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.3,
                        "response_mime_type": "application/json"
                    }
                )

                raw_text = response.text.strip()
                raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.MULTILINE)
                raw_text = re.sub(r"^```\s*", "", raw_text, flags=re.MULTILINE)

                start = raw_text.find("{")
                end = raw_text.rfind("}")
                if start != -1 and end != -1:
                    raw_text = raw_text[start : end + 1]

                return json.loads(raw_text)

            except Exception:
                continue

    return {
        "query_title": user_query,
        "category_type": "Quick Guide",
        "summary": "Essential roadmap and practice outline for preparation.",
        "key_stats": {
            "eligibility_or_prereq": "Standard eligibility criteria",
            "difficulty_rating": "Moderate",
            "recommended_timeline": "Consistent 4-8 weeks"
        },
        "syllabus_units": [
            {
                "unit_name": "Core Fundamentals",
                "weightage": "High",
                "must_cover_topics": "Basics, conceptual problems, and previous year patterns"
            }
        ],
        "high_yield_questions": [
            {
                "q": f"What are the foundational concepts tested in {user_query}?",
                "approach": "Master definitions, standard formulas, and practice 15-20 previous year questions."
            }
        ],
        "strategy_and_mistakes": [
            "Pro Tip: Stick to 1 standard reference book and do active revision.",
            "Pitfall: Spending too much time on theory without solving time-bound questions."
        ]
    }
