import os, re, json, time, urllib.robotparser
from urllib.parse import urljoin, urlparse, urldefrag
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from sqlalchemy import select
from db import SessionLocal, Movie, PublishedLink

BASE = os.getenv("SITE_BASE_URL", "https://cinesubz.net").rstrip("/")
HOST = urlparse(BASE).netloc.lower()
UA = os.getenv("USER_AGENT", "CineSubzMetadataResearchBot/1.0 (contact: replace-with-your-email@example.com)")
DELAY = max(2.0, float(os.getenv("REQUEST_DELAY_SECONDS", "3")))
TIMEOUT = 20
session_http = requests.Session()
session_http.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})

def allowed_by_robots(url):
    """Fail closed if robots.txt cannot be read; never bypass a disallow rule."""
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(urljoin(BASE + "/", "robots.txt"))
    try:
        rp.read()
        return rp.can_fetch(UA, url)
    except Exception:
        return False

def get_soup(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != HOST:
        raise ValueError("Only same-site pages are fetched.")
    if not allowed_by_robots(url):
        raise PermissionError(f"robots.txt does not permit fetching: {url}")
    time.sleep(DELAY)
    response = session_http.get(url, timeout=TIMEOUT, allow_redirects=False)
    if response.status_code in (301, 302, 303, 307, 308):
        raise RuntimeError("Redirect encountered; redirects are not followed by this scraper.")
    response.raise_for_status()
    if "text/html" not in response.headers.get("Content-Type", "").lower():
        raise ValueError("Not an HTML page.")
    return BeautifulSoup(response.text, "html.parser")

def clean_url(href, base_url):
    if not href:
        return ""
    url = urldefrag(urljoin(base_url, href.strip()))[0]
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return ""
    return url[:4096]

def same_site(url):
    return urlparse(url).netloc.lower() == HOST

def is_movie_page(url, anchor_text=""):
    path = urlparse(url).path.lower()
    if not same_site(url) or path in ("/", ""):
        return False
    if any(x in path for x in ("/category/", "/tag/", "/page/", "/genre/", "/language/", "/author/", "/wp-", "/feed")):
        return False
    if re.search(r"\.(jpg|jpeg|png|webp|gif|pdf|zip|srt)$", path):
        return False
    return len(path.strip("/")) > 3

def parse_catalogue_links(soup, page_url):
    found = []
    for a in soup.select("a[href]"):
        url = clean_url(a.get("href"), page_url)
        label = " ".join(a.get_text(" ", strip=True).split())
        if url and is_movie_page(url, label):
            # Avoid collecting nav links; accept anchors whose title text resembles a catalogue item.
            parent_text = " ".join(a.parent.get_text(" ", strip=True).split()) if a.parent else label
            if label and (re.search(r"\b(19|20)\d{2}\b", parent_text) or len(label) > 8):
                found.append((url, label))
    return list(dict.fromkeys(found))

def next_page_url(soup, current_url):
    candidates = []
    for a in soup.select("a[href]"):
        text = " ".join(a.get_text(" ", strip=True).split()).lower()
        rel = " ".join(a.get("rel", [])).lower()
        href = clean_url(a.get("href"), current_url)
        if href and same_site(href) and (text in {"next", "next »", "older posts", "→", "›"} or "next" in rel):
            candidates.append(href)
    # WordPress-like pagination fallback.
    if not candidates:
        for a in soup.select("a[href]"):
            href = clean_url(a.get("href"), current_url)
            if href and same_site(href) and re.search(r"/page/\d+/?$", urlparse(href).path):
                candidates.append(href)
    return candidates[0] if candidates else ""

def parse_movie(soup, movie_url, title_hint=""):
    title = ""
    for selector in ("h1", "article h2", ".entry-title", ".post-title"):
        node = soup.select_one(selector)
        if node and node.get_text(" ", strip=True):
            title = node.get_text(" ", strip=True)
            break
    title = title or title_hint or urlparse(movie_url).path.strip("/").replace("-", " ")
    text = " ".join(soup.get_text(" ", strip=True).split())
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", title + " " + text[:5000])
    rating_match = re.search(r"(?:IMDb|IMDB|★|Rating)[^\d]{0,15}(\d(?:\.\d)?(?:/10)?)", text, re.I)
    quality_match = re.search(r"\b(4K|2160p|1080p|720p|480p|WEB-DL|WEBRip|BluRay|HDRip)\b", text, re.I)
    description = ""
    meta_desc = soup.select_one('meta[name="description"]')
    if meta_desc:
        description = (meta_desc.get("content") or "")[:5000]
    if not description:
        for selector in (".entry-content", "article"):
            node = soup.select_one(selector)
            if node:
                description = node.get_text(" ", strip=True)[:5000]
                break
    poster = ""
    og = soup.select_one('meta[property="og:image"]')
    if og:
        poster = clean_url(og.get("content"), movie_url)
    if not poster:
        img = soup.select_one("article img[src], .entry-content img[src], img.wp-post-image")
        if img:
            poster = clean_url(img.get("src"), movie_url)
    metadata = {}
    for meta in soup.select("meta[property^='og:'], meta[name='twitter:']"):
        k = meta.get("property") or meta.get("name")
        v = meta.get("content")
        if k and v:
            metadata[k] = v[:2000]
    links = []
    seen = set()
    keywords = ("download", "google drive", "mega", "mediafire", "telegram", "gofile", "direct link", "server", "watch online", "download link")
    for a in soup.select("a[href]"):
        href = clean_url(a.get("href"), movie_url)
        label = " ".join(a.get_text(" ", strip=True).split())[:1000]
        if not href or href in seen:
            continue
        # Store links explicitly presented as download/watch/server links; do not visit them.
        context = (label + " " + " ".join(a.parent.get_text(" ", strip=True).split()[:20])).lower() if a.parent else label.lower()
        if any(k in context for k in keywords):
            links.append((label or "Published link", href))
            seen.add(href)
    return {
        "url": movie_url, "title": title[:1000], "year": year_match.group(1) if year_match else "",
        "rating": rating_match.group(1) if rating_match else "",
        "quality": quality_match.group(1) if quality_match else "",
        "poster_url": poster, "description": description,
        "metadata_json": json.dumps(metadata, ensure_ascii=False)
    }, links

def run_scrape(job_id, max_pages, max_details):
    with SessionLocal() as db:
        from db import Job
        job = db.get(Job, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()
    try:
        catalog_url = BASE + "/"
        seen_pages, candidates = set(), []
        for _ in range(max(1, max_pages)):
            if not catalog_url or catalog_url in seen_pages:
                break
            seen_pages.add(catalog_url)
            soup = get_soup(catalog_url)
            candidates.extend(parse_catalogue_links(soup, catalog_url))
            next_url = next_page_url(soup, catalog_url)
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                job.pages_seen += 1
                db.commit()
            catalog_url = next_url
            if not catalog_url:
                break
        # Unique catalogue URLs, and don't re-fetch records already in DB during incremental runs.
        unique = []
        seen = set()
        for u, title in candidates:
            if u not in seen:
                unique.append((u, title)); seen.add(u)
        processed = 0
        for movie_url, hint in unique:
            if processed >= max_details:
                break
            with SessionLocal() as db:
                existing = db.scalar(select(Movie).where(Movie.url == movie_url))
            if existing:
                continue
            soup = get_soup(movie_url)
            data, links = parse_movie(soup, movie_url, hint)
            with SessionLocal() as db:
                movie = Movie(**data)
                db.add(movie)
                db.flush()
                for label, href in links:
                    db.add(PublishedLink(movie_url=movie_url, label=label, url=href, host=urlparse(href).netloc.lower()))
                job = db.get(Job, job_id)
                job.movies_seen += 1
                job.links_seen += len(links)
                db.commit()
            processed += 1
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.status = "completed"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"[:4000]
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
