from flask import Flask, render_template, request, redirect, session
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
    if "user" in session:
        return redirect("/dashboard")
    return redirect("/login")


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
            "resume": r.resume_text,
            "result": parsed_data
        })

    db.close()  # <-- Ab ye safe jagah par close hoga

    return render_template("history.html", reports=parsed_reports)


# logout
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    from flask import request, render_template, redirect, url_for
    from werkzeug.security import generate_password_hash
    from models import db, User
    import sqlalchemy as sa

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        new_password = request.form.get('new_password', '').strip()

        if not email or not new_password:
            return "Email aur New Password dono required hain.", 400

        # Line 167 ka safe fix (Modern SQLAlchemy syntax)
        user = None
        try:
            user = db.session.execute(sa.select(User).filter_by(email=email)).scalar_one_or_none()
        except Exception:
            user = db.session.query(User).filter_by(email=email).first()

        if not user:
            return f"<h3 style='color:red; font-family:sans-serif;'>Error: Email '{email}' database mein register nahi hai!</h3>", 404

        # Password update
        hashed_password = generate_password_hash(new_password)
        if hasattr(user, 'set_password'):
            user.set_password(new_password)
        elif hasattr(user, 'password_hash'):
            user.password_hash = hashed_password
        else:
            user.password = hashed_password

        db.session.commit()
        return redirect(url_for('login'))

    return render_template('forgot_password.html')
    
if __name__ == "__main__":
    app.run(debug=True)
