import os
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from summarizer import summarize_text

# Load .env if present
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL") or f"sqlite:///{os.path.join(BASE_DIR, 'quickrecap.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25MB max upload

db = SQLAlchemy(app)

# Models
class Summary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_text = db.Column(db.Text, nullable=False)
    summary_text = db.Column(db.Text, nullable=False)
    method = db.Column(db.String(32), nullable=False)
    ratio = db.Column(db.Float, nullable=False, default=0.2)
    filename = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "summary_text": self.summary_text,
            "method": self.method,
            "ratio": self.ratio,
            "filename": self.filename,
            "created_at": self.created_at.isoformat()
        }

# Create DB if not exists
with app.app_context():
    db.create_all()

# Helpers
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    # serve stored uploaded files (optional)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    payload = request.get_json() or {}
    text = payload.get("text", "")
    method = payload.get("method", "auto")
    ratio = float(payload.get("ratio", 0.2))

    if not text.strip():
        return jsonify({"error": "No input text provided."}), 400

    start = time.time()
    summary, meta = summarize_text(text, method=method, ratio=ratio)
    elapsed = time.time() - start

    # persist summary
    s = Summary(original_text=text, summary_text=summary, method=meta.get("chosen_method", method), ratio=ratio)
    db.session.add(s)
    db.session.commit()

    return jsonify({"summary": summary, "meta": meta, "elapsed_seconds": elapsed, "id": s.id})

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    method = request.form.get("method", "auto")
    ratio = float(request.form.get("ratio", 0.2))
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    # to avoid overwrite, if exists append timestamp
    if os.path.exists(save_path):
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{int(time.time())}{ext}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    file.save(save_path)

    # Extract text based on extension
    ext = filename.rsplit(".", 1)[1].lower()
    extracted_text = ""
    try:
        if ext == "pdf":
            import pdfplumber
            with pdfplumber.open(save_path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
                extracted_text = "\n".join(pages).strip()
        elif ext == "docx":
            from docx import Document
            doc = Document(save_path)
            paragraphs = [p.text for p in doc.paragraphs]
            extracted_text = "\n".join(paragraphs).strip()
        elif ext == "txt":
            with open(save_path, "r", encoding="utf-8", errors="ignore") as fh:
                extracted_text = fh.read()
        else:
            extracted_text = ""
    except Exception as e:
        return jsonify({"error": f"Failed to extract text: {str(e)}"}), 500

    if not extracted_text:
        return jsonify({"error": "No extractable text found in file."}), 400

    start = time.time()
    summary, meta = summarize_text(extracted_text, method=method, ratio=ratio)
    elapsed = time.time() - start

    # persist
    s = Summary(original_text=extracted_text, summary_text=summary, method=meta.get("chosen_method", method), ratio=ratio, filename=filename)
    db.session.add(s)
    db.session.commit()

    return jsonify({"summary": summary, "meta": meta, "elapsed_seconds": elapsed, "id": s.id, "filename": filename})

@app.route("/api/history", methods=["GET"])
def api_history():
    # return last 10 summaries
    items = Summary.query.order_by(Summary.created_at.desc()).limit(10).all()
    return jsonify([i.to_dict() for i in items])

if __name__ == "__main__":
    app.run(debug=True)
