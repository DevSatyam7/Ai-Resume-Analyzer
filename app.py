import os
import json
import PyPDF2
import docx
from flask import Flask, render_template, request, redirect, session, url_for, Response, send_from_directory, send_file
from authlib.integrations.flask_client import OAuth
from db import Base, engine, SessionLocal
import models
from ai import analyze_resume, get_comprehensive_drill, rewrite_bullet_point

app = Flask(__name__)
app.secret_key = "secret12345678"
Base.metadata.create_all(bind=engine)

# Google OAuth Setup
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)


def get_or_cache_syllabus(query):
    norm_query = query.lower().strip()
    db = SessionLocal()
    try:
        cached = db.query(models.SyllabusCache).filter_by(normalized_query=norm_query).first()
        if cached:
            try:
                return json.loads(cached.content_json)
            except Exception:
                return cached.content_json

        drill_data = get_comprehensive_drill(query)
        content_to_save = json.dumps(drill_data) if isinstance(drill_data, (dict, list)) else str(drill_data)
        
        new_cache = models.SyllabusCache(
            normalized_query=norm_query,
            display_title=query.title(),
            content_json=content_to_save
        )
        db.add(new_cache)
        db.commit()
        return drill_data
    except Exception:
        db.rollback()
        return get_comprehensive_drill(query)
    finally:
        db.close()


@app.context_processor
def inject_user_reports():
    user_email = session.get("user")
    if user_email:
        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(email=user_email).first()
            if user:
                reports = db.query(models.Report).filter_by(user_id=user.id).order_by(models.Report.id.desc()).all()
                return dict(user_reports=reports)
        except Exception:
            return dict(user_reports=[])
        finally:
            db.close()
    return dict(user_reports=[])


@app.route("/")
def home():
    return render_template("home.html", logged_in=("user" in session))


@app.route("/about")
def about():
    return render_template("about.html", logged_in=("user" in session))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        db = SessionLocal()
        existing_user = db.query(models.User).filter_by(email=email).first()
        if existing_user:
            db.close()
            return "user already exist"

        user = models.User(email=email, password=password)
        db.add(user)
        db.commit()
        db.close()
        return redirect("/login")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        db = SessionLocal()
        user = db.query(models.User).filter_by(email=email, password=password).first()
        db.close()

        if user:
            session["user"] = user.email
            return redirect("/dashboard")
        else:
            return "Invalid credentials"

    return render_template("login.html")


@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_authorize', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/login/google/callback')
def google_authorize():
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        if user_info and 'email' in user_info:
            email = user_info['email']
            db = SessionLocal()
            try:
                user = db.query(models.User).filter_by(email=email).first()
                if not user:
                    user = models.User(email=email, password="")
                    db.add(user)
                    db.commit()
                session["user"] = user.email
            finally:
                db.close()
    except Exception as e:
        print(f"Google Auth Error: {e}")
    return redirect(url_for('dashboard'))


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")

    result = None
    searched_role = ""
    searched_jd = ""
    current_audit_id = None

    if request.method == "POST":
        user_goal = request.form.get("goal") or request.form.get("role")
        job_description = request.form.get("job_description", "").strip()
        resume_text = request.form.get("resume", "").strip()
        file = request.files.get("file")
        language = request.form.get("language", "en")

        searched_role = user_goal or ""
        searched_jd = job_description

        if file and file.filename != "":
            try:
                if file.filename.lower().endswith(".pdf"):
                    pdf_reader = PyPDF2.PdfReader(file)
                    extracted = ""
                    for page in pdf_reader.pages:
                        extracted += page.extract_text() or ""
                    if extracted.strip():
                        resume_text = extracted.strip()
                elif file.filename.lower().endswith(".docx"):
                    doc = docx.Document(file)
                    extracted = "\n".join([p.text for p in doc.paragraphs])
                    if extracted.strip():
                        resume_text = extracted.strip()
            except Exception as e:
                result = {"error": f"File read error: {str(e)}"}

        if not resume_text:
            result = {"error": "Resume text nahi mil paya! Kripya PDF ki jagah text box me direct paste karein."}
        elif not user_goal:
            result = {"error": "Kripya apna career goal likhein."}
        else:
            try:
                effective_goal = user_goal
                if job_description:
                    effective_goal = f"{user_goal} (Target Job Description / Criteria: {job_description})"

                result = analyze_resume(resume_text, effective_goal, language=language)

                if isinstance(result, dict) and "error" not in result:
                    result["target_role"] = user_goal
                    result["job_description"] = job_description

                db = SessionLocal()
                user = db.query(models.User).filter_by(email=session["user"]).first()
                if user:
                    report = models.Report(
                        user_id=user.id,
                        resume_text=resume_text,
                        result=json.dumps(result)
                    )
                    db.add(report)
                    db.commit()
                    db.refresh(report)
                    current_audit_id = report.id
                db.close()
            except Exception as e:
                result = {"error": f"Backend/AI Error: {str(e)}"}

    return render_template(
        "dashboard.html",
        result=result,
        searched_role=searched_role,
        searched_jd=searched_jd,
        current_audit_id=current_audit_id
    )


