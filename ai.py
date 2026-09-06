import os
import json
import re
import google.generativeai as genai

def analyze_resume(resume_text, target_role="Software Developer", **kwargs):
    role = kwargs.get("role", target_role) or "Software Developer"

    raw_keys = os.getenv("GEMINI_API_KEY", "").strip()
    if not raw_keys:
        raise ValueError("GEMINI_API_KEY is not set in Render environment.")

    # Single key ya comma-separated multiple keys dono support karega
    api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

    prompt = f"""
You are an expert ATS (Applicant Tracking System) evaluator and senior technical recruiter.
Target Career Role: {role}

Analyze the resume and return a valid JSON object matching exactly this schema:
{{
  "ats_score": 75,
  "profile_summary": "Short 2-3 sentence executive assessment of fit.",
  "matched_skills": ["Skill1", "Skill2"],
  "missing_skills": ["SkillA", "SkillB"],
  "roadmap": [
    {{"phase": "Phase 1 (Week 1-2)", "tasks": "Core focus and tools to learn"}},
    {{"phase": "Phase 2 (Week 3-4)", "tasks": "Advanced implementations and projects"}}
  ],
  "interview_questions": [
    {{"question": "Key technical question", "tip": "What the interviewer wants to hear"}}
  ]
}}

Resume:
{resume_text}
"""

    # Flash-Lite ko pehle rakha hai taaki 20 limit wala error na aaye aur fast chale
    models_to_try = [
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-flash-latest"
    ]

    last_error = None

    # Agar multiple keys hain to unpar bari-bari try karega
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
                    system_instruction="You are a strict ATS evaluator. Output only valid JSON."
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

    raise Exception(f"All models failed. Last error: {last_error}")
def get_comprehensive_drill(user_query):
    prompt = f"""
    You are an elite academic counselor, competitive exam strategist, and subject master.
    The user is asking about: "{user_query}"

    Analyze whether this is an EXAM (e.g. JEE, NEET, SSC CGL, RRB NTPC, GATE, UPSC) 
    or an ACADEMIC/TECH SUBJECT/TOPIC (e.g. DSA, Thermodynamics, DBMS, Operating Systems).

    Provide a complete, accurate breakdown strictly in valid JSON format without any markdown backticks.
    
    Format:
    {{
      "query_title": "{user_query}",
      "category_type": "Competitive Exam OR Academic Topic",
      "summary": "2-3 crisp sentences detailing what this exam/topic covers and why it matters.",
      "key_stats": {{
        "eligibility_or_prereq": "Eligibility criteria (for exam) or prerequisites (for topic)",
        "difficulty_rating": "Moderate / High / Extreme",
        "recommended_timeline": "Estimated prep duration (e.g. 6 Months, 4 Weeks)"
      }},
      "syllabus_units": [
        {{
          "unit_name": "Core Unit / Section Name",
          "weightage": "High / Medium / Low",
          "must_cover_topics": "Comma separated key topics under this unit"
        }},
        {{
          "unit_name": "Secondary Unit / Section Name",
          "weightage": "High / Medium",
          "must_cover_topics": "Comma separated key topics"
        }}
      ],
      "high_yield_questions": [
        {{
          "q": "Real exam pattern / Viva / Interview question 1",
          "approach": "Step-by-step logic, formula, or crisp answer"
        }},
        {{
          "q": "Real exam pattern / Viva / Interview question 2",
          "approach": "Step-by-step logic, formula, or crisp answer"
        }},
        {{
          "q": "Real exam pattern / Viva / Interview question 3",
          "approach": "Step-by-step logic, formula, or crisp answer"
        }},
        {{
          "q": "Real exam pattern / Viva / Interview question 4",
          "approach": "Step-by-step logic, formula, or crisp answer"
        }},
        {{
          "q": "Real exam pattern / Viva / Interview question 5",
          "approach": "Step-by-step logic, formula, or crisp answer"
        }}
      ],
      "strategy_and_mistakes": [
        "Pro Tip: Recommended standard resource, book, or scoring strategy",
        "Pitfall: Frequent trap where students lose marks or get negative marking"
      ]
    }}
    """

    # Aapka existing Gemini model call
    response = model.generate_content(prompt)
    clean_text = response.text.strip()
    
    # Markdown formatting clean karna
    clean_text = re.sub(r"^```json\s*", "", clean_text)
    clean_text = re.sub(r"^```\s*", "", clean_text)
    clean_text = re.sub(r"\s*```$", "", clean_text)

    try:
        return json.loads(clean_text)
    except Exception as e:
        print("JSON Parsing Error in Topic Drill:", e)
        return {
            "query_title": user_query,
            "category_type": "Overview",
            "summary": "Quick breakdown for preparation.",
            "key_stats": {
                "eligibility_or_prereq": "Standard criteria",
                "difficulty_rating": "Moderate",
                "recommended_timeline": "Consistent Practice"
            },
            "syllabus_units": [],
            "high_yield_questions": [],
            "strategy_and_mistakes": ["Focus on core concepts and past questions."]
        }    
