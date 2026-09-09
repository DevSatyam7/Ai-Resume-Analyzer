import os
import json
import PyPDF2
import docx
from flask import Flask, render_template, request, redirect, session, url_for, Response, send_from_directory, send_file
from db import Base, engine, SessionLocal
import models
from ai import analyze_resume, get_comprehensive_drill, rewrite_bullet_point

app = Flask(__name__)
app.secret_key = "secret12345678"
Base.metadata.create_all(bind=engine)


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


# Sidebar history ke liye context processor jo session check karke data bhejega
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
    
    content_text = report.result
    try:
        parsed_res = json.loads(report.result)
        if isinstance(parsed_res, dict):
            content_text = json.dumps(parsed_res, indent=2, ensure_ascii=False)
    except Exception:
        pass

    full_content = f"""==================================================
        CAREERSANALYSIS — AI AUDIT REPORT
==================================================
Report ID: #{report.id}
Platform: CareersAnalysis
Developer: Satyam Kumar (GEC Munger)
--------------------------------------------------

{content_text}

==================================================
End of Report • Confidential Career Assessment
==================================================
"""
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
        
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
