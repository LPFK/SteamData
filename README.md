# datastory-steam

Formation projet Semaine 2 (May 2026).

**Central question:** Does price, genre, or studio size predict a game's review score on Steam, and do indie games outperform AAA titles?

---

## What's in the repo

| File | What it does |
|---|---|
| `dashboard.py` | Streamlit visual dashboard — run this to see the charts |
| `app/api.py` | Flask REST API with JWT auth and Swagger UI |
| `app/data_processing.py` | Loads and cleans the raw CSVs, builds the parquet files |
| `app/models.py` | SQLAlchemy database models |
| `app/auth.py` | bcrypt, Fernet, and JWT security logic |
| `tp_morning.py` | Morning TP deliverable — DB init and security demo |

---

## Quickstart

### 1. Get the data

Download both datasets from Kaggle and place the CSV files inside `data/raw/`:

- [Steam Games Dataset](https://www.kaggle.com/datasets/fronkongames/steam-games-dataset) — save as `data/raw/games.csv`
- [Steam Reviews and Rankings](https://www.kaggle.com/datasets/mohamedtarek01234/steam-games-reviews-and-rankings) — save as `data/raw/reviews.csv`

### 2. Create the virtual environment

```bash
python -m venv .venv

# Mac / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up secrets

```bash
cp .env.example .env
```

Then open `.env` and replace the placeholder values. Run these two commands to generate real keys:

```bash
# generates FERNET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# generates JWT_SECRET
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Build the data files

This reads the raw CSVs and produces two parquet files used by the dashboard and API:

```bash
python -m app.data_processing
```

Expected output:
```
[load] games    | 122,611 rows | 40 cols
[clean] games   | 122,611 rows kept
[save] games.parquet + reviews_enriched.parquet -> data/
```

---

## Running the dashboard

```bash
streamlit run dashboard.py
```

Opens at **http://localhost:8501**. Shows six charts covering the three core questions and the main hypotheses.

---

## Running the API

```bash
python -m app.api
```

Runs at **http://localhost:5000**. Interactive Swagger UI at **http://localhost:5000/apidocs**.

Quick test sequence:

```bash
# create a user
curl -X POST http://localhost:5000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "password123"}'

# log in and copy the token from the response
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "password123"}'

# query games (replace <token> with the value from the login response)
curl http://localhost:5000/api/data \
  -H "Authorization: Bearer <token>"
```

---

## Running the tests

```bash
pytest tests/
```

---

## Project structure

```
datastory-steam/
├── app/
│   ├── api.py               # Flask routes
│   ├── auth.py              # security (bcrypt, Fernet, JWT)
│   ├── data_processing.py   # load, clean, merge, seed
│   ├── errors.py            # shared error response helper
│   ├── models.py            # SQLAlchemy models
│   └── schemas.py           # marshmallow validation schemas
├── data/
│   ├── raw/                 # place Kaggle CSVs here (gitignored)
│   ├── games.parquet        # built by data_processing (gitignored)
│   └── reviews_enriched.parquet
├── tests/
├── dashboard.py             # Streamlit dashboard
├── tp_morning.py            # morning TP deliverable
├── .env.example             # copy to .env and fill in keys
└── requirements.txt
```

---

## Key columns

| Column | Description |
|---|---|
| `review_ratio` | positive reviews / total reviews (0 to 1) |
| `price_tier` | free / budget (under $5) / mid ($5-20) / premium (over $20) |
| `is_indie` | True if "Indie" appears in the game's genre list |
| `primary_genre` | first genre listed for the game |
| `release_year` | extracted from the release date string |
| `estimated_owners_min/max` | parsed from the "X - Y" range string in the dataset |
