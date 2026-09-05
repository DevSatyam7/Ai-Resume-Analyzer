from flask import Flask, render_template, request, redirect, session, url_for, Response
from db import Base, engine, SessionLocal
import models
import PyPDF2
import docx
import json
from ai import analyze_resume

app = Flask(__name__)
app.secret_key = "secret12345678"
Base.metadata.create_all(bind=engine)


# home
@app.route("/")
def home():
    return render_template("home.html", logged_in=("user" in session))

# -----signup
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


# login-----
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
# --dashboard
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")

    result = None

    if request.method == "POST":
        user_goal = request.form.get("goal") or request.form.get("role")
        resume_text = request.form.get("resume", "").strip()
        file = request.files.get("file")

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
                # AI Analysis
                result = analyze_resume(resume_text, user_goal)

                # Database Save (Bina email column ke taaki crash na ho)
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

    return render_template("dashboard.html", result=result)
# history
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
            "id": r:id,
            "resume": r.resume_text,
            "result": parsed_data
        })

    db.close()  # <-- Ab ye safe jagah par close hoga

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

# logout
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
@app.route('/robots.txt')
def robots():
    content = "User-agent: *\nAllow: /\nDisallow: /dashboard\nDisallow: /forgot-password\nDisallow: /login\nDisallow: /signup"
    return Response(content, mimetype="text/plain")

@app.route('/sitemap.xml')
def sitemap():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
       <url>
          <loc>https://ai-resume-analyzer-2jxj.onrender.com/</loc>
          <priority>1.0</priority>
       </url>
    </urlset>"""
    return Response(xml, mimetype="application/xml")

if __name__ == "__main__":
    app.run(debug=True)
