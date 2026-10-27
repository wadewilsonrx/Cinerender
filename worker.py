import time, logging
from sqlalchemy import select
from db import SessionLocal, Job, init_db
from scraper import run_scrape

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
init_db()
logging.info("CineSubz metadata worker started")
while True:
    job_id = None
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.status == "queued").order_by(Job.created_at).with_for_update(skip_locked=True))
        if job:
            job.status = "claimed"
            job_id = job.id
            db.commit()
    if job_id:
        # run_scrape sets status=running and records progress
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            max_pages, max_details = job.max_pages, job.max_details
        logging.info("Running job %s", job_id)
        run_scrape(job_id, max_pages, max_details)
    else:
        time.sleep(3)
