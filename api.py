import os
from functools import wraps

from flask import Flask, jsonify, request, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flasgger import Swagger
from pydantic import BaseModel, EmailStr, field_validator, ValidationError

from app.models import init_db, get_session, User, SteamGame, SteamReview
from app.auth import (
    hash_password,
    verify_password,
    encrypt_field,
    decrypt_field,
    create_token,
    verify_token,
)

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],  # no global limit i choose to apply limits per route
    storage_uri="memory://",
)

swagger = Swagger(app, template={
    "info": {
        "title": "datastory-steam API",
        "description": "Steam games analysis API. JWT required on protected routes.",
        "version": "1.0.0",
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Format: Bearer <token>",
        }
    },
})


# Pydantic schemas for request validation

class RegisterInput(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v

    @field_validator("username")
    @classmethod
    def username_clean(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("username must be at least 2 characters")
        return v


class LoginInput(BaseModel):
    username: str
    password: str


class GameFilterInput(BaseModel):
    genre: str | None = None
    price_tier: str | None = None     # free, budget, mid or premium
    is_indie: bool | None = None
    year_min: int | None = None
    year_max: int | None = None
    limit: int = 50

    @field_validator("limit")
    @classmethod
    def limit_range(cls, v: int) -> int:
        if v < 1 or v > 200:
            raise ValueError("limit must be between 1 and 200")
        return v


# Auth decorator for protected routes

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "missing or malformed Authorization header"}), 401
        token = auth_header.removeprefix("Bearer ").strip()
        payload = verify_token(token)
        if payload is None:
            return jsonify({"error": "invalid or expired token"}), 401
        g.current_user = payload
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        if g.current_user.get("role") != "admin":
            return jsonify({"error": "admin role required"}), 403
        return f(*args, **kwargs)
    return decorated


# Helper to parse and validate JSON body via Pydantic

def parse_body(schema_class):
    data = request.get_json(silent=True)
    if data is None:
        return None, jsonify({"error": "request body must be JSON"}), 400
    try:
        return schema_class(**data), None, None
    except ValidationError as e:
        errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
        return None, jsonify({"error": "validation failed", "details": errors}), 422


# Routes

@app.get("/health")
def health():
    """
    Health check.
    ---
    responses:
      200:
        description: API is running
    """
    return jsonify({"status": "ok"})


@app.post("/register")
def register():
    """
    Register a new user. Password is bcrypt-hashed, email is Fernet-encrypted.
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            username: {type: string}
            email: {type: string}
            password: {type: string, minLength: 8}
    responses:
      201:
        description: user created
      409:
        description: username already taken
      422:
        description: validation error
    """
    body, err_response, err_code = parse_body(RegisterInput)
    if err_response:
        return err_response, err_code

    session = get_session()
    try:
        if session.query(User).filter_by(username=body.username).first():
            return jsonify({"error": "username already taken"}), 409

        user = User(
            username        = body.username,
            email_encrypted = encrypt_field(body.email),
            password_hash   = hash_password(body.password),
            role            = "viewer",
        )
        session.add(user)
        session.commit()
        return jsonify({"id": user.id, "username": user.username}), 201
    finally:
        session.close()


@app.post("/login")
@limiter.limit("10 per minute")  # rate limit on login only
def login():
    """
    Authenticate and receive a signed JWT.
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            username: {type: string}
            password: {type: string}
    responses:
      200:
        description: authentication successful, returns JWT
      401:
        description: invalid credentials
      422:
        description: validation error
    """
    body, err_response, err_code = parse_body(LoginInput)
    if err_response:
        return err_response, err_code

    session = get_session()
    try:
        user = session.query(User).filter_by(username=body.username).first()
        # same error message whether user exists or not — avoids user enumeration
        if not user or not verify_password(body.password, user.password_hash):
            return jsonify({"error": "invalid credentials"}), 401

        token = create_token(user_id=user.id, role=user.role)
        return jsonify({"token": token, "role": user.role}), 200
    finally:
        session.close()


