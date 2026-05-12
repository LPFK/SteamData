from pathlib import Path
import pandas as pd
from sqlalchemy.orm import Session

DATA_DIR  = Path(__file__).resolve().parents[1] / "data"
RAW_DIR   = DATA_DIR / "raw"

# expected filenames once downloaded from Kaggle
FILE_GAMES   = "games.csv"          # dataset A — fronkongames
FILE_REVIEWS = "reviews.csv"        # dataset B — mohamedtarek01234


def _parse_owners(value: str) -> tuple[int, int]:
    # estimated_owners comes as a string range like "20000 - 50000"
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
    # genres is stored as a comma-separated string like "Action,Indie,RPG"
    if pd.isna(genres) or genres == "":
        return "unknown"
    return str(genres).split(",")[0].strip()


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
    # The CSV header merges "Discount" and "DLC count" as one entry, causing a 1-column
    # shift from col 7 onward. Supply the correct 40 column names to fix the mapping.
    df = pd.read_csv(path, encoding="utf-8", skiprows=1, names=_GAMES_COLUMNS)
    print(f"[load] games    | {len(df):>7,} rows | {df.shape[1]} cols")
    return df


def load_reviews() -> pd.DataFrame:
    path = RAW_DIR / FILE_REVIEWS
    if not path.exists():
        raise FileNotFoundError(f"Missing: {path}. Download dataset B from Kaggle.")
    df = pd.read_csv(path, encoding="utf-8")
    print(f"[load] reviews  | {len(df):>7,} rows | {df.shape[1]} cols")
    return df


def clean_games(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # normalise all column names at once — strip whitespace, lowercase, spaces to underscores
    # this handles the full fronkongames schema: "Release date", "Peak CCU", "DLC count", etc.
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # app_id specifically used "AppID" before normalisation, now it's "appid" — rename to app_id
    if "appid" in df.columns:
        df = df.rename(columns={"appid": "app_id"})

    df["app_id"] = df["app_id"].astype(str)

    # extract year from release_date string (format varies: "Oct 5, 2017" or "2017-10-05")
    df["release_year"] = pd.to_datetime(
        df["release_date"], errors="coerce"
    ).dt.year.astype("Int64")

    # review ratio — guard against division by zero
    total = df["positive"] + df["negative"]
    df["total_reviews"] = total
    df["review_ratio"] = (df["positive"] / total.where(total > 0)).round(4)

    # price tier
    df["is_free"] = df["price"].fillna(0) == 0
    df["price_tier"] = df.apply(
        lambda r: _price_tier(r["price"], r["is_free"]), axis=1
    )

    # owners range — column is now "estimated_owners" after normalisation
    owners = df["estimated_owners"].apply(_parse_owners)
    df["estimated_owners_min"] = owners.apply(lambda x: x[0])
    df["estimated_owners_max"] = owners.apply(lambda x: x[1])

    # genre helpers
    df["primary_genre"] = df["genres"].apply(_primary_genre)
    df["is_indie"] = df["genres"].fillna("").str.contains("Indie", case=False)

    # primary developer (first in the list if multiple)
    df["primary_developer"] = (
        df["developers"].fillna("unknown")
                        .apply(lambda x: str(x).split(",")[0].strip())
    )

    # drop columns we don't need — all names are now normalised
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

    # normalise column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # make sure app_id is a string for joining
    if "app_id" in df.columns:
        df["app_id"] = df["app_id"].astype(str)

    # drop rows with no review score
    before = len(df)
    df = df.dropna(subset=["review_score"])
    print(f"[clean] reviews | {before - len(df):,} rows without score dropped")

    return df


def build_master() -> tuple[pd.DataFrame, pd.DataFrame]:
    # returns two DataFrames: games (full 122k) and reviews (290-game subset joined with game metadata)
    games   = clean_games(load_games())
    reviews = clean_reviews(load_reviews())

    # enrich reviews with game metadata for the 290-game analysis
    game_meta = games[["app_id", "price", "price_tier", "primary_genre",
                        "is_indie", "release_year", "review_ratio",
                        "total_reviews", "primary_developer"]]

    reviews_enriched = reviews.merge(game_meta, on="app_id", how="left")

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

    # reviews are large — insert in chunks to avoid memory issues
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
                app_name     = getattr(row, "app_name", None),
                review_score = getattr(row, "review_score", None),
                review_votes = getattr(row, "review_votes", None),
                review_text  = getattr(row, "review_text", None),
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