@app.route("/rewrite-bullet", methods=["POST"])
def rewrite_bullet():
    if "user" not in session:
        return {"error": "Pehle login karein"}, 401

    data = request.get_json() or {}
    raw_bullet = data.get("bullet", "").strip()
    role = data.get("role", "Software Engineer").strip()

    if not raw_bullet:
        return {"error": "Kripya koi bullet point likhein."}, 400

    options = rewrite_bullet_point(raw_bullet, role)
    return {"success": True, "options": options}


@app.route("/history")
def history():
    if "user" not in session:
        return redirect("/login")

    db = SessionLocal()
    user = db.query(models.User).filter_by(email=session["user"]).first()

    reports = []
    if user:
        reports = db.query(models.Report).filter_by(user_id=user.id).order_by(models.Report.id.desc()).all()

    parsed_reports = []
    for r in reports:
        raw_data = {}
        if isinstance(r.result, str):
            try:
                raw_data = json.loads(r.result)
            except Exception:
                raw_data = {}
        elif isinstance(r.result, dict):
            raw_data = r.result

        complete_data = {
            "ats_score": raw_data.get("ats_score", 70),
            "target_role": raw_data.get("target_role") or raw_data.get("goal") or "Software Engineer",
            "file_summary": raw_data.get("file_summary", "Professional evaluation summary record."),
            "pay_scale": raw_data.get("pay_scale", {"category": "Corporate", "salary_range": "₹6.0 - ₹12.0 LPA", "in_hand_monthly": "₹45,000 - ₹85,000 / month", "career_growth": "Standard progression path."}),
            "eligibility": raw_data.get("eligibility", {"status": "Eligible", "required_qualification": "B.Tech / MCA", "matched_qualification": "Verified", "age_or_experience_fit": "Fits criteria"}),
            "matched_skills": raw_data.get("matched_skills", ["Python", "Flask", "SQL"]),
            "missing_skills": raw_data.get("missing_skills", ["Docker", "System Design"]),
            "roadmap": raw_data.get("roadmap", ["Phase 1: Core Fundamentals", "Phase 2: Project Deployment"]),
            "viva_questions": raw_data.get("viva_questions", ["Explain Flask request context."]),
            "youtube_links": raw_data.get("youtube_links", [{"title": "Advanced Flask Tutorial", "url": "https://www.youtube.com/results?search_query=Advanced+Flask+System+Design"}]),
            "hr_pitch": raw_data.get("hr_pitch", "Dear Hiring Manager,\n\nI am writing to express my strong interest in the engineering position.\n\nBest regards,\nSatyam Kumar")
        }

        for k, v in raw_data.items():
            if v is not None:
                complete_data[k] = v

        parsed_reports.append({
            "id": r.id,
            "resume": r.resume_text,
            "result": complete_data
        })

    db.close()
    return render_template("history.html", reports=parsed_reports)


@app.route("/delete-report/<int:report_id>", methods=["POST"])
def delete_report(report_id):
    if "user" not in session:
        return redirect("/login")
    
    db = SessionLocal()
    user = db.query(models.User).filter_by(email=session["user"]).first()
    
    if user:
        report = db.query(models.Report).filter_by(id=report_id, user_id=user.id).first()
        if report:
            db.delete(report)
            db.commit()
            
    db.close()
    return redirect("/history")