@app.get("/me")
@require_auth
def me():
    """
    Return the current authenticated user's profile.
    ---
    security:
      - Bearer: []
    responses:
      200:
        description: user profile with decrypted email
      401:
        description: not authenticated
    """
    session = get_session()
    try:
        user = session.query(User).filter_by(id=g.current_user["sub"]).first()
        if not user:
            return jsonify({"error": "user not found"}), 404
        return jsonify({
            "id":       user.id,
            "username": user.username,
            "email":    decrypt_field(user.email_encrypted),
            "role":     user.role,
        })
    finally:
        session.close()


@app.get("/games")
@require_auth
def games():
    """
    Query games from dataset A with optional filters.
    ---
    security:
      - Bearer: []
    parameters:
      - {name: genre,      in: query, type: string}
      - {name: price_tier, in: query, type: string, enum: [free, budget, mid, premium]}
      - {name: is_indie,   in: query, type: boolean}
      - {name: year_min,   in: query, type: integer}
      - {name: year_max,   in: query, type: integer}
      - {name: limit,      in: query, type: integer, default: 50}
    responses:
      200:
        description: list of games
      422:
        description: validation error
    """
    try:
        filters = GameFilterInput(
            genre      = request.args.get("genre"),
            price_tier = request.args.get("price_tier"),
            is_indie   = request.args.get("is_indie"),
            year_min   = request.args.get("year_min"),
            year_max   = request.args.get("year_max"),
            limit      = int(request.args.get("limit", 50)),
        )
    except ValidationError as e:
        errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
        return jsonify({"error": "validation failed", "details": errors}), 422

    session = get_session()
    try:
        q = session.query(SteamGame)

        if filters.genre:
            q = q.filter(SteamGame.primary_genre.ilike(f"%{filters.genre}%"))
        if filters.price_tier:
            q = q.filter(SteamGame.price_tier == filters.price_tier)
        if filters.is_indie is not None:
            q = q.filter(SteamGame.is_indie == filters.is_indie)
        if filters.year_min:
            q = q.filter(SteamGame.release_year >= filters.year_min)
        if filters.year_max:
            q = q.filter(SteamGame.release_year <= filters.year_max)

        rows = q.limit(filters.limit).all()

        return jsonify([{
            "app_id":        r.app_id,
            "name":          r.name,
            "release_year":  r.release_year,
            "price":         r.price,
            "price_tier":    r.price_tier,
            "is_indie":      r.is_indie,
            "primary_genre": r.primary_genre,
            "review_ratio":  r.review_ratio,
            "total_reviews": r.total_reviews,
            "metacritic_score": r.metacritic_score,
            "average_playtime_forever": r.average_playtime_forever,
        } for r in rows])
    finally:
        session.close()


@app.get("/games/<app_id>")
@require_auth
def game_detail(app_id: str):
    """
    Get full details for a single game.
    ---
    security:
      - Bearer: []
    parameters:
      - {name: app_id, in: path, type: string, required: true}
    responses:
      200:
        description: game detail
      404:
        description: game not found
    """
    session = get_session()
    try:
        game = session.query(SteamGame).filter_by(app_id=app_id).first()
        if not game:
            return jsonify({"error": "game not found"}), 404

        return jsonify({
            "app_id":                    game.app_id,
            "name":                      game.name,
            "release_year":              game.release_year,
            "price":                     game.price,
            "price_tier":                game.price_tier,
            "is_free":                   game.is_free,
            "required_age":              game.required_age,
            "positive":                  game.positive,
            "negative":                  game.negative,
            "review_ratio":              game.review_ratio,
            "total_reviews":             game.total_reviews,
            "metacritic_score":          game.metacritic_score,
            "recommendations":           game.recommendations,
            "achievements":              game.achievements,
            "average_playtime_forever":  game.average_playtime_forever,
            "median_playtime_forever":   game.median_playtime_forever,
            "peak_ccu":                  game.peak_ccu,
            "estimated_owners_min":      game.estimated_owners_min,
            "estimated_owners_max":      game.estimated_owners_max,
            "primary_genre":             game.primary_genre,
            "is_indie":                  game.is_indie,
            "primary_developer":         game.primary_developer,
            "windows":                   game.windows,
            "mac":                       game.mac,
            "linux":                     game.linux,
            "dlc_count":                 game.dlc_count,
        })
    finally:
        session.close()


