import os
import json
import re
import time
import urllib.request
import urllib.error


def _call_gemini_raw(prompt, models_to_try=None, temperature=0.2, json_mode=True):
    raw_keys = os.getenv("GEMINI_API_KEY", "").strip()
    if not raw_keys:
        raise ValueError("GEMINI_API_KEY is not set in Render environment.")

    api_keys = ["".join(k.split()).strip("'\"") for k in raw_keys.split(",") if k.strip()]
    api_keys = [k for k in api_keys if len(k) >= 35]

    if not api_keys:
        raise ValueError("No valid GEMINI_API_KEY found after cleaning.")

    if not models_to_try:
        models_to_try = [
            "gemini-3.6-flash",
            "gemini-2.5-flash",
            "gemini-1.5-flash"
        ]

    last_error = None

    for idx, key in enumerate(api_keys):
        for m_name in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent"
                headers = {
                    "Content-Type": "application/json",
                    "X-goog-api-key": key
                }
                body = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": temperature
                    }
                }
                if json_mode:
                    body["generationConfig"]["responseMimeType"] = "application/json"

                req = urllib.request.Request(
                    url,
                    data=json.dumps(body).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=25) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    raw_text = resp_data["candidates"][0]["content"]["parts"][0]["text"].strip()

                    if raw_text.startswith("```json"):
                        raw_text = raw_text[7:]
                    elif raw_text.startswith("```"):
                        raw_text = raw_text[3:]
                    if raw_text.endswith("```"):
                        raw_text = raw_text[:-3]
                    raw_text = raw_text.strip()

                    start = raw_text.find("{")
                    end = raw_text.rfind("}")
                    if start != -1 and end != -1:
                        raw_text = raw_text[start : end + 1]

                    return json.loads(raw_text)

            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8", errors="ignore")
                last_error = f"Key #{idx+1} ({m_name}) - HTTP {e.code}: {err_msg}"
                time.sleep(0.6)
                continue
            except Exception as e:
                last_error = f"Key #{idx+1} ({m_name}) - {str(e)}"
                continue

    raise Exception(f"All keys and models failed. Last error: {last_error}")


def analyze_resume(resume_text, target_role="Software Engineer", language="en", **kwargs):
    role = kwargs.get("role", target_role) or "Software Engineer"

    lang_rule = (
        "Respond in clear Hindi (Devanagari script), keeping core technical terms in English."
        if language == "hi"
        else "Respond in crisp, professional English."
    )

    prompt = f"""
You are an expert ATS auditor, senior corporate technical recruiter, and government exam counselor.
Target Role / Examination: {role}
Language Instruction: {lang_rule}

Analyze the candidate profile. Return ONLY a valid JSON object matching exactly this schema:
{{
  "ats_score": 78,
  "file_summary": "2-3 crisp sentences evaluating candidate fit for {role}.",
  "pay_scale": {{
    "category": "Corporate / Government / PSU",
    "salary_range": "e.g. ₹6.5 - ₹10.0 LPA",
    "in_hand_monthly": "e.g. ₹50,000 - ₹72,000 / month",
    "career_growth": "Next level promotion or salary jump in 2-3 years"
  }},
  "eligibility": {{
    "status": "Eligible / Partial Verification Needed / Not Eligible",
    "required_qualification": "Standard qualification required for this role",
    "matched_qualification": "What candidate holds",
    "age_or_experience_fit": "Fits criteria or details missing"
  }},
  "matched_skills": "Comma-separated string of matched skills found in resume",
  "missing_skills": "Comma-separated string of missing or recommended skills",
  "roadmap": [
    "Phase 1: Foundational topics and missing core tools (Week 1-2)",
    "Phase 2: Real-world projects or high-weightage mock drills (Week 3-4)"
  ],
  "viva_questions": [
    "Technical or conceptual question 1 tailored to the role",
    "Technical or conceptual question 2 tailored to the role",
    "Technical or conceptual question 3 tailored to the role",
    "Technical or conceptual question 4 tailored to the role",
    "Technical or conceptual question 5 tailored to the role"
  ],
  "youtube_links": [
    {{"title": "Advanced System Design & Flask Masterclass", "url": "[https://www.youtube.com/results?search_query=Advanced+Flask+System+Design](https://www.youtube.com/results?search_query=Advanced+Flask+System+Design)"}},
    {{"title": "ATS Resume Optimization & Google XYZ Formula", "url": "[https://www.youtube.com/results?search_query=ATS+Resume+Optimization+Tips](https://www.youtube.com/results?search_query=ATS+Resume+Optimization+Tips)"}}
  ],
  "hr_pitch": "Dear Hiring Manager,\n\nI am writing to express my strong interest in the position. Having recently audited my resume via CareersAnalysis, I achieved a strong ATS match score with demonstrated skills in Python, Flask, and database architectures.\n\nAs a proactive engineering student, I have built production-ready microservices and optimized application workflows. I would love to bring this technical rigor to your engineering team.\n\nBest regards,\nSatyam Kumar"
}}

Candidate Details:
{resume_text}
"""
    return _call_gemini_raw(prompt, temperature=0.2, json_mode=True)


def get_comprehensive_drill(user_query):
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
    try:
        return _call_gemini_raw(prompt, temperature=0.3, json_mode=True)
    except Exception as e:
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
                    "approach": "Master definitions, standard formulas, and practice previous year questions."
                }
            ],
            "strategy_and_mistakes": [
                "Pro Tip: Stick to 1 standard reference book and do active revision.",
                "Pitfall: Spending too much time on theory without solving time-bound questions."
            ]
        }


def evaluate_answer(question, user_answer):
    prompt = f"""
You are a senior technical interviewer and viva examiner.
Question: "{question}"
Candidate Answer: "{user_answer}"

Evaluate the answer objectively and return ONLY valid JSON:
{{
  "score": "7/10",
  "verdict": "Strong / Average / Needs Improvement",
  "feedback": "1-2 crisp sentences on what was good and what was missing.",
  "ideal_answer": "Crisp 2-sentence ideal response."
}}
"""
    try:
        return _call_gemini_raw(prompt, temperature=0.2, json_mode=True)
    except Exception:
        return {
            "score": "N/A",
            "verdict": "Reviewed",
            "feedback": "Include more direct keywords and practical examples in your answer.",
            "ideal_answer": "State the definition directly, mention a use case, and keep it crisp."
        }


def rewrite_bullet_point(raw_bullet, target_role="Software Engineer"):
    prompt = f"""You are an elite Tech Recruiter & ATS Optimization Expert.
Rewrite this weak resume bullet point into 2 punchy, professional, metric-driven bullet points using the Google X-Y-Z formula (Accomplished [X] measured by [Y] by doing [Z]).

Target Role: {target_role}
Weak Bullet: "{raw_bullet}"

Return ONLY a valid JSON object matching exactly this schema:
{{"options": ["Option 1 with strong action verb and metrics", "Option 2 with architectural focus"]}}
"""
    try:
        data = _call_gemini_raw(prompt, temperature=0.3, json_mode=True)
        return data.get("options", [])
    except Exception:
        return [
            f"Architected and deployed optimized modules for {raw_bullet}, reducing operational latency by 28%.",
            f"Engineered full-stack scalable components around {raw_bullet}, driving measurable performance gains."
        ]
