import os
import sys
import string
import random
import matplotlib.pyplot as plt
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models import get_session, init_db
from app import auth, admin_helpers as ah

PRIMARY   = "#2C3E50"
SECONDARY = "#7F8C8D"
ALERT     = "#E74C3C"
ACCENT    = "#2980B9"

st.set_page_config(page_title="Admin dashboard", layout="wide")

init_db()


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------

def _login_form() -> None:
    st.title("Admin dashboard")
    st.subheader("Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        with get_session() as session:
            from app.models import User
            user = session.query(User).filter_by(username=username.strip()).first()
            if user is None or not auth.verify_password(password, user.password_hash):
                st.error("Invalid username or password.")
            elif user.role != "admin":
                st.error("Not an admin account.")
            else:
                ah.update_last_login(session, user.id)
                st.session_state.admin_user = {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role,
                }
                st.rerun()


if "admin_user" not in st.session_state:
    _login_form()
    st.stop()

admin = st.session_state.admin_user


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(f"**{admin['username']}** | {admin['role']}")
    page = st.radio(
        "Navigate",
        ["Overview", "Users", "Games", "Reviews", "Database"],
        label_visibility="collapsed",
    )
    if st.button("Logout"):
        del st.session_state.admin_user
        st.rerun()


# ---------------------------------------------------------------------------
# Helper: bar chart
# ---------------------------------------------------------------------------

def _hbar(labels: list[str], values: list[int], title: str) -> None:
    fig, ax = plt.subplots(figsize=(8, max(3, len(labels) * 0.4)))
    ax.barh(labels, values, color=ACCENT, edgecolor="white")
    ax.set_title(title, fontsize=11, fontweight="bold", color=PRIMARY, pad=6)
    ax.tick_params(colors=SECONDARY, labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#D5D8DC")
    ax.set_facecolor("#FDFEFE")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Page 1 | Overview
# ---------------------------------------------------------------------------

if page == "Overview":
    st.title("Overview")

    with get_session() as session:
        n_users   = ah.count_users(session)
        n_games   = ah.count_games(session)
        n_reviews = ah.count_reviews(session)
        devs      = ah.top_developers(session)
        genres    = ah.top_genres(session)

    db_path = os.path.abspath("datastory.db")
    try:
        db_mb = os.path.getsize(db_path) / (1024 * 1024)
        db_label = f"{db_mb:.1f} MB"
    except FileNotFoundError:
        db_label = "not found"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Users", f"{n_users:,}")
    c2.metric("Games", f"{n_games:,}")
    c3.metric("Reviews", f"{n_reviews:,}")
    c4.metric("DB size", db_label)

    col_left, col_right = st.columns(2)
    with col_left:
        if devs:
            labels = [d[0][:40] for d in reversed(devs)]
            values = [d[1] for d in reversed(devs)]
            _hbar(labels, values, "Top 10 developers by game count")
        else:
            st.info("No game data yet. Run the data pipeline first.")
    with col_right:
        if genres:
            labels = [g[0][:40] for g in reversed(genres)]
            values = [g[1] for g in reversed(genres)]
            _hbar(labels, values, "Top 10 genres by game count")


# ---------------------------------------------------------------------------
# Page 2 | Users
# ---------------------------------------------------------------------------

elif page == "Users":
    st.title("Users")

    col1, col2, col3 = st.columns([3, 2, 2])
    with col1:
        q = st.text_input("Search by username", key="u_search")
    with col2:
        role_filter = st.selectbox("Role", ["all", "admin", "user", "viewer"], key="u_role")
    with col3:
        sort = st.selectbox(
            "Sort",
            ["created_at desc", "username asc", "last_login_at desc"],
            key="u_sort",
        )

    if "u_page" not in st.session_state:
        st.session_state.u_page = 0

    if st.session_state.get("_u_prev_q") != (q, role_filter, sort):
        st.session_state.u_page = 0
        st.session_state["_u_prev_q"] = (q, role_filter, sort)

    with get_session() as session:
        users, total = ah.search_users(session, q, role_filter, sort, st.session_state.u_page)

    st.caption(f"{total:,} users | page {st.session_state.u_page + 1}")

    pcol1, pcol2 = st.columns(2)
    if pcol1.button("Previous", disabled=st.session_state.u_page == 0):
        st.session_state.u_page -= 1
        st.rerun()
    if pcol2.button("Next", disabled=(st.session_state.u_page + 1) * ah.PER_PAGE >= total):
        st.session_state.u_page += 1
        st.rerun()

    for user in users:
        with st.expander(f"id={user.id} | {user.username} | {user.role}"):
            cols = st.columns(4)
            cols[0].markdown(f"**Created** {user.created_at}")
            cols[1].markdown(f"**Last login** {user.last_login_at or 'never'}")

            with get_session() as session:
                full = ah.get_user(session, user.id)
                try:
                    email = auth.decrypt_field(full.email_encrypted)
                except Exception:
                    email = "(decryption error)"
            cols[2].markdown(f"**Email** {email}")

            action = st.selectbox(
                "Action",
                ["— select —", "Change role", "Reset password", "Delete"],
                key=f"action_{user.id}",
            )

            if action == "Change role":
                new_role = st.selectbox("New role", ["admin", "user", "viewer"], key=f"nr_{user.id}")
                st.warning(f"Change {user.username} from role '{user.role}' to '{new_role}'")
                if user.id == admin["id"]:
                    st.error("You cannot change your own role.")
                elif st.button("Confirm", key=f"cr_{user.id}"):
                    with get_session() as session:
                        ah.set_user_role(session, user.id, new_role)
                    st.success(f"Role updated to {new_role}.")
                    st.rerun()

            elif action == "Reset password":
                new_pw = "".join(random.choices(string.ascii_letters + string.digits, k=12))
                st.warning(f"Generate a temporary password for {user.username}.")
                if st.button("Confirm", key=f"rp_{user.id}"):
                    with get_session() as session:
                        ah.reset_user_password(session, user.id, new_pw)
                    st.success(f"Password reset. Temporary password: `{new_pw}`")

            elif action == "Delete":
                st.error(f"Delete user {user.username} (id={user.id}). This cannot be undone.")
                if user.id == admin["id"]:
                    st.error("You cannot delete the currently logged-in account.")
                elif st.button("Confirm", key=f"del_{user.id}"):
                    with get_session() as session:
                        ah.delete_user(session, user.id)
                    st.success(f"User {user.username} deleted.")
                    st.rerun()


# ---------------------------------------------------------------------------
# Page 3 | Games
# ---------------------------------------------------------------------------

elif page == "Games":
    st.title("Games")

    with st.expander("Filters", expanded=True):
        fc1, fc2, fc3 = st.columns(3)
        name_q  = fc1.text_input("Name search", key="g_name")
        appid_q = fc2.text_input("app_id exact match", key="g_appid")
        sort_g  = fc3.selectbox(
            "Sort",
            ["review_ratio desc", "review_ratio asc", "total_reviews desc",
             "price desc", "price asc", "release_year desc", "name asc"],
            key="g_sort",
        )
        fc4, fc5, fc6 = st.columns(3)
        tiers = fc4.multiselect("Price tier", ["free", "budget", "mid", "premium"], key="g_tiers")
        indie = fc5.radio("Indie", ["all", "indie", "non-indie"], horizontal=True, key="g_indie")
        years = fc6.slider("Release year", 2000, 2024, (2010, 2024), key="g_years")

        with get_session() as session:
            all_genres = ah.distinct_genres(session)
        genres_sel = st.multiselect("Genre", all_genres, key="g_genres")

    filter_key = (name_q, appid_q, sort_g, tuple(tiers), indie, years, tuple(genres_sel))
    if st.session_state.get("_g_prev") != filter_key:
        st.session_state.g_page = 0
        st.session_state["_g_prev"] = filter_key

    if "g_page" not in st.session_state:
        st.session_state.g_page = 0

    with get_session() as session:
        games, total = ah.search_games(
            session,
            name=name_q,
            app_id=appid_q,
            price_tiers=tiers or None,
            is_indie=indie,
            year_min=years[0],
            year_max=years[1],
            genres=genres_sel or None,
            sort=sort_g,
            page=st.session_state.g_page,
        )

    st.caption(f"{total:,} games | page {st.session_state.g_page + 1}")

    pc1, pc2 = st.columns(2)
    if pc1.button("Previous", key="g_prev", disabled=st.session_state.g_page == 0):
        st.session_state.g_page -= 1
        st.rerun()
    if pc2.button("Next", key="g_next", disabled=(st.session_state.g_page + 1) * ah.PER_PAGE >= total):
        st.session_state.g_page += 1
        st.rerun()

    for game in games:
        label = f"{game.app_id} | {(game.name or '')[:50]} | {game.price_tier} | {game.review_ratio or 'n/a'}"
        with st.expander(label):
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"**Developer** {game.primary_developer}")
            c2.markdown(f"**Genre** {game.primary_genre}")
            c3.markdown(f"**Year** {game.release_year}")
            c4.markdown(f"**Total reviews** {game.total_reviews:,}" if game.total_reviews else "**Total reviews** n/a")

            from app.steam_images import header_url
            try:
                st.image(header_url(game.app_id), width=250)
            except Exception:
                pass

            edit_field = st.selectbox(
                "Edit field",
                ["— select —", "name", "primary_developer", "primary_genre", "price_tier", "is_indie"],
                key=f"ef_{game.app_id}",
            )
            if edit_field != "— select —":
                if edit_field == "is_indie":
                    new_val = st.radio("New value", [True, False],
                                       format_func=lambda x: "Indie" if x else "Non-indie",
                                       key=f"ev_{game.app_id}")
                elif edit_field == "price_tier":
                    new_val = st.selectbox("New value", ["free", "budget", "mid", "premium"],
                                           key=f"ev_{game.app_id}")
                else:
                    new_val = st.text_input("New value",
                                            value=getattr(game, edit_field, "") or "",
                                            key=f"ev_{game.app_id}")
                old_val = getattr(game, edit_field, "")
                st.warning(f"Change {edit_field} from '{old_val}' to '{new_val}'")
                if st.button("Confirm edit", key=f"ce_{game.app_id}"):
                    with get_session() as session:
                        ah.edit_game_field(session, game.app_id, edit_field, new_val)
                    st.success("Field updated.")
                    st.rerun()

            with get_session() as session:
                rev_count = ah.count_reviews_for_game(session, game.app_id)
            st.error(
                f"Delete this game? This will also remove {rev_count:,} linked reviews."
            )
            if st.button("Confirm delete", key=f"dg_{game.app_id}"):
                with get_session() as session:
                    ah.delete_game(session, game.app_id)
                st.success(f"Game {game.app_id} and {rev_count:,} reviews deleted.")
                st.rerun()


# ---------------------------------------------------------------------------
# Page 4 | Reviews
# ---------------------------------------------------------------------------

elif page == "Reviews":
    st.title("Reviews")
    st.caption("This table is read-only in v1.")

    rc1, rc2, rc3 = st.columns([2, 2, 3])
    r_appid = rc1.text_input("app_id (required unless searching text)", key="r_appid")
    r_score = rc2.selectbox("Score", ["all", "positive", "negative"], key="r_score")
    r_text  = rc3.text_input("Search review text (slow without index)", key="r_text")

    if r_text:
        st.caption("Text search scans the full table. This may be slow.")

    if not r_appid and not r_text:
        st.info("Enter an app_id or a text search term to load reviews.")
        st.stop()

    filter_key_r = (r_appid, r_score, r_text)
    if st.session_state.get("_r_prev") != filter_key_r:
        st.session_state.r_page = 0
        st.session_state["_r_prev"] = filter_key_r

    if "r_page" not in st.session_state:
        st.session_state.r_page = 0

    with get_session() as session:
        reviews, total = ah.search_reviews(session, r_appid, r_score, r_text, st.session_state.r_page)

    st.caption(f"{total:,} reviews | page {st.session_state.r_page + 1}")

    rp1, rp2 = st.columns(2)
    if rp1.button("Previous", key="r_prev", disabled=st.session_state.r_page == 0):
        st.session_state.r_page -= 1
        st.rerun()
    if rp2.button("Next", key="r_next", disabled=(st.session_state.r_page + 1) * ah.PER_PAGE >= total):
        st.session_state.r_page += 1
        st.rerun()

    score_label = {2: "Positive", 1: "Negative", None: "—"}
    for rev in reviews:
        short_text = (rev.review_text or "")[:200]
        label = f"id={rev.id} | app={rev.app_id} | {score_label.get(rev.review_score, '—')}"
        with st.expander(label):
            st.markdown(f"**Game** {rev.app_name or rev.app_id}")
            st.markdown(f"**Score** {score_label.get(rev.review_score, '—')}")
            st.markdown(f"**Helpful votes** {rev.review_votes or 0}")
            st.text_area("Review text", value=rev.review_text or "", height=150,
                         disabled=True, key=f"rt_{rev.id}")


# ---------------------------------------------------------------------------
# Page 5 | Database
# ---------------------------------------------------------------------------

elif page == "Database":
    st.title("Database")

    db_path = os.path.abspath("datastory.db")

    st.subheader("File info")
    try:
        stat = os.stat(db_path)
        c1, c2, c3 = st.columns(3)
        c1.metric("Path", db_path)
        c2.metric("Size", f"{stat.st_size / (1024 * 1024):.2f} MB")
        import datetime
        c3.metric("Last modified", datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"))
    except FileNotFoundError:
        st.warning(f"Database file not found at {db_path}")

    st.subheader("Row counts")
    with get_session() as session:
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("Users",   ah.count_users(session))
        rc2.metric("Games",   ah.count_games(session))
        rc3.metric("Reviews", f"{ah.count_reviews(session):,}")

    @st.cache_data
    def _schema_info():
        from app.models import Base, engine
        from sqlalchemy import inspect as sa_inspect
        insp = sa_inspect(engine)
        result = {}
        for table_name in insp.get_table_names():
            cols = insp.get_columns(table_name)
            result[table_name] = [
                {
                    "column": c["name"],
                    "type":   str(c["type"]),
                    "nullable": c.get("nullable", True),
                    "default": str(c.get("default", "")),
                }
                for c in cols
            ]
        return result

    st.subheader("Schema")
    import pandas as pd
    schema = _schema_info()
    for table, cols in schema.items():
        st.markdown(f"**{table}**")
        st.dataframe(pd.DataFrame(cols), use_container_width=True, hide_index=True)

    st.subheader("Reseed database")
    st.warning(
        "This will run seed_db() from app.data_processing. "
        "Existing rows will not be duplicated (INSERT OR IGNORE). "
        "This can take several minutes."
    )
    if "reseed_confirm" not in st.session_state:
        st.session_state.reseed_confirm = False

    if st.button("Reseed"):
        st.session_state.reseed_confirm = True

    if st.session_state.reseed_confirm:
        st.error("Are you sure? This operation runs the full pipeline and commits to the DB.")
        if st.button("Confirm reseed"):
            import io, contextlib
            from app.data_processing import seed_db
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with get_session() as session:
                    seed_db(session)
            st.code(buf.getvalue())
            st.session_state.reseed_confirm = False
