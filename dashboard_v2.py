from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import streamlit as st

DATA_DIR      = Path(__file__).resolve().parent / "data"
GAMES_PARQUET = DATA_DIR / "games.parquet"

PRIMARY   = "#2C3E50"
SECONDARY = "#7F8C8D"
ALERT     = "#E74C3C"
BLUE      = "#2980B9"

BUCKET_COLORS = {
    "before 2015":  SECONDARY,
    "2015 to 2019": BLUE,
    "2020 to 2024": PRIMARY,
}

TIER_ORDER  = ["free", "budget", "mid", "premium"]
TIER_LABELS = {
    "free":    "Free",
    "budget":  "Budget (under 5)",
    "mid":     "Mid (5-20)",
    "premium": "Premium (over 20)",
}

BAND_ORDER  = ["mid", "new mid", "premium"]
BAND_LABELS = {
    "mid":     "Mid (5-20)",
    "new mid": "New mid (20-40)",
    "premium": "Premium (over 40)",
}

MIN_REVIEWS = 10
YEAR_MIN    = 2010
YEAR_MAX    = 2024
PRICE_CAP   = 80
REF_LINE    = 0.70

st.set_page_config(page_title="The price of disappointment", layout="wide")


@st.cache_data
def load_games() -> pd.DataFrame:
    df = pd.read_parquet(GAMES_PARQUET)
    df = df[
        (df["total_reviews"] >= MIN_REVIEWS) &
        (df["release_year"].between(YEAR_MIN, YEAR_MAX)) &
        (df["review_ratio"].notna())
    ].copy()

    def price_band(p):
        if p <= 0:  return "free"
        if p < 5:   return "budget"
        if p <= 20: return "mid"
        if p <= 40: return "new mid"
        return "premium"

    df["price_band"] = df["price"].apply(price_band)

    def year_bucket(y):
        if y < 2015:  return "before 2015"
        if y <= 2019: return "2015 to 2019"
        return "2020 to 2024"

    df["year_bucket"] = df["release_year"].apply(year_bucket)
    df["indie_label"] = df["is_indie"].map({True: "Indie", False: "Non-indie"})
    return df


def apply_style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, fontsize=12, fontweight="bold", color=PRIMARY, pad=8)
    ax.set_xlabel(xlabel, fontsize=10, color=SECONDARY)
    ax.set_ylabel(ylabel, fontsize=10, color=SECONDARY)
    ax.tick_params(colors=SECONDARY, labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor("#D5D8DC")
    ax.set_facecolor("#FDFEFE")


def section(title: str, thesis: str) -> None:
    st.subheader(title)
    st.caption(thesis)


def interpretation(text: str) -> None:
    st.markdown(f"*{text}*")


if not GAMES_PARQUET.exists():
    st.error(
        "games.parquet not found. Run the pipeline first:\n\n"
        "```\npython -m app.data_processing\n```"
    )
    st.stop()

games = load_games()

st.title("The price of disappointment")
st.markdown(
    "As AAA game prices climbed past 60 then 70 euros, player satisfaction dropped. "
    "The data shows it is the new mid-price tier 20 to 40 EUR that now earns the "
    "best reviews, not the most expensive titles."
)



section(
    "Prices have been rising, but not for everyone",
    "Since 2015, non-indie publishers have pushed prices steadily upward. Indie prices barely moved.",
)

ch1 = games[(games["price"] > 0) & (games["price"] <= PRICE_CAP)].copy()
price_trend = (
    ch1.groupby(["release_year", "indie_label"])["price"]
    .median()
    .reset_index()
)

fig, ax = plt.subplots(figsize=(11, 4))
for label, color in [("Indie", BLUE), ("Non-indie", ALERT)]:
    subset = price_trend[price_trend["indie_label"] == label]
    ax.plot(subset["release_year"], subset["price"],
            marker="o", markersize=4, linewidth=2, color=color, label=label)

apply_style(ax, "Median game price by release year", "Release year", "Median price (EUR)")
ax.legend(fontsize=9)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0f}"))
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

interpretation(
    "Non-indie prices show a clear upward step after 2022, when major publishers moved to the "
    "70 EUR standard. Indie titles stayed anchored in the 5-15 EUR range throughout the same period."
)



section(
    "Did paying more earn better reviews?",
    "Across every time period, higher price does not reliably predict a better review score.",
)

ch2 = games[(games["price"] > 0) & (games["price"] <= PRICE_CAP)].copy()
sample = ch2.sample(min(6_000, len(ch2)), random_state=42)

