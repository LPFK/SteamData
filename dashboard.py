from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st
from matplotlib.lines import Line2D

DATA_DIR        = Path(__file__).resolve().parent / "data"
GAMES_PARQUET   = DATA_DIR / "games.parquet"
REVIEWS_PARQUET = DATA_DIR / "reviews_enriched.parquet"

PRIMARY         = "#2C3E50"
SECONDARY       = "#7F8C8D"
ALERT           = "#E74C3C"
INDIE_COLOR     = "#2980B9"
NON_INDIE_COLOR = "#E74C3C"

PRICE_TIER_ORDER  = ["free", "budget", "mid", "premium"]
PRICE_TIER_LABELS = {
    "free":    "Free",
    "budget":  "Budget (<$5)",
    "mid":     "Mid ($5-20)",
    "premium": "Premium (>$20)",
}

MIN_REVIEWS = 10

st.set_page_config(page_title="Steam Data Story", page_icon=None, layout="wide")


@st.cache_data
def load_games() -> pd.DataFrame:
    df = pd.read_parquet(GAMES_PARQUET)
    df = df[df["total_reviews"] >= MIN_REVIEWS].copy()
    df["indie_label"] = df["is_indie"].map({True: "Indie", False: "Non-indie"})
    df["price_tier"]  = pd.Categorical(df["price_tier"], categories=PRICE_TIER_ORDER, ordered=True)
    return df


def apply_style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, fontsize=13, fontweight="bold", color=PRIMARY, pad=10)
    ax.set_xlabel(xlabel, fontsize=10, color=SECONDARY)
    ax.set_ylabel(ylabel, fontsize=10, color=SECONDARY)
    ax.tick_params(colors=SECONDARY, labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor("#D5D8DC")
    ax.set_facecolor("#FDFEFE")


if not GAMES_PARQUET.exists():
    st.error(
        "games.parquet not found. Run the pipeline first:\n\n"
        "```\npython -m app.data_processing\n```"
    )
    st.stop()


games = load_games()

st.title("Steam games as a data story")
st.caption(
    f"Dataset A | {len(games):,} games with at least {MIN_REVIEWS} reviews | "
    "review_ratio = positive / (positive + negative)"
)

st.divider()

col1, col2, col3, col4 = st.columns(4)

indie_mean   = games.loc[games["is_indie"],  "review_ratio"].mean()
nonind_mean  = games.loc[~games["is_indie"], "review_ratio"].mean()
free_mean    = games.loc[games["price_tier"] == "free",    "review_ratio"].mean()
premium_mean = games.loc[games["price_tier"] == "premium", "review_ratio"].mean()

col1.metric("Games analysed",        f"{len(games):,}")
col2.metric("Indie avg score",       f"{indie_mean:.1%}", f"{indie_mean - nonind_mean:+.1%} vs non-indie")
col3.metric("Free games avg score",    f"{free_mean:.1%}")
col4.metric("Premium games avg score", f"{premium_mean:.1%}")

st.divider()

st.subheader("Review score distribution")
st.caption("Most games cluster near the extremes — the 'bimodal' pattern typical of Steam.")

fig, ax = plt.subplots(figsize=(9, 3.5))
ax.hist(games["review_ratio"].dropna(), bins=60, color=PRIMARY, edgecolor="white", linewidth=0.4)
apply_style(ax, "Distribution of review ratio (all games, >= 10 reviews)", "Review ratio", "Number of games")
ax.axvline(
    games["review_ratio"].median(), color=ALERT, linewidth=1.5, linestyle="--",
    label=f"Median {games['review_ratio'].median():.2f}",
)
ax.legend(fontsize=9)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

st.divider()

st.subheader("Do indie games score better than non-indie, at the same price?")
st.caption("Box plots per price tier. Filters: >= 10 reviews. H1 predicts indie > non-indie at every tier.")

fig, axes = plt.subplots(1, 4, figsize=(14, 4.5), sharey=True)
palette = {"Indie": INDIE_COLOR, "Non-indie": NON_INDIE_COLOR}

for i, tier in enumerate(PRICE_TIER_ORDER):
    subset = games[games["price_tier"] == tier]
    ax = axes[i]
    if subset.empty:
        ax.set_visible(False)
        continue
    sns.boxplot(
        data=subset, x="indie_label", y="review_ratio",
        palette=palette, width=0.5, linewidth=0.8, fliersize=2, ax=ax,
    )
    n_indie   = subset["is_indie"].sum()
    n_nonindi = (~subset["is_indie"]).sum()
    ax.set_title(PRICE_TIER_LABELS[tier], fontsize=11, fontweight="bold", color=PRIMARY)
    ax.set_xlabel("")
    ax.set_ylabel("Review ratio" if i == 0 else "")
    ax.tick_params(colors=SECONDARY, labelsize=9)
    ax.set_facecolor("#FDFEFE")
    for spine in ax.spines.values():
        spine.set_edgecolor("#D5D8DC")
    ax.text(0, -0.12, f"n={n_indie:,}",  ha="center", fontsize=7, color=INDIE_COLOR,     transform=ax.get_xaxis_transform())
    ax.text(1, -0.12, f"n={n_nonindi:,}", ha="center", fontsize=7, color=NON_INDIE_COLOR, transform=ax.get_xaxis_transform())

fig.suptitle("Review ratio by price tier — indie vs non-indie", fontsize=13, fontweight="bold", color=PRIMARY, y=1.01)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

st.divider()

st.subheader("Does higher price predict a better (or worse) review score?")
st.caption("Bar chart: median review ratio per price tier. H2 tests whether free games are punished for aggressive monetization.")

tier_stats = (
    games.groupby("price_tier", observed=True)["review_ratio"]
    .agg(median="median", count="count")
    .reset_index()
)

fig, ax = plt.subplots(figsize=(7, 4))
bars = ax.bar(
    tier_stats["price_tier"].map(PRICE_TIER_LABELS),
    tier_stats["median"],
    color=[PRIMARY, SECONDARY, "#5DADE2", "#A9CCE3"],
    edgecolor="white",
    width=0.55,
)
for bar, (_, row) in zip(bars, tier_stats.iterrows()):
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 0.005,
        f"{row['median']:.2f}\nn={int(row['count']):,}",
        ha="center", va="bottom", fontsize=8, color=PRIMARY,
    )