@app.route("/view-audit/<int:report_id>")
def view_audit(report_id):
    if "user" not in session:
        return redirect("/login")
    
    db = SessionLocal()
    user = db.query(models.User).filter_by(email=session["user"]).first()
    if not user:
        db.close()
        return redirect("/login")
        
    report = db.query(models.Report).filter_by(id=report_id, user_id=user.id).first()
    if not report:
        db.close()
        return "Report nahi mili", 404
        
    try:
        raw_data = json.loads(report.result)
    except Exception:
        raw_data = {"error": "Could not parse saved audit data."}
        
    db.close()
    return render_template('dashboard.html', 
                           result=raw_data, 
                           searched_role=raw_data.get("target_role", "Software Engineer"), 
                           searched_jd=raw_data.get("job_description", ""),
                           current_audit_id=report.id)


@app.route("/download-audit/<int:report_id>")
def download_audit(report_id):
    if "user" not in session:
        return redirect("/login")
        
    db = SessionLocal()
    user = db.query(models.User).filter_by(email=session["user"]).first()
    if not user:
        db.close()
        return redirect("/login")
        
    report = db.query(models.Report).filter_by(id=report_id, user_id=user.id).first()
    if not report:
        db.close()
        return "Report nahi mili", 404
        
    file_name = f"CareersAnalysis_Report_{report.id}.txt"
    file_path = os.path.join('static', 'reports', file_name)
    os.makedirs(os.path.join('static', 'reports'), exist_ok=True)
    
    formatted_text = ""
    try:
        raw_data = json.loads(report.result)
        
        data = {
            "ats_score": raw_data.get("ats_score", 70),
            "target_role": raw_data.get("target_role") or "Software Engineer",
            "file_summary": raw_data.get("file_summary", "Professional profile evaluation record."),
            "pay_scale": raw_data.get("pay_scale", {"category": "Corporate", "salary_range": "₹6.0 - ₹12.0 LPA", "in_hand_monthly": "₹45,000 - ₹85,000 / month", "career_growth": "Standard growth path"}),
            "eligibility": raw_data.get("eligibility", {"status": "Eligible", "required_qualification": "B.Tech / MCA", "matched_qualification": "Matched", "age_or_experience_fit": "Meets criteria"}),
            "matched_skills": raw_data.get("matched_skills", ["Python", "Flask", "SQL"]),
            "missing_skills": raw_data.get("missing_skills", ["Docker", "System Design"]),
            "roadmap": raw_data.get("roadmap", ["Phase 1: Core Fundamentals", "Phase 2: Project Deployment"]),
            "viva_questions": raw_data.get("viva_questions", ["Explain Flask architecture."]),
            "youtube_links": raw_data.get("youtube_links", [{"title": "Flask Tutorial", "url": "https://youtube.com"}]),
            "hr_pitch": raw_data.get("hr_pitch", "Dear Hiring Manager,\n\nI am excited to apply...")
        }
        for k, v in raw_data.items():
            if v is not None:
                data[k] = v
        
        pay = data.get('pay_scale', {})
        elig = data.get('eligibility', {})
        
        matched_str = ", ".join(data.get('matched_skills', [])) if isinstance(data.get('matched_skills'), list) else str(data.get('matched_skills'))
        missing_str = ", ".join(data.get('missing_skills', [])) if isinstance(data.get('missing_skills'), list) else str(data.get('missing_skills'))
        
        roadmap_list = "\n".join([f"- {step}" for step in data.get('roadmap', [])]) if isinstance(data.get('roadmap'), list) else str(data.get('roadmap'))
        viva_list = "\n".join([f"{i+1}. {q}" for i, q in enumerate(data.get('viva_questions', []))]) if isinstance(data.get('viva_questions'), list) else str(data.get('viva_questions'))
        yt_list = "\n".join([f"- {yt.get('title')}: {yt.get('url')}" for yt in data.get('youtube_links', [])]) if isinstance(data.get('youtube_links'), list) else str(data.get('youtube_links'))
        
        formatted_text = f"""
============================================================
              CAREERSANALYSIS - AI AUDIT REPORT
============================================================
Report ID    : #{report.id}
Target Role  : {data.get('target_role', 'N/A')}
ATS Match    : {data.get('ats_score', 'N/A')}%
------------------------------------------------------------

1. EXECUTIVE PROFILE SUMMARY:
{data.get('file_summary', 'N/A')}

2. PAY SCALE & SALARY PROJECTION:
- Category          : {pay.get('category', 'N/A')}
- Projected Range   : {pay.get('salary_range', 'N/A')}
- Estimated In-Hand : {pay.get('in_hand_monthly', 'N/A')}
- Career Growth     : {pay.get('career_growth', 'N/A')}

3. ELIGIBILITY & CRITERIA FIT:
- Status            : {elig.get('status', 'N/A')}
- Required Qual.    : {elig.get('required_qualification', 'N/A')}
- Matched Qual.     : {elig.get('matched_qualification', 'N/A')}
- Experience Fit    : {elig.get('age_or_experience_fit', 'N/A')}

4. SKILL GAP & KEYWORD ANALYSIS:
- Matched Skills    : {matched_str}
- Missing Skills    : {missing_str}

5. ROLE PLACEMENT ROADMAP:
{roadmap_list}

6. TOP INTERVIEW & VIVA QUESTIONS:
{viva_list}

7. MISSING SKILL YOUTUBE LEARNING LINKS:
{yt_list}

8. INSTANT HR PITCH / COVER LETTER:
{data.get('hr_pitch', 'N/A')}

============================================================
Verified & Generated via CareersAnalysis Platform • Gemini AI
============================================================
"""
    except Exception as e:
        formatted_text = f"Report Data Error: {str(e)}\n\nRaw Data:\n{report.result}"

    with open(file_path, 'w', encoding='utf-8-sig') as f:
        f.write(formatted_text)
        
    db.close()
    return send_file(file_path, as_attachment=True, download_name=file_name)


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'GET':
        return render_template('forgot_password.html')

    email = request.form.get('email', '').strip()
    new_password = request.form.get('new_password', '').strip()

    if not email or not new_password:
        return "Email aur Password dono required hain.", 400

    db_session = SessionLocal()
    try:
        user = db_session.query(models.User).filter_by(email=email).first()
        if not user:
            return f"<h3 style='color:red;'>Error: Email '{email}' database mein nahi mila!</h3>", 404

        user.password = new_password
        db_session.commit()
        return redirect('/login')
    except Exception as e:
        db_session.rollback()
        return f"<h3>Database Error</h3>", 500
    finally:
        db_session.close()


