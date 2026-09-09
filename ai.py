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

Analyze the candidate profile against the target role. Return ONLY a valid JSON object matching exactly this schema:
{{
  "ats_score": 78,
  "file_summary": "2-3 crisp sentences evaluating candidate fit for {role}.",
  "pay_scale": {{
    "category": "Corporate / Government / PSU",
    "salary_range": "e.g. ₹6.5 - ₹10.0 LPA",
    "in_hand_monthly": "e.g. ₹50,000 - ₹72,000 / month",
    "career_growth": "Next level promotion or salary jump in 2-3 years with percentage hike"
  }},
  "eligibility": {{
    "status": "Eligible / Partial Verification Needed / Not Eligible",
    "required_qualification": "Standard qualification required for this role",
    "matched_qualification": "What candidate holds based on resume",
    "criteria_fit": "Suitability assessment for freshers or experienced tracks"
  }},
  "matched_skills": ["Python", "Flask", "SQL"],
  "missing_skills": ["Docker", "Spring Boot", "System Design"],
  "roadmap": [
    "Phase 1 (Week 1-4): Detailed and comprehensive breakdown of foundational topics, core programming, and missing prerequisites.",
    "Phase 2 (Week 5-8): Advanced frameworks, architectural patterns, and hands-on production project milestones.",
    "Phase 3 (Week 9-12): Mock drills, previous year question papers, and cloud deployment strategies."
  ],
  "viva_questions": [
    {{
      "question": "Detailed technical or conceptual question 1 tailored to the role",
      "evaluation_focus": "What the interviewer expects to hear, core architecture, or practical resolution."
    }},
    {{
      "question": "Detailed technical or conceptual question 2 tailored to the role",
      "evaluation_focus": "What the interviewer expects to hear, core architecture, or practical resolution."
    }},
    {{
      "question": "Detailed technical or conceptual question 3 tailored to the role",
      "evaluation_focus": "What the interviewer expects to hear, core architecture, or practical resolution."
    }},
    {{
      "question": "Detailed technical or conceptual question 4 tailored to the role",
      "evaluation_focus": "What the interviewer expects to hear, core architecture, or practical resolution."
    }},
    {{
      "question": "Detailed technical or conceptual question 5 tailored to the role",
      "evaluation_focus": "What the interviewer expects to hear, core architecture, or practical resolution."
    }}
  ],
  "youtube_links": [
    {{
      "title": "Comprehensive tutorial title addressing a missing skill",
      "url": "[https://www.youtube.com/results?search_query=search+query](https://www.youtube.com/results?search_query=search+query)"
    }}
  ],
  "hr_pitch": "Respected Selection Panel,\\n\\nI am writing to express my strong candidacy for the position. Having recently audited my resume via CareersAnalysis, I achieved a strong ATS match score with demonstrated skills in Python, Flask, and database architectures.\\n\\nAs a proactive engineering student, I have built production-ready microservices and optimized application workflows. I would love to bring this technical rigor to your engineering team.\\n\\nSincerely,\\nSatyam Kumar"
}}

CRITICAL INSTRUCTIONS:
1. You MUST generate a dedicated YouTube tutorial link in the `youtube_links` array for **EVERY SINGLE SKILL** listed in `missing_skills`. Do not skip any missing skill.
2. `viva_questions` must contain **EXACTLY 5** rich objects where each object contains both "question" and "evaluation_focus".
3. `roadmap` must contain 3 detailed, comprehensive phases with week spans and thorough descriptions.

Candidate Details:
{resume_text}
"""
    try:
        return _call_gemini_raw(prompt, temperature=0.2, json_mode=True)
    except Exception as e:
        return {
            "ats_score": 65,
            "target_role": role,
            "file_summary": "Resume evaluated with baseline metrics due to generation timeout.",
            "pay_scale": {
                "category": "Corporate (IT/Product Companies)",
                "salary_range": "₹8.0 - ₹15.0 LPA",
                "in_hand_monthly": "₹60,000 - ₹1,05,000 / month",
                "career_growth": "2-3 वर्षों में Senior Engineer के रूप में 30%-50% का सैलरी हाइक।"
            },
            "eligibility": {
                "status": "Partial Verification Needed",
                "required_qualification": "B.Tech/B.E. in CS/IT/ECE or equivalent",
                "matched_qualification": "Engineering Student",
                "criteria_fit": "Fresher या 0-2 वर्ष का टेक्निकल अनुभव उपयुक्त है"
            },
            "matched_skills": ["Python", "Problem Solving"],
            "missing_skills": ["Docker", "Advanced System Design", "Spring Boot", "MLOps"],
            "roadmap": [
                "Phase 1 (Week 1-4): Python Programming, Data Structures, SQL, और Core Mathematics में महारत हासिल करें।",
                "Phase 2 (Week 5-8): Advanced frameworks, backend engineering, और hands-on production projects बनाएं।",
                "Phase 3 (Week 9-12): System Design, Docker containerization, और mock interview drills पूर्ण करें।"
            ],
            "viva_questions": [
                {
                    "question": "Explain core Object-Oriented Programming principles with a real-world system design example.",
                    "evaluation_focus": "Clarity on encapsulation, inheritance, polymorphism, and practical system scalability."
                },
                {
                    "question": "How do you optimize database indexing and query performance in high-load applications?",
                    "evaluation_focus": "Understanding B-Trees, query execution plans, normalization, and caching strategies."
                },
                {
                    "question": "What is the difference between multi-threading and multi-processing in Python?",
                    "evaluation_focus": "Global Interpreter Lock (GIL), CPU-bound vs I/O-bound tasks, and concurrency models."
                },
                {
                    "question": "Explain the lifecycle of a request in a Flask web application.",
                    "evaluation_focus": "Request context, app context, middleware, and routing mechanisms."
                },
                {
                    "question": "How do you containerize and deploy a microservice using Docker?",
                    "evaluation_focus": "Dockerfile layers, volume mounting, container networking, and orchestration basics."
                }
            ],
            "youtube_links": [
                {"title": "Docker Containerization Masterclass", "url": "[https://www.youtube.com/results?search_query=Docker+Tutorial+Complete](https://www.youtube.com/results?search_query=Docker+Tutorial+Complete)"},
                {"title": "Spring Boot & REST API Guide", "url": "[https://www.youtube.com/results?search_query=Spring+Boot+Tutorial](https://www.youtube.com/results?search_query=Spring+Boot+Tutorial)"},
                {"title": "Advanced System Design Complete Course", "url": "[https://www.youtube.com/results?search_query=System+Design+Interview](https://www.youtube.com/results?search_query=System+Design+Interview)"}
            ],
            "hr_pitch": "Respected Selection Panel,\n\nI am writing to express my strong candidacy for the position. Having audited my resume via CareersAnalysis, I achieved a strong ATS match score with demonstrated skills in Python, Flask, and database architectures.\n\nSincerely,\nSatyam Kumar"
        }


def get_comprehensive_drill(user_query):
    prompt = f"""
You are an expert exam mentor and academic strategist.
Analyze this user query: "{user_query}"
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
Rewrite this weak resume bullet point into 2 punchy, professional, metric-driven bullet points using the Google X-Y-Z formula.
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
            f"Architected and optimized modules for {raw_bullet}, reducing operational latency by 28%.",
            f"Engineered full-stack scalable components around {raw_bullet}, driving measurable performance gains."
        ]
