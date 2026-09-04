import os
import json
import re
import google.generativeai as genai

# Server ke environment variable se API key lega
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)


def analyze_resume(resume_text, user_goal):
    # API key check
    current_key = os.environ.get("GEMINI_API_KEY")
    if not current_key:
        return {"error": "GEMINI_API_KEY environment variable set nahi hai."}

    genai.configure(api_key=current_key)

    prompt = f"""
You are an expert ATS and technical hiring manager.
Target Role: "{user_goal}"

Evaluate the resume and return strictly valid JSON matching this schema:
{{
  "ats_score": 75,
  "profile_summary": "Short 2-3 sentence executive assessment of fit",
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

  models_to_try = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-flash-latest"]
  last_error = None
  

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
            end = raw_text.rfind("}") + 1

            if start != -1 and end != 0:
                return json.loads(raw_text[start:end])
            return json.loads(raw_text)

        except Exception as e:
            last_error = e
            continue

    return {"error": f"AI Response Parse Error: {str(last_error)}"}