@app.route('/google46e0869a1ebb8f89.html')
def google_verify_file():
    return "google-site-verification: google46e0869a1ebb8f89.html"


@app.route('/robots.txt')
def robots():
    content = """User-agent: *
Allow: /
Allow: /prep-hub
Disallow: /dashboard
Disallow: /history
Disallow: /delete-report/
Disallow: /forgot-password
Disallow: /logout

Sitemap: https://ai-resume-analyzer-2jxj.onrender.com/sitemap.xml
"""
    return Response(content, mimetype="text/plain")


@app.route('/sitemap.xml')
def sitemap():
    base_url = "https://ai-resume-analyzer-2jxj.onrender.com"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{base_url}/</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>{base_url}/prep-hub</loc>
        <changefreq>daily</changefreq>
        <priority>0.9</priority>
    </url>
    <url>
        <loc>{base_url}/login</loc>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
    <url>
        <loc>{base_url}/signup</loc>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
</urlset>"""
    return Response(xml, mimetype="application/xml")


@app.route("/topic-drill", methods=["GET", "POST"])
def topic_drill():
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if not query:
            return redirect("/")
        
        drill_data = get_or_cache_syllabus(query)
        return render_template("drill_result.html", data=drill_data, query=query)
    
    return redirect("/")


@app.route("/prep-hub", methods=["GET", "POST"])
def prep_hub():
    result_data = None
    query = ""
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if query:
            result_data = get_or_cache_syllabus(query)
    
    return render_template("prep_hub.html", data=result_data, query=query, logged_in=("user" in session))


@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')


@app.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')


if __name__ == "__main__":
    app.run(debug=True)
