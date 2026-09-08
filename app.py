from flask import Flask, render_template, request, redirect, session, url_for, Response
from db import Base, engine, SessionLocal
import models
import PyPDF2
import docx
import json
from ai import analyze_resume, get_comprehensive_drill, rewrite_bullet_point

app = Flask(__name__)
app.secret_key = "secret12345678"
Base.metadata.create_all(bind=engine)


# Helper: TiDB Cache-First Query Engine (Zero Quota Waste)
def get_or_cache_syllabus(query):
    norm_query = query.lower().strip()
    db = SessionLocal()
    try:
        # 1. Pehle TiDB check karo (Instant 0.05s response)
        cached = db.query(models.SyllabusCache).filter_by(normalized_query=norm_query).first()
        if cached:
            try:
                return json.loads(cached.content_json)
            except Exception:
                return cached.content_json

        # 2. Agar database me nahi hai, tab Gemini call karo
        drill_data = get_comprehensive_drill(query)

        # 3. Future users ke liye TiDB me save kar lo
        content_to_save = json.dumps(drill_data) if isinstance(drill_data, (dict, list)) else str(drill_data)
        new_cache = models.SyllabusCache(
            normalized_query=norm_query,
            display_title=query.title(),
            content_json=content_to_save
        )
        db.add(new_cache)
        db.commit()
        return drill_data
    except Exception as e:
        db.rollback()
        # Edge-case fallback: database issue aane par direct AI response render hoga
        return get_comprehensive_drill(query)
    finally:
        db.close()


# Home
@app.route("/")
def home():
    return render_template("home.html", logged_in=("user" in session))


# Signup
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


# Login
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


# Dashboard
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")

    result = None
    searched_role = ""
    searched_jd = ""

    if request.method == "POST":
        user_goal = request.form.get("goal") or request.form.get("role")
        job_description = request.form.get("job_description", "").strip()
        resume_text = request.form.get("resume", "").strip()
        file = request.files.get("file")
        language = request.form.get("language", "en")

        searched_role = user_goal or ""
        searched_jd = job_description

        # File se text extract karna
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
        # Validation
        if not resume_text:
            result = {"error": "Resume text nahi mil paya! Kripya PDF ki jagah text box me direct paste karein."}
        elif not user_goal:
            result = {"error": "Kripya apna career goal likhein."}
        else:
            try:
                # Agar user ne specific JD / criteria diya hai toh AI ko target ke sath jod kar bhejo
                effective_goal = user_goal
                if job_description:
                    effective_goal = f"{user_goal} (Target Job Description / Criteria: {job_description})"

                result = analyze_resume(resume_text, effective_goal, language=language)

                # Report me target role aur JD criteria attach karo taaki dashboard me show ho
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
                db.close()
            except Exception as e:
                result = {"error": f"Backend/AI Error: {str(e)}"}

    return render_template(
        "dashboard.html",
        result=result,
        searched_role=searched_role,
        searched_jd=searched_jd
    )
# Micro-SaaS: Instant ATS Bullet Rewriter (AJAX)
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

# History
@app.route("/history")
def history():
    if "user" not in session:
        return redirect("/login")

    db = SessionLocal()
    user = db.query(models.User).filter_by(email=session["user"]).first()

    reports = []
    if user:
        reports = db.query(models.Report).filter_by(user_id=user.id).all()

    parsed_reports = []
    for r in reports:
        parsed_data = {}
        if isinstance(r.result, str):
            try:
                parsed_data = json.loads(r.result)
            except Exception:
                parsed_data = {}
        elif isinstance(r.result, dict):
            parsed_data = r.result

        parsed_reports.append({
            "id": r.id,
            "resume": r.resume_text,
            "result": parsed_data
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


# Logout
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
            return f"<h3 style='color:red;'>Error: Email '{email}' database mein nahi mila! Pehle Sign Up karein.</h3>", 404

        user.password = new_password
        db_session.commit()
        return redirect('/login')

    except Exception as e:
        db_session.rollback()
        import traceback
        return f"<h3>Database Error:</h3><pre>{traceback.format_exc()}</pre>", 500
    finally:
        db_session.close()


# ---------------- SEO & SEARCH CONSOLE ROUTES ----------------

# Google Site Verification File
@app.route('/google46e0869a1ebb8f89.html')
def google_verify_file():
    return "google-site-verification: google46e0869a1ebb8f89.html"


# Optimized robots.txt
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


# Comprehensive XML Sitemap for Google Indexing
@app.route('/sitemap.xml')
def sitemap():
    base_url = "https://ai-resume-analyzer-2jxj.onrender.com"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <!-- Home Page -->
    <url>
        <loc>{base_url}/</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
    <!-- Placement & Syllabus Hub -->
    <url>
        <loc>{base_url}/prep-hub</loc>
        <changefreq>daily</changefreq>
        <priority>0.9</priority>
    </url>
    <!-- Auth Pages -->
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


# ---------------- PREP & DRILL ROUTES ----------------

# Cached Topic Drill (Home Page Instant Explorer)
@app.route("/topic-drill", methods=["GET", "POST"])
def topic_drill():
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if not query:
            return redirect("/")
        
        drill_data = get_or_cache_syllabus(query)
        return render_template("drill_result.html", data=drill_data, query=query)
    
    return redirect("/")


# Placement & Syllabus Hub
@app.route("/prep-hub", methods=["GET", "POST"])
def prep_hub():
    result_data = None
    query = ""
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if query:
            result_data = get_or_cache_syllabus(query)
    
    return render_template("prep_hub.html", data=result_data, query=query, logged_in=("user" in session))


if __name__ == "__main__":
    app.run(debug=True)
