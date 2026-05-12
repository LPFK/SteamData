from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import User, SteamGame, SteamReview
from app import auth

PER_PAGE = 50

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def count_users(session: Session) -> int:
    return session.query(func.count(User.id)).scalar()


def count_games(session: Session) -> int:
    return session.query(func.count(SteamGame.app_id)).scalar()


def count_reviews(session: Session) -> int:
    return session.query(func.count(SteamReview.id)).scalar()


def top_developers(session: Session, n: int = 10) -> list[tuple[str, int]]:
    rows = (
        session.query(SteamGame.primary_developer, func.count(SteamGame.app_id))
        .filter(SteamGame.primary_developer.isnot(None))
        .group_by(SteamGame.primary_developer)
        .order_by(func.count(SteamGame.app_id).desc())
        .limit(n)
        .all()
    )
    return [(r[0], r[1]) for r in rows]


def top_genres(session: Session, n: int = 10) -> list[tuple[str, int]]:
    rows = (
        session.query(SteamGame.primary_genre, func.count(SteamGame.app_id))
        .filter(SteamGame.primary_genre.isnot(None))
        .group_by(SteamGame.primary_genre)
        .order_by(func.count(SteamGame.app_id).desc())
        .limit(n)
        .all()
    )
    return [(r[0], r[1]) for r in rows]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

_USER_SORTS = {
    "created_at desc": User.created_at.desc(),
    "username asc":    User.username.asc(),
    "last_login_at desc": User.last_login_at.desc(),
}


def search_users(
    session: Session,
    query: str = "",
    role_filter: str = "all",
    sort: str = "created_at desc",
    page: int = 0,
) -> tuple[list[User], int]:
    q = session.query(User)
    if query:
        q = q.filter(User.username.ilike(f"%{query}%"))
    if role_filter != "all":
        q = q.filter(User.role == role_filter)
    total = q.count()
    order = _USER_SORTS.get(sort, User.created_at.desc())
    rows = q.order_by(order).offset(page * PER_PAGE).limit(PER_PAGE).all()
    return rows, total


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def set_user_role(session: Session, user_id: int, new_role: str) -> None:
    user = session.get(User, user_id)
    if user:
        user.role = new_role
        session.commit()


def reset_user_password(session: Session, user_id: int, new_password: str) -> None:
    user = session.get(User, user_id)
    if user:
        user.password_hash = auth.hash_password(new_password)
        session.commit()


def delete_user(session: Session, user_id: int) -> None:
    user = session.get(User, user_id)
    if user:
        session.delete(user)
        session.commit()


def update_last_login(session: Session, user_id: int) -> None:
    user = session.get(User, user_id)
    if user:
        user.last_login_at = datetime.now(timezone.utc)
        session.commit()


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------

_GAME_SORTS = {
    "review_ratio desc":   SteamGame.review_ratio.desc(),
    "review_ratio asc":    SteamGame.review_ratio.asc(),
    "total_reviews desc":  SteamGame.total_reviews.desc(),
    "price desc":          SteamGame.price.desc(),
    "price asc":           SteamGame.price.asc(),
    "release_year desc":   SteamGame.release_year.desc(),
    "name asc":            SteamGame.name.asc(),
}


def search_games(
    session: Session,
    name: str = "",
    app_id: str = "",
    price_tiers: list[str] | None = None,
    is_indie: str = "all",
    year_min: int = 2010,
    year_max: int = 2024,
    genres: list[str] | None = None,
    sort: str = "review_ratio desc",
    page: int = 0,
) -> tuple[list[SteamGame], int]:
    q = session.query(SteamGame)
    if name:
        q = q.filter(SteamGame.name.ilike(f"%{name}%"))
    if app_id:
        q = q.filter(SteamGame.app_id == app_id.strip())
    if price_tiers:
        q = q.filter(SteamGame.price_tier.in_(price_tiers))
    if is_indie == "indie":
        q = q.filter(SteamGame.is_indie == True)
    elif is_indie == "non-indie":
        q = q.filter(SteamGame.is_indie == False)
    q = q.filter(
        SteamGame.release_year >= year_min,
        SteamGame.release_year <= year_max,
    )
    if genres:
        q = q.filter(SteamGame.primary_genre.in_(genres))
    total = q.count()
    order = _GAME_SORTS.get(sort, SteamGame.review_ratio.desc())
    rows = q.order_by(order).offset(page * PER_PAGE).limit(PER_PAGE).all()
    return rows, total


def get_game(session: Session, app_id: str) -> SteamGame | None:
    return session.get(SteamGame, app_id)


def distinct_genres(session: Session) -> list[str]:
    rows = (
        session.query(SteamGame.primary_genre)
        .filter(SteamGame.primary_genre.isnot(None))
        .distinct()
        .order_by(SteamGame.primary_genre)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def edit_game_field(session: Session, app_id: str, field: str, value) -> None:
    allowed = {"name", "primary_developer", "primary_genre", "price_tier", "is_indie"}
    if field not in allowed:
        raise ValueError(f"Field {field!r} is not editable via the admin dashboard")
    game = session.get(SteamGame, app_id)
    if game:
        setattr(game, field, value)
        session.commit()


def count_reviews_for_game(session: Session, app_id: str) -> int:
    return (
        session.query(func.count(SteamReview.id))
        .filter(SteamReview.app_id == app_id)
        .scalar()
    )


def delete_game(session: Session, app_id: str) -> int:
    review_count = count_reviews_for_game(session, app_id)
    session.query(SteamReview).filter(SteamReview.app_id == app_id).delete()
    game = session.get(SteamGame, app_id)
    if game:
        session.delete(game)
    session.commit()
    return review_count


def review_ratio_series(session: Session, app_id: str) -> list[tuple[int, float]]:
    rows = (
        session.query(SteamReview.review_score)
        .filter(SteamReview.app_id == app_id, SteamReview.review_score.isnot(None))
        .all()
    )
    if not rows:
        return []
    cumulative, result = 0, []
    for i, (score,) in enumerate(rows, 1):
        cumulative += 1 if score == 2 else 0
        if i % max(1, len(rows) // 100) == 0:
            result.append((i, cumulative / i))
    return result


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

def search_reviews(
    session: Session,
    app_id: str = "",
    review_score: str = "all",
    text_query: str = "",
    page: int = 0,
) -> tuple[list[SteamReview], int]:
    q = session.query(SteamReview)
    if app_id:
        q = q.filter(SteamReview.app_id == app_id.strip())
    if review_score == "positive":
        q = q.filter(SteamReview.review_score == 2)
    elif review_score == "negative":
        q = q.filter(SteamReview.review_score == 1)
    if text_query:
        q = q.filter(SteamReview.review_text.ilike(f"%{text_query}%"))
    total = q.count()
    rows = q.offset(page * PER_PAGE).limit(PER_PAGE).all()
    return rows, total
