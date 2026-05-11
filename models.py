from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String,
    Float, Boolean, DateTime, Text
)
from sqlalchemy.orm import DeclarativeBase, Session

DATABASE_URL = "sqlite:///datastory.db"
engine = create_engine(DATABASE_URL, echo=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True)
    username        = Column(String(64), unique=True, nullable=False)
    email_encrypted = Column(Text, nullable=False)        # stored encrypted via Fernet
    password_hash   = Column(String(128), nullable=False) # stored hashed via bcrypt
    role            = Column(String(16), default="viewer", nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"


class SteamGame(Base):
    # one row per game from dataset A (fronkongames, 122k+ games)
    __tablename__ = "steam_games"

    app_id                   = Column(String(16), primary_key=True)
    name                     = Column(String(256))
    release_year             = Column(Integer)       # extracted from release_date
    price                    = Column(Float)
    price_tier               = Column(String(16))    # free / budget / mid / premium
    is_free                  = Column(Boolean)
    required_age             = Column(Integer)
    positive                 = Column(Integer)
    negative                 = Column(Integer)
    review_ratio             = Column(Float)         # positive / (positive + negative)
    total_reviews            = Column(Integer)
    metacritic_score         = Column(Integer)
    recommendations          = Column(Integer)
    achievements             = Column(Integer)
    average_playtime_forever = Column(Integer)       # in minutes
    median_playtime_forever  = Column(Integer)
    peak_ccu                 = Column(Integer)
    estimated_owners_min     = Column(Integer)       # lower bound of "X - Y" range
    estimated_owners_max     = Column(Integer)
    primary_genre            = Column(String(64))    # first genre in the list
    is_indie                 = Column(Boolean)
    primary_developer        = Column(String(128))
    windows                  = Column(Boolean)
    mac                      = Column(Boolean)
    linux                    = Column(Boolean)
    dlc_count                = Column(Integer)

    def __repr__(self) -> str:
        return f"<SteamGame {self.app_id} | {self.name[:30]}>"


class SteamReview(Base):
    # one row per review from dataset B (290 games, ~1M reviews)
    __tablename__ = "steam_reviews"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    app_id      = Column(String(16))   # joins to SteamGame.app_id
    app_name    = Column(String(256))
    review_score = Column(Integer)     # typically 1 (negative) or 2 (positive) on Steam
    review_votes = Column(Integer)     # how many users found the review helpful
    review_text  = Column(Text)

    def __repr__(self) -> str:
        return f"<SteamReview app={self.app_id} score={self.review_score}>"


def init_db() -> None:
    Base.metadata.create_all(engine)
    print("[db] tables created")


def get_session() -> Session:
    return Session(engine)
