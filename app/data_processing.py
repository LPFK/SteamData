from pathlib import Path
import pandas as pd
from sqlalchemy.orm import Session

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RAW_DIR  = DATA_DIR / "raw"

FILE_GAMES   = "games.csv"
FILE_REVIEWS = "steam_game_reviews.csv"


def _parse_owners(value: str) -> tuple[int, int]:
    try:
        parts = str(value).replace(",", "").split(" - ")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 0, 0


def _price_tier(price: float, is_free: bool) -> str:
    if is_free or price == 0:
        return "free"
    if price < 5:
        return "budget"
    if price <= 20:
        return "mid"
    return "premium"


def _primary_genre(genres: str) -> str:
    if pd.isna(genres) or genres == "":
        return "unknown"
    return str(genres).split(",")[0].strip()


# The raw CSV header merges "Discount" and "DLC count" into one token, shifting every
# subsequent column by one. Supplying the correct 40 names fixes the mapping.
_GAMES_COLUMNS = [
    "AppID", "Name", "Release date", "Estimated owners", "Peak CCU",
    "Required age", "Price", "Discount", "DLC count", "About the game",
    "Supported languages", "Full audio languages", "Reviews", "Header image",
    "Website", "Support url", "Support email", "Windows", "Mac", "Linux",
    "Metacritic score", "Metacritic url", "User score", "Positive", "Negative",
    "Score rank", "Achievements", "Recommendations", "Notes",
    "Average playtime forever", "Average playtime two weeks",
    "Median playtime forever", "Median playtime two weeks",
    "Developers", "Publishers", "Categories", "Genres", "Tags",
    "Screenshots", "Movies",
]


def load_games() -> pd.DataFrame:
    path = RAW_DIR / FILE_GAMES
    if not path.exists():
        raise FileNotFoundError(f"Missing: {path}. Download dataset A from Kaggle.")
    df = pd.read_csv(path, encoding="utf-8", skiprows=1, names=_GAMES_COLUMNS)
    print(f"[load] games    | {len(df):>7,} rows | {df.shape[1]} cols")
    return df


def load_reviews() -> pd.DataFrame:
    path = RAW_DIR / FILE_REVIEWS
    if not path.exists():
        raise FileNotFoundError(f"Missing: {path}. Download dataset B from Kaggle.")
    df = pd.read_csv(path, encoding="utf-8", low_memory=False)
    print(f"[load] reviews  | {len(df):>7,} rows | {df.shape[1]} cols")
    return df