fig, ax = plt.subplots(figsize=(11, 5))

for bucket, color in BUCKET_COLORS.items():
    pts = sample[sample["year_bucket"] == bucket]
    ax.scatter(pts["price"], pts["review_ratio"],
               color=color, alpha=0.18, s=10, linewidths=0, label=bucket)

    trend = ch2[ch2["year_bucket"] == bucket][["price", "review_ratio"]].dropna()
    if len(trend) >= 20:
        coeffs = np.polyfit(trend["price"], trend["review_ratio"], 2)
        xs = np.linspace(trend["price"].min(), min(trend["price"].max(), PRICE_CAP), 200)
        ys = np.clip(np.polyval(coeffs, xs), 0, 1)
        ax.plot(xs, ys, color=color, linewidth=2.2)

ax.axhline(REF_LINE, color=SECONDARY, linewidth=1, linestyle="--", alpha=0.6,
           label=f"{REF_LINE:.0%} reference")

apply_style(ax, "Price vs review ratio, trend by era", "Price (EUR)", "Review ratio")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
ax.set_xlim(0, PRICE_CAP)
ax.set_ylim(0, 1.05)
ax.legend(fontsize=9)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

interpretation(
    "The trend lines are flat to slightly negative across all three eras. "
    "Recent high-priced releases (2020-2024) show the weakest relationship between price and score. "
    "players are not rewarding ambition, they are punishing unmet expectations."
)



section(
    "The AAA disappointment curve",
    "For non-indie games, the premium tier scores lower than mid, the opposite of what marketing suggests.",
)

ch3 = games.copy()
ch3["price_tier"] = pd.Categorical(ch3["price_tier"], categories=TIER_ORDER, ordered=True)

fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
palette = {t: c for t, c in zip(TIER_ORDER, [SECONDARY, BLUE, PRIMARY, ALERT])}

for ax, label in zip(axes, ["Non-indie", "Indie"]):
    subset = ch3[ch3["indie_label"] == label]
    sns.boxplot(
        data=subset, x="price_tier", y="review_ratio",
        palette=palette, width=0.5, linewidth=0.8, fliersize=1.5, ax=ax,
        order=TIER_ORDER,
    )
    ax.axhline(REF_LINE, color=SECONDARY, linewidth=1, linestyle="--", alpha=0.5)
    ax.set_title(label, fontsize=12, fontweight="bold", color=PRIMARY)
    ax.set_xlabel("")
    ax.set_ylabel("Review ratio" if ax is axes[0] else "")
    ax.set_xticklabels([TIER_LABELS[t] for t in TIER_ORDER], rotation=15, ha="right", fontsize=8)
    ax.tick_params(colors=SECONDARY, labelsize=9)
    ax.set_facecolor("#FDFEFE")
    for spine in ax.spines.values():
        spine.set_edgecolor("#D5D8DC")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))

fig.suptitle("Review ratio by price tier, indie vs non-indie", fontsize=12, fontweight="bold",
             color=PRIMARY, y=1.01)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

interpretation(
    "The non-indie premium box sits visibly lower than the mid box, the disappointment is real and measurable. "
    "Indie games show a different pattern: their premium tier holds up, likely because the audience self-selects "
    "and expectations are set more honestly."
)



section(
    "The 20-40 EUR tier is quietly winning",
    "Games priced between 20 and 40 EUR have pulled ahead of premium titles on review score since 2018.",
)

ch4 = games[(games["price"] > 5) & (games["price"] <= PRICE_CAP)].copy()
ch4 = ch4[ch4["price_band"].isin(BAND_ORDER)]
ch4["price_band"] = pd.Categorical(ch4["price_band"], categories=BAND_ORDER, ordered=True)

band_trend = (
    ch4.groupby(["release_year", "price_band"])["review_ratio"]
    .mean()
    .reset_index()
)

band_colors = {
    "mid":     SECONDARY,
    "new mid": BLUE,
    "premium": ALERT,
}

fig, ax = plt.subplots(figsize=(11, 4))
for band, color in band_colors.items():
    subset = band_trend[band_trend["price_band"] == band]
    ax.plot(subset["release_year"], subset["review_ratio"],
            marker="o", markersize=4, linewidth=2, color=color, label=BAND_LABELS[band])

ax.axhline(REF_LINE, color=SECONDARY, linewidth=1, linestyle="--", alpha=0.5)
apply_style(ax, "Average review ratio by price band over time", "Release year", "Average review ratio")
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
ax.legend(fontsize=9)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