apply_style(ax, "Median review ratio by price tier", "Price tier", "Median review ratio")
ax.set_ylim(0, 1)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

st.divider()

st.subheader("Has Steam become saturated? Do newer games score lower?")
st.caption("Median review ratio by release year, indie vs non-indie. H5 predicts a drop post-2015 as supply exploded.")

year_data = (
    games.dropna(subset=["release_year", "review_ratio"])
    .groupby(["release_year", "indie_label"])["review_ratio"]
    .median()
    .reset_index()
)
year_data = year_data[year_data["release_year"].between(2005, 2024)]

fig, ax = plt.subplots(figsize=(11, 4))
for label, color in [("Indie", INDIE_COLOR), ("Non-indie", NON_INDIE_COLOR)]:
    subset = year_data[year_data["indie_label"] == label]
    ax.plot(subset["release_year"], subset["review_ratio"],
            marker="o", markersize=4, color=color, linewidth=1.8, label=label)

apply_style(ax, "Median review ratio by release year", "Release year", "Median review ratio")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
ax.axvline(2015, color=ALERT, linewidth=1, linestyle="--", alpha=0.6, label="2015 — Steam Direct opens")
ax.legend(fontsize=9)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

st.divider()

st.subheader("Do players who spend more time also review better?")
st.caption(
    "Scatter of average playtime (log scale) vs review ratio. "
    "Capped at 2000h to remove extreme outliers. H4 predicts a positive correlation."
)

playtime_data = (
    games[games["average_playtime_forever"] > 0]
    .dropna(subset=["review_ratio"])
    .sample(min(8_000, len(games)), random_state=42)
)

fig, ax = plt.subplots(figsize=(9, 4.5))
ax.scatter(
    playtime_data["average_playtime_forever"].clip(upper=120_000) / 60,
    playtime_data["review_ratio"],
    c=playtime_data["is_indie"].map({True: INDIE_COLOR, False: NON_INDIE_COLOR}),
    alpha=0.25, s=12, linewidths=0,
)
ax.set_xscale("log")
ax.legend(handles=[
    Line2D([0], [0], marker="o", color="w", markerfacecolor=INDIE_COLOR,     markersize=7, label="Indie"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor=NON_INDIE_COLOR, markersize=7, label="Non-indie"),
], fontsize=9)
apply_style(ax, "Average playtime vs review ratio (log scale, sample of 8k games)",
            "Average playtime (hours, log scale)", "Review ratio")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

st.divider()

st.subheader("Which genres score the highest on average?")
st.caption("Top 15 genres by median review ratio (min 50 games per genre).")

genre_stats = (
    games.groupby("primary_genre")["review_ratio"]
    .agg(median="median", count="count")
    .reset_index()
    .query("count >= 50")
    .sort_values("median", ascending=True)
    .tail(15)
)

fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.barh(genre_stats["primary_genre"], genre_stats["median"], color=PRIMARY, edgecolor="white")
for bar, (_, row) in zip(bars, genre_stats.iterrows()):
    ax.text(
        bar.get_width() + 0.003,
        bar.get_y() + bar.get_height() / 2,
        f"{row['median']:.2f}  n={int(row['count']):,}",
        va="center", fontsize=7.5, color=SECONDARY,
    )
apply_style(ax, "Top 15 genres by median review ratio (min 50 games)", "Median review ratio", "")
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
ax.set_xlim(0, 1.05)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)