def clean_games(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    if "appid" in df.columns:
        df = df.rename(columns={"appid": "app_id"})

    df["app_id"] = df["app_id"].astype(str)

    df["release_year"] = pd.to_datetime(
        df["release_date"], errors="coerce"
    ).dt.year.astype("Int64")

    total = df["positive"] + df["negative"]
    df["total_reviews"] = total
    df["review_ratio"] = (df["positive"] / total.where(total > 0)).round(4)

    df["is_free"] = df["price"].fillna(0) == 0
    df["price_tier"] = df.apply(
        lambda r: _price_tier(r["price"], r["is_free"]), axis=1
    )

    owners = df["estimated_owners"].apply(_parse_owners)
    df["estimated_owners_min"] = owners.apply(lambda x: x[0])
    df["estimated_owners_max"] = owners.apply(lambda x: x[1])

    df["primary_genre"] = df["genres"].apply(_primary_genre)
    df["is_indie"] = df["genres"].fillna("").str.contains("Indie", case=False)

    df["primary_developer"] = (
        df["developers"].fillna("unknown")
                        .apply(lambda x: str(x).split(",")[0].strip())
    )

    drop_cols = [
        "detailed_description", "short_description", "about_the_game",
        "reviews", "header_image", "website", "support_url", "support_email",
        "screenshots", "movies", "notes", "packages",
        "supported_languages", "full_audio_languages",
        "metacritic_url", "score_rank",
    ]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    print(f"[clean] games   | {len(df):,} rows kept")
    return df


def clean_reviews(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    before = len(df)
    df = df.dropna(subset=["recommendation"])
    print(f"[clean] reviews | {before - len(df):,} rows without recommendation dropped")

    # convert text recommendation to numeric score matching the SteamReview model convention
    df["review_score"] = df["recommendation"].map({"Recommended": 2, "Not Recommended": 1})

    # normalise join key for case-insensitive matching against games.name
    df["name_key"] = df["game_name"].str.strip().str.lower()

    # helpful votes may be strings like "1,152" — coerce to int
    df["helpful"] = pd.to_numeric(
        df["helpful"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    ).fillna(0).astype(int)

    df["funny"] = pd.to_numeric(
        df["funny"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    ).fillna(0).astype(int)

    return df


def build_master() -> tuple[pd.DataFrame, pd.DataFrame]:
    games   = clean_games(load_games())
    reviews = clean_reviews(load_reviews())

    game_meta = games[["app_id", "name", "price", "price_tier", "primary_genre",
                        "is_indie", "release_year", "review_ratio",
                        "total_reviews", "primary_developer"]].copy()
    game_meta["name_key"] = game_meta["name"].str.strip().str.lower()
    # keep one row per name — the entry with the most reviews is most likely the canonical release
    game_meta = game_meta.sort_values("total_reviews", ascending=False).drop_duplicates("name_key")

    reviews_enriched = reviews.merge(game_meta, on="name_key", how="left")

    print(f"[merge] reviews enriched | {len(reviews_enriched):,} rows | "
          f"{reviews_enriched['app_id'].nunique()} unique games")

    return games, reviews_enriched


def save_master(games: pd.DataFrame, reviews: pd.DataFrame) -> None:
    games.to_parquet(DATA_DIR / "games.parquet", index=False)
    reviews.to_parquet(DATA_DIR / "reviews_enriched.parquet", index=False)
    print(f"[save] games.parquet + reviews_enriched.parquet -> {DATA_DIR}")


def load_master() -> tuple[pd.DataFrame, pd.DataFrame]:
    gp = DATA_DIR / "games.parquet"
    rp = DATA_DIR / "reviews_enriched.parquet"
    if not gp.exists() or not rp.exists():
        raise FileNotFoundError("Parquet files not found. Run build_master() first.")
    return pd.read_parquet(gp), pd.read_parquet(rp)


def seed_db(session: Session) -> None:
    from app.models import SteamGame, SteamReview

    games, reviews = load_master()

    existing_games = {r.app_id for r in session.query(SteamGame.app_id).all()}

    game_rows = [
        SteamGame(
            app_id                   = str(row.app_id),
            name                     = getattr(row, "name", None),
            release_year             = getattr(row, "release_year", None),
            price                    = getattr(row, "price", None),
            price_tier               = getattr(row, "price_tier", None),
            is_free                  = bool(getattr(row, "is_free", False)),
            required_age             = getattr(row, "required_age", None),
            positive                 = getattr(row, "positive", None),
            negative                 = getattr(row, "negative", None),
            review_ratio             = getattr(row, "review_ratio", None),
            total_reviews            = getattr(row, "total_reviews", None),
            metacritic_score         = getattr(row, "metacritic_score", None),
            recommendations          = getattr(row, "recommendations", None),
            achievements             = getattr(row, "achievements", None),
            average_playtime_forever = getattr(row, "average_playtime_forever", None),
            median_playtime_forever  = getattr(row, "median_playtime_forever", None),
            peak_ccu                 = getattr(row, "peak_ccu", None),
            estimated_owners_min     = getattr(row, "estimated_owners_min", None),
            estimated_owners_max     = getattr(row, "estimated_owners_max", None),
            primary_genre            = getattr(row, "primary_genre", None),
            is_indie                 = bool(getattr(row, "is_indie", False)),
            primary_developer        = getattr(row, "primary_developer", None),
            windows                  = bool(getattr(row, "windows", False)),
            mac                      = bool(getattr(row, "mac", False)),
            linux                    = bool(getattr(row, "linux", False)),
            dlc_count                = getattr(row, "dlc_count", None),
        )
        for row in games.itertuples()
        if str(row.app_id) not in existing_games
    ]

    session.bulk_save_objects(game_rows)
    session.commit()
    print(f"[seed] {len(game_rows):,} games inserted")

    # reviews are large — chunked to avoid memory pressure during bulk insert
    chunk_size = 10_000
    review_chunks = [
        reviews.iloc[i : i + chunk_size]
        for i in range(0, len(reviews), chunk_size)
    ]

    total_inserted = 0
    for chunk in review_chunks:
        review_rows = [
            SteamReview(
                app_id       = str(getattr(row, "app_id", "")),
                app_name     = getattr(row, "game_name", None),
                review_score = getattr(row, "review_score", None),
                review_votes = getattr(row, "helpful", None),
                review_text  = getattr(row, "review", None),
            )
            for row in chunk.itertuples()
        ]
        session.bulk_save_objects(review_rows)
        session.commit()
        total_inserted += len(review_rows)

    print(f"[seed] {total_inserted:,} reviews inserted")


if __name__ == "__main__":
    games, reviews = build_master()
    save_master(games, reviews)
    print(games.dtypes)
    print(reviews.head(3))