st.markdown("**Top-reviewed games in the 20-40 EUR band**")

top_new_mid = (
    games[
        (games["price"] > 20) & (games["price"] <= 40) &
        (games["total_reviews"] >= 50) &
        (games["release_year"] >= 2021)
    ]
    .sort_values("review_ratio", ascending=False)
    .head(20)
    .sort_values("review_ratio")
)

ANNOTATE = {"Cyberpunk 2077", "Hades II"}

norm = plt.Normalize(top_new_mid["release_year"].min(), top_new_mid["release_year"].max())
cmap = plt.colormaps["Blues"]

fig, ax = plt.subplots(figsize=(9, 6))
bars = ax.barh(
    top_new_mid["name"].str[:45],
    top_new_mid["review_ratio"],
    color=[cmap(norm(y)) for y in top_new_mid["release_year"]],
    edgecolor="white",
)
for bar, (_, row) in zip(bars, top_new_mid.iterrows()):
    label = f"{row['review_ratio']:.2f}  {row['release_year']:.0f}  {row['price']:.0f} EUR"
    ax.text(bar.get_width() + 0.003, bar.get_y() + bar.get_height() / 2,
            label, va="center", fontsize=7.5, color=SECONDARY)
    if row["name"] in ANNOTATE:
        ax.annotate(
            row["name"],
            xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
            xytext=(-8, 0), textcoords="offset points",
            ha="right", va="center", fontsize=7.5, color=ALERT, fontweight="bold",
        )

ax.axvline(REF_LINE, color=SECONDARY, linewidth=1, linestyle="--", alpha=0.5)
apply_style(ax, "Top 20 games priced 20-40 EUR (min 50 reviews, from 2021)",
            "Review ratio", "")
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
ax.set_xlim(0, 1.12)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

interpretation(
    "The gap between the new mid and premium lines widens after 2018 and is largest in 2022-2024. "
    "exactly when the 70 EUR standard was being pushed. The top-reviewed games in this band "
    "demonstrate that the price point itself is not the cause: quality and honest positioning are."
)



section(
    "The verdict: what actually earns a good review",
    "The clearest predictor is the combination of indie status and the 5-20 EUR sweet spot. Games with fewer than 250 reviews are excluded.",
)

verdict_games = games[games["total_reviews"] >= 250]

pivot = (
    verdict_games.groupby(["price_tier", "indie_label"])["review_ratio"]
    .mean()
    .unstack("indie_label")
    .reindex(TIER_ORDER)
)

fig, ax = plt.subplots(figsize=(7, 4))
sns.heatmap(
    pivot,
    ax=ax,
    cmap="Blues",
    annot=True,
    fmt=".2f",
    linewidths=0.5,
    linecolor="#D5D8DC",
    cbar_kws={"label": "Avg review ratio"},
    vmin=0.6,
    vmax=1.0,
)
ax.set_title("Average review ratio by price tier and studio type",
             fontsize=12, fontweight="bold", color=PRIMARY, pad=8)
ax.set_xlabel("")
ax.set_ylabel("")
ax.set_yticklabels([TIER_LABELS[t] for t in TIER_ORDER], rotation=0, fontsize=9)
ax.set_xticklabels(["Non-indie", "Indie"], fontsize=9)
fig.tight_layout()
st.pyplot(fig)
plt.close(fig)

best_val  = pivot.stack().max()
worst_val = pivot.stack().min()
best_idx  = pivot.stack().idxmax()
worst_idx = pivot.stack().idxmin()
delta     = (
    pivot.loc["mid", "Indie"] - pivot.loc["premium", "Non-indie"]
    if "Indie" in pivot.columns and "Non-indie" in pivot.columns
    else float("nan")
)

col1, col2, col3 = st.columns(3)
col1.metric(
    "Best cell",
    f"{best_val:.1%}",
    f"{TIER_LABELS.get(best_idx[0], best_idx[0])} | {best_idx[1]}",
)
col2.metric(
    "Worst cell",
    f"{worst_val:.1%}",
    f"{TIER_LABELS.get(worst_idx[0], worst_idx[0])} | {worst_idx[1]}",
)
col3.metric(
    "Indie mid vs non-indie premium",
    f"{delta:+.1%}" if not np.isnan(delta) else "n/a",
    "the size of the gap",
)

interpretation(
    "Indie mid-priced games consistently outperform non-indie premium games by a meaningful margin. "
    "The data does not reward scale, it rewards games that deliver what they promise at a price "
    "that does not set the player up for disappointment."
)