@app.get("/stats/genres")
@require_auth
def stats_genres():
    """
    Average review ratio and total games per genre.
    ---
    security:
      - Bearer: []
    responses:
      200:
        description: genre stats
    """
    from sqlalchemy import func

    session = get_session()
    try:
        rows = (
            session.query(
                SteamGame.primary_genre,
                func.count(SteamGame.app_id).label("game_count"),
                func.avg(SteamGame.review_ratio).label("avg_review_ratio"),
                func.avg(SteamGame.price).label("avg_price"),
            )
            .filter(SteamGame.primary_genre.isnot(None))
            .group_by(SteamGame.primary_genre)
            .order_by(func.count(SteamGame.app_id).desc())
            .all()
        )

        return jsonify([{
            "genre":            r.primary_genre,
            "game_count":       r.game_count,
            "avg_review_ratio": round(r.avg_review_ratio, 4) if r.avg_review_ratio else None,
            "avg_price":        round(r.avg_price, 2) if r.avg_price else None,
        } for r in rows])
    finally:
        session.close()


@app.get("/stats/price-tiers")
@require_auth
def stats_price_tiers():
    """
    Review ratio and game count broken down by price tier.
    ---
    security:
      - Bearer: []
    responses:
      200:
        description: price tier stats
    """
    from sqlalchemy import func

    session = get_session()
    try:
        rows = (
            session.query(
                SteamGame.price_tier,
                func.count(SteamGame.app_id).label("game_count"),
                func.avg(SteamGame.review_ratio).label("avg_review_ratio"),
                func.avg(SteamGame.average_playtime_forever).label("avg_playtime_min"),
            )
            .filter(SteamGame.price_tier.isnot(None))
            .group_by(SteamGame.price_tier)
            .all()
        )

        return jsonify([{
            "price_tier":       r.price_tier,
            "game_count":       r.game_count,
            "avg_review_ratio": round(r.avg_review_ratio, 4) if r.avg_review_ratio else None,
            "avg_playtime_min": round(r.avg_playtime_min, 0) if r.avg_playtime_min else None,
        } for r in rows])
    finally:
        session.close()


@app.get("/stats/indie-vs-aaa")
@require_auth
def stats_indie_vs_aaa():
    """
    Core question: compare review ratio between indie and non-indie games, by price tier and genre.
    ---
    security:
      - Bearer: []
    responses:
      200:
        description: indie vs AAA comparison stats
    """
    from sqlalchemy import func

    session = get_session()
    try:
        rows = (
            session.query(
                SteamGame.is_indie,
                SteamGame.price_tier,
                func.count(SteamGame.app_id).label("game_count"),
                func.avg(SteamGame.review_ratio).label("avg_review_ratio"),
                func.avg(SteamGame.price).label("avg_price"),
                func.avg(SteamGame.average_playtime_forever).label("avg_playtime_min"),
            )
            .filter(
                SteamGame.price_tier.isnot(None),
                SteamGame.review_ratio.isnot(None),
                SteamGame.total_reviews >= 10,  # filter out games with almost no reviews
            )
            .group_by(SteamGame.is_indie, SteamGame.price_tier)
            .all()
        )

        return jsonify([{
            "is_indie":         r.is_indie,
            "price_tier":       r.price_tier,
            "game_count":       r.game_count,
            "avg_review_ratio": round(r.avg_review_ratio, 4) if r.avg_review_ratio else None,
            "avg_price":        round(r.avg_price, 2) if r.avg_price else None,
            "avg_playtime_min": round(r.avg_playtime_min, 0) if r.avg_playtime_min else None,
        } for r in rows])
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
