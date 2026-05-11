# datastory-steam

**Question:** Does price, genre, or studio size predict a game's review score on Steam and do indie games outperform AAA titles?

Datasets:
- A: [Steam Games Dataset](https://www.kaggle.com/datasets/fronkongames/steam-games-dataset) — 122k+ games, 40+ columns (fronkongames, Jan 2026)
- B: [Steam Reviews and Rankings](https://www.kaggle.com/datasets/mohamedtarek01234/steam-games-reviews-and-rankings) — ~1M reviews across 290 games


---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Generate secrets and paste into `.env`:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Data

Place the Kaggle CSVs in `data/raw/`:
- `games.csv` (dataset A)
- `reviews.csv` (dataset B)

Build the parquet files:
```bash
python -m app.data_processing
```

---

## TP morning

```bash
python tp_morning.py
```

---

## Two analysis granularities

| Scope | Source | Rows | Question |
|---|---|---|---|
| Global | games.parquet | 122k | Does price tier or genre correlate with review_ratio? |
| Deep | reviews_enriched.parquet | ~1M | Do reviews for indie games skew more positive than AAA? |

---

## Project structure

```
datastory-steam/
├── app/
│   ├── models.py          # User, SteamGame, SteamReview
│   ├── auth.py            # bcrypt, Fernet, JWT
│   ├── data_processing.py # load, clean, merge, seed
│   └── api.py             # Flask API (day 1 afternoon)
├── data/
│   ├── raw/               # Kaggle CSVs (gitignored)
│   ├── games.parquet
│   └── reviews_enriched.parquet
├── tests/
├── .env
├── .env.example
└── tp_morning.py
```

---

## Key derived columns

| Column | Source | Notes |
|---|---|---|
| review_ratio | games | positive / (positive + negative) |
| price_tier | games | free / budget / mid / premium |
| is_indie | games | True if "Indie" in genres |
| primary_genre | games | first genre in the list |
| release_year | games | extracted from release_date |
| estimated_owners_min/max | games | parsed from "X - Y" range string |
