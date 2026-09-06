import os
import json
import re
import urllib.request
import urllib.error


def _call_gemini_raw(prompt, models_to_try=None, temperature=0.2, json_mode=True):
    """
    6 keys rotation ke sath Gemini ko direct x-goog-api-key header se call karta hai
    taaki nayi AQ. wali keys par 401 unsupported token error na aaye.
    """
    raw_keys = os.getenv("GEMINI_API_KEY", "").strip()
    if not raw_keys:
        raise ValueError("GEMINI_API_KEY is not set in Render environment.")

    # Comma, newline ya spaces se split karke saari keys ko safely clean karna
    api_keys = [k.strip().strip("'\"") for k in re.split(r'[\s,]+', raw_keys) if k.strip().strip("'\"")]

    if not models_to_try:
        models_to_try = [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro"
        ]

    last_error = None

    # Bari-bari har key aur model par try karega (Multi-key rotation)
    for key in api_keys:
        for m_name in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent"
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": key
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

                    # Markdown tags clean karna
                    raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.MULTILINE)
                    raw_text = re.sub(r"^```\s*", "", raw_text, flags=re.MULTILINE)

                    start = raw_text.find("{")
                    end = raw_text.rfind("}")
                    if start != -1 and end != -1:
                        raw_text = raw_text[start : end + 1]

                    return json.loads(raw_text)

            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8", errors="ignore")
                last_error = f"HTTP {e.code}: {err_msg}"
                continue
            except Exception as e:
                last_error = str(e)
                continue

    raise Exception(f"All keys and models failed. Last error: {last_error}")


def analyze_resume(resume_text, target_role="Software Developer", language="en", **kwargs):
    role = kwargs.get("role", target_role) or "Software Developer"

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
    {{"q": "Technical / CBT Question 1", "tip": "What interviewer looks for"}},
    {{"q": "Technical / CBT Question 2", "tip": "What interviewer looks for"}},
    {{"q": "Technical / CBT Question 3", "tip": "What interviewer looks for"}},
    {{"q": "Technical / CBT Question 4", "tip": "What interviewer looks for"}},
    {{"q": "Technical / CBT Question 5", "tip": "What interviewer looks for"}}
  ]
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
        print("Fallback triggered for drill:", e)
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
    except Exception as e:
        print("Fallback triggered for evaluation:", e)
        return {
            "score": "N/A",
            "verdict": "Reviewed",
            "feedback": "Include more direct keywords and practical examples in your answer.",
            "ideal_answer": "State the definition directly, mention a use case, and keep it crisp."
        }
