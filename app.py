from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

import altair as alt
import pandas as pd
import requests
import streamlit as st


DEFAULT_INSTANCE = "helvede.net"
HASHTAG = "DanmarkSkifter"
START_DATE = date(2025, 12, 1)
PAGE_LIMIT = 40
REQUEST_TIMEOUT = 20
USER_AGENT = "danmark-skifter-trend-dashboard/1.0"


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def strip_html(value: str) -> str:
    parser = _HTMLStripper()
    parser.feed(value or "")
    return parser.get_text().strip()


def parse_next_max_id(link_header: Optional[str]) -> Optional[str]:
    if not link_header:
        return None

    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue

        start = section.find("<")
        end = section.find(">")
        if start == -1 or end == -1:
            continue

        url = section[start + 1 : end]
        if "max_id=" not in url:
            continue

        return url.split("max_id=", 1)[1].split("&", 1)[0]

    return None


def fetch_hashtag_statuses(
    instance: str,
    hashtag: str,
    start_date: date,
    page_limit: int,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    base_url = f"https://{instance}/api/v1/timelines/tag/{hashtag}"
    params = {"limit": 40}
    max_id: Optional[str] = None
    rows: List[Dict[str, object]] = []
    pages_fetched = 0
    oldest_seen: Optional[date] = None

    for _ in range(page_limit):
        if max_id:
            params["max_id"] = max_id
        elif "max_id" in params:
            del params["max_id"]

        response = session.get(base_url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()

        if not payload:
            break

        pages_fetched += 1

        for status in payload:
            created_at = datetime.fromisoformat(
                status["created_at"].replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            created_day = created_at.date()
            oldest_seen = created_day if oldest_seen is None else min(oldest_seen, created_day)

            if created_day < start_date:
                continue

            rows.append(
                {
                    "created_day": created_day,
                    "created_at": created_at,
                    "account": status["account"]["acct"],
                    "display_name": status["account"]["display_name"]
                    or status["account"]["username"],
                    "content_text": strip_html(status["content"]),
                    "reblogs": status["reblogs_count"],
                    "favourites": status["favourites_count"],
                    "replies": status["replies_count"],
                    "url": status["url"] or status["uri"],
                }
            )

        max_id = parse_next_max_id(response.headers.get("Link"))
        if not max_id:
            break
        if oldest_seen and oldest_seen < start_date:
            break

    frame = pd.DataFrame(rows)
    meta: Dict[str, object] = {
        "pages_fetched": pages_fetched,
        "oldest_seen": oldest_seen.isoformat() if oldest_seen else None,
        "statuses_collected": len(rows),
        "start_date": start_date.isoformat(),
        "instance": instance,
    }
    return frame, meta


def build_daily_trend(frame: pd.DataFrame, start_date: date) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["created_day", "posts", "engagement"])

    trend = (
        frame.assign(
            engagement=frame["reblogs"] + frame["favourites"] + frame["replies"]
        )
        .groupby("created_day", as_index=False)
        .agg(posts=("url", "count"), engagement=("engagement", "sum"))
    )

    all_days = pd.date_range(start=start_date, end=date.today(), freq="D")
    trend = (
        trend.set_index("created_day")
        .reindex(all_days, fill_value=0)
        .rename_axis("created_day")
        .reset_index()
    )
    trend["created_day"] = pd.to_datetime(trend["created_day"])
    return trend


@st.cache_data(show_spinner=False, ttl=1800)
def load_data(instance: str, hashtag: str, start_date: date, page_limit: int):
    frame, meta = fetch_hashtag_statuses(instance, hashtag, start_date, page_limit)
    trend = build_daily_trend(frame, start_date)
    return frame, trend, meta


st.set_page_config(
    page_title="#DanmarkSkifter on Mastodon",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(255, 214, 10, 0.18), transparent 34%),
            radial-gradient(circle at top right, rgba(0, 119, 182, 0.14), transparent 32%),
            linear-gradient(180deg, #f6f1e8 0%, #f4efe5 46%, #efe7db 100%);
    }
    .block-container {
        max-width: 1180px;
        padding-top: 2.4rem;
        padding-bottom: 2rem;
    }
    h1, h2, h3 {
        font-family: "Georgia", "Times New Roman", serif;
        letter-spacing: -0.02em;
        color: #102a43;
    }
    p, div[data-testid="stMarkdownContainer"] p, label {
        color: #243b53;
    }
    .hero {
        padding: 1.4rem 1.6rem;
        border: 1px solid rgba(16, 42, 67, 0.08);
        border-radius: 24px;
        background: rgba(255, 252, 247, 0.72);
        backdrop-filter: blur(8px);
        box-shadow: 0 18px 48px rgba(16, 42, 67, 0.08);
        margin-bottom: 1rem;
    }
    .hero-kicker {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        color: #486581;
        margin-bottom: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <section class="hero">
        <div class="hero-kicker">Single-Chart Mastodon Dashboard</div>
        <h1>How trending is #{HASHTAG} on Mastodon?</h1>
        <p>
            This dashboard pulls public posts from a Mastodon hashtag timeline and rolls them up by day,
            starting on <strong>{START_DATE.isoformat()}</strong>.
        </p>
    </section>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Data Source")
    instance = st.text_input("Mastodon instance", value=DEFAULT_INSTANCE).strip()
    st.caption("Default server is `helvede.net`. If that does not work, try `mastodon.social`.")
    page_limit = st.slider("Pages to scan", min_value=5, max_value=40, value=PAGE_LIMIT)
    st.caption(
        "More pages digs further back in time, but the API only exposes what the chosen instance still has available."
    )

try:
    posts_frame, trend_frame, metadata = load_data(
        instance=instance,
        hashtag=HASHTAG,
        start_date=START_DATE,
        page_limit=page_limit,
    )
except requests.HTTPError as exc:
    st.error(f"Mastodon returned an error: {exc}")
    st.stop()
except requests.RequestException as exc:
    st.error(f"Could not reach the Mastodon API: {exc}")
    st.stop()

if trend_frame.empty:
    st.warning(
        "No public posts were returned for this hashtag on the selected instance in the available time range."
    )
    st.stop()

chart = (
    alt.Chart(trend_frame)
    .mark_area(line={"color": "#0b6e4f", "strokeWidth": 2.5}, color="#f4a261")
    .encode(
        x=alt.X("created_day:T", title="Day"),
        y=alt.Y("posts:Q", title="Posts with #DanmarkSkifter"),
        tooltip=[
            alt.Tooltip("created_day:T", title="Day"),
            alt.Tooltip("posts:Q", title="Posts"),
            alt.Tooltip("engagement:Q", title="Engagement"),
        ],
    )
    .properties(height=520)
)

st.altair_chart(chart, width="stretch")

st.caption(
    f"Loaded {metadata['statuses_collected']} posts from `{metadata['instance']}` across "
    f"{metadata['pages_fetched']} API pages. Oldest fetched day: {metadata['oldest_seen'] or 'unknown'}."
)
