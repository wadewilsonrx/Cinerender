import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, DateTime, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def utcnow():
    return datetime.now(timezone.utc)

def database_url():
    url = os.getenv("DATABASE_URL", "sqlite:///cinesubz_dev.db")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

engine = create_engine(database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Movie(Base):
    __tablename__ = "movies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(1000), default="")
    year: Mapped[str] = mapped_column(String(20), default="")
    rating: Mapped[str] = mapped_column(String(40), default="")
    quality: Mapped[str] = mapped_column(String(100), default="")
    poster_url: Mapped[str] = mapped_column(String(2048), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class PublishedLink(Base):
    __tablename__ = "published_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    movie_url: Mapped[str] = mapped_column(String(2048), index=True)
    label: Mapped[str] = mapped_column(String(1000), default="")
    url: Mapped[str] = mapped_column(String(4096))
    host: Mapped[str] = mapped_column(String(255), default="")
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("movie_url", "url", name="uq_movie_link"),)

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    mode: Mapped[str] = mapped_column(String(30), default="test")
    max_pages: Mapped[int] = mapped_column(Integer, default=3)
    max_details: Mapped[int] = mapped_column(Integer, default=10)
    pages_seen: Mapped[int] = mapped_column(Integer, default=0)
    movies_seen: Mapped[int] = mapped_column(Integer, default=0)
    links_seen: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

def init_db():
    Base.metadata.create_all(engine)
