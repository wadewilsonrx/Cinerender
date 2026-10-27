import os, csv, io, json, hmac
from functools import wraps
from flask import Flask, request, redirect, url_for, render_template, Response, session, flash
from sqlalchemy import select, desc, func
from db import SessionLocal, Movie, PublishedLink, Job, init_db

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.getenv("DASHBOARD_PASSWORD", "local-dev-change-me"))
init_db()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

@app.get("/health")
def health():
    return {"ok": True}

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        expected = os.getenv("DASHBOARD_PASSWORD", "")
        if not expected:
            flash("Set DASHBOARD_PASSWORD in the environment before using the dashboard.", "error")
        elif hmac.compare_digest(request.form.get("password", ""), expected):
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            flash("Incorrect password.", "error")
    return render_template("login.html")

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    with SessionLocal() as db:
        movie_count = db.scalar(select(func.count()).select_from(Movie)) or 0
        link_count = db.scalar(select(func.count()).select_from(PublishedLink)) or 0
        jobs = db.scalars(select(Job).order_by(desc(Job.id)).limit(10)).all()
        stmt = select(Movie).order_by(desc(Movie.id)).limit(100)
        if q:
            stmt = select(Movie).where(Movie.title.ilike(f"%{q}%")).order_by(desc(Movie.id)).limit(100)
        movies = db.scalars(stmt).all()
    return render_template("index.html", movies=movies, jobs=jobs, movie_count=movie_count, link_count=link_count, q=q)

@app.post("/jobs")
@login_required
def create_job():
    mode = request.form.get("mode", "test")
    if mode not in ("test", "full"):
        mode = "test"
    # Full mode is intentionally bounded per run; repeat jobs to continue safely.
    pages = 3 if mode == "test" else min(100, max(1, int(os.getenv("MAX_PAGES_PER_JOB", "3"))))
    details = 10 if mode == "test" else min(500, max(1, int(os.getenv("MAX_DETAILS_PER_JOB", "10"))))
    with SessionLocal() as db:
        active = db.scalar(select(Job).where(Job.status.in_(["queued", "claimed", "running"])))
        if active:
            flash(f"Job #{active.id} is already active.", "error")
        else:
            job = Job(status="queued", mode=mode, max_pages=pages, max_details=details)
            db.add(job); db.commit()
            flash(f"Created {mode} job #{job.id}. The background worker will start it.", "success")
    return redirect(url_for("index"))

@app.get("/export/<kind>")
@login_required
def export(kind):
    if kind not in ("csv", "json", "links.csv"):
        return "Unknown export type", 404
    with SessionLocal() as db:
        if kind == "links.csv":
            rows = db.scalars(select(PublishedLink).order_by(PublishedLink.id)).all()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["movie_url", "label", "published_url", "host", "scraped_at"])
            for r in rows:
                writer.writerow([r.movie_url, r.label, r.url, r.host, r.scraped_at.isoformat() if r.scraped_at else ""])
            return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=published_links.csv"})
        rows = db.scalars(select(Movie).order_by(Movie.id)).all()
        data = [{"url":r.url,"title":r.title,"year":r.year,"rating":r.rating,"quality":r.quality,"poster_url":r.poster_url,"description":r.description,"metadata":json.loads(r.metadata_json or "{}"),"scraped_at":r.scraped_at.isoformat() if r.scraped_at else ""} for r in rows]
        if kind == "json":
            return Response(json.dumps(data, ensure_ascii=False, indent=2), mimetype="application/json", headers={"Content-Disposition":"attachment; filename=movies.json"})
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["url","title","year","rating","quality","poster_url","description","metadata","scraped_at"])
        writer.writeheader()
        for row in data:
            row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False)
            writer.writerow(row)
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=movies.csv"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
