from functools import wraps

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flasgger import Swagger
from marshmallow import ValidationError

from app.models import init_db, get_session, User, SteamGame
from app.auth import (
    hash_password,
    verify_password,
    encrypt_field,
    decrypt_field,
    create_token,
    verify_token,
)
from app.schemas import RegisterSchema, LoginSchema, GameQuerySchema
from app.errors import error_response

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

swagger = Swagger(app, template={
    "info": {
        "title": "datastory-steam API",
        "description": "Steam games analysis API. JWT required on protected routes. Use /apidocs to test every endpoint.",
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


# JWT decorator — reusable, keeps routes clean

def jwt_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth  = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        payload = verify_token(token)
        if not payload:
            return error_response("unauthorized", "Token invalide ou expiré", 401)
        request.user = payload
        return f(*args, **kwargs)
    return wrapper


# Parse and validate JSON body through a marshmallow schema

def parse_body(schema):
    data = request.get_json(silent=True)
    if data is None:
        return None, error_response("bad_request", "Request body must be valid JSON", 400)
    try:
        return schema.load(data), None
    except ValidationError as e:
        return None, error_response("validation_failed", e.messages, 422)


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


@app.post("/api/register")
def register():
    """
    Register a new user. Password hashed with bcrypt, email encrypted with Fernet.
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [username, email, password]
          properties:
            username: {type: string, minLength: 2, maxLength: 64}
            email:    {type: string, format: email}
            password: {type: string, minLength: 8}
    responses:
      201:
        description: user created
      409:
        description: username already taken
      422:
        description: validation failed
    """
    body, err = parse_body(RegisterSchema())
    if err:
        return err

    session = get_session()
    try:
        if session.query(User).filter_by(username=body["username"]).first():
            return error_response("conflict", "Username already taken", 409)

        user = User(
            username        = body["username"],
            email_encrypted = encrypt_field(body["email"]),
            password_hash   = hash_password(body["password"]),
            role            = "viewer",
        )
        session.add(user)
        session.commit()
        return jsonify({"id": user.id, "username": user.username}), 201
    finally:
        session.close()


@app.post("/api/login")
@limiter.limit("5 per minute")
def login():
    """
    Authenticate and receive a signed JWT.
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [username, password]
          properties:
            username: {type: string}
            password: {type: string}
    responses:
      200:
        description: JWT returned in body
      401:
        description: invalid credentials
      422:
        description: validation failed
      429:
        description: too many attempts
    """
    body, err = parse_body(LoginSchema())
    if err:
        return err

    session = get_session()
    try:
        user = session.query(User).filter_by(username=body["username"]).first()
        # same message whether user exists or not — avoids user enumeration
        if not user or not verify_password(body["password"], user.password_hash):
            return error_response("invalid_credentials", "Username ou mot de passe incorrect", 401)

        token = create_token(user_id=user.id, role=user.role)
        return jsonify({"token": token, "role": user.role}), 200
    finally:
        session.close()


@app.get("/api/me")
@jwt_required
def me():
    """
    Return the current authenticated user's profile with decrypted email.
    ---
    security:
      - Bearer: []
    responses:
      200:
        description: user profile
      401:
        description: not authenticated
      404:
        description: user not found
    """
    session = get_session()
    try:
        user = session.query(User).filter_by(id=int(request.user["sub"])).first()
        if not user:
            return error_response("not_found", "User not found", 404)
        return jsonify({
            "id":       user.id,
            "username": user.username,
            "email":    decrypt_field(user.email_encrypted),
            "role":     user.role,
        })
    finally:
        session.close()


@app.get("/api/data")
@jwt_required
def data():
    """
    Query games with optional filters. Paginated via limit and offset.
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
      - {name: offset,     in: query, type: integer, default: 0}
    responses:
      200:
        description: paginated list of games
      401:
        description: not authenticated
      422:
        description: validation failed
    """
    try:
        params = GameQuerySchema().load(request.args)
    except ValidationError as e:
        return error_response("validation_failed", e.messages, 422)

    session = get_session()
    try:
        q = session.query(SteamGame)

        if params["genre"]:
            q = q.filter(SteamGame.primary_genre.ilike(f"%{params['genre']}%"))
        if params["price_tier"]:
            q = q.filter(SteamGame.price_tier == params["price_tier"])
        if params["is_indie"] is not None:
            q = q.filter(SteamGame.is_indie == params["is_indie"])
        if params["year_min"]:
            q = q.filter(SteamGame.release_year >= params["year_min"])
        if params["year_max"]:
            q = q.filter(SteamGame.release_year <= params["year_max"])

        total = q.count()
        rows  = q.offset(params["offset"]).limit(params["limit"]).all()

        return jsonify({
            "total":  total,
            "limit":  params["limit"],
            "offset": params["offset"],
            "results": [{
                "app_id":                   r.app_id,
                "name":                     r.name,
                "release_year":             r.release_year,
                "price":                    r.price,
                "price_tier":               r.price_tier,
                "is_indie":                 r.is_indie,
                "primary_genre":            r.primary_genre,
                "review_ratio":             r.review_ratio,
                "total_reviews":            r.total_reviews,
                "metacritic_score":         r.metacritic_score,
                "average_playtime_forever": r.average_playtime_forever,
            } for r in rows],
        })
    finally:
        session.close()


@app.get("/api/data/<app_id>")
@jwt_required
def data_detail(app_id: str):
    """
    Full detail for one game by app_id.
    ---
    security:
      - Bearer: []
    parameters:
      - {name: app_id, in: path, type: string, required: true}
    responses:
      200:
        description: game detail
      401:
        description: not authenticated
      404:
        description: game not found
    """
    session = get_session()
    try:
        game = session.query(SteamGame).filter_by(app_id=app_id).first()
        if not game:
            return error_response("not_found", f"Game {app_id} not found", 404)

        return jsonify({
            "app_id":                   game.app_id,
            "name":                     game.name,
            "release_year":             game.release_year,
            "price":                    game.price,
            "price_tier":               game.price_tier,
            "is_free":                  game.is_free,
            "required_age":             game.required_age,
            "positive":                 game.positive,
            "negative":                 game.negative,
            "review_ratio":             game.review_ratio,
            "total_reviews":            game.total_reviews,
            "metacritic_score":         game.metacritic_score,
            "recommendations":          game.recommendations,
            "achievements":             game.achievements,
            "average_playtime_forever": game.average_playtime_forever,
            "median_playtime_forever":  game.median_playtime_forever,
            "peak_ccu":                 game.peak_ccu,
            "estimated_owners_min":     game.estimated_owners_min,
            "estimated_owners_max":     game.estimated_owners_max,
            "primary_genre":            game.primary_genre,
            "is_indie":                 game.is_indie,
            "primary_developer":        game.primary_developer,
            "windows":                  game.windows,
            "mac":                      game.mac,
            "linux":                    game.linux,
            "dlc_count":                game.dlc_count,
        })
    finally:
        session.close()


@app.get("/api/insights")
@jwt_required
def insights():
    """
    Aggregated stats answering the core question: do indie games review better than non-indie?
    Returns genre breakdown, price tier breakdown, and indie vs non-indie comparison.
    ---
    security:
      - Bearer: []
    responses:
      200:
        description: aggregated insights across all three dimensions
      401:
        description: not authenticated
    """
    from sqlalchemy import func

    session = get_session()
    try:
        genres = (
            session.query(
                SteamGame.primary_genre,
                func.count(SteamGame.app_id).label("game_count"),
                func.avg(SteamGame.review_ratio).label("avg_review_ratio"),
                func.avg(SteamGame.price).label("avg_price"),
            )
            .filter(SteamGame.primary_genre.isnot(None))
            .group_by(SteamGame.primary_genre)
            .order_by(func.count(SteamGame.app_id).desc())
            .limit(20)
            .all()
        )

        price_tiers = (
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

        indie_comparison = (
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
                SteamGame.total_reviews >= 10,
            )
            .group_by(SteamGame.is_indie, SteamGame.price_tier)
            .all()
        )

        return jsonify({
            "genres": [{
                "genre":            r.primary_genre,
                "game_count":       r.game_count,
                "avg_review_ratio": round(r.avg_review_ratio, 4) if r.avg_review_ratio else None,
                "avg_price":        round(r.avg_price, 2) if r.avg_price else None,
            } for r in genres],

            "price_tiers": [{
                "price_tier":       r.price_tier,
                "game_count":       r.game_count,
                "avg_review_ratio": round(r.avg_review_ratio, 4) if r.avg_review_ratio else None,
                "avg_playtime_min": round(r.avg_playtime_min, 0) if r.avg_playtime_min else None,
            } for r in price_tiers],

            "indie_vs_non_indie": [{
                "is_indie":         r.is_indie,
                "price_tier":       r.price_tier,
                "game_count":       r.game_count,
                "avg_review_ratio": round(r.avg_review_ratio, 4) if r.avg_review_ratio else None,
                "avg_price":        round(r.avg_price, 2) if r.avg_price else None,
                "avg_playtime_min": round(r.avg_playtime_min, 0) if r.avg_playtime_min else None,
            } for r in indie_comparison],
        })
    finally:
        session.close()


@app.errorhandler(429)
def rate_limit_handler(e):
    return error_response("rate_limited", "Trop de tentatives, réessayez plus tard", 429)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
