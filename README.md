# DanmarkSkifter Trend Dashboard

Single-chart Streamlit dashboard for tracking how active `#DanmarkSkifter` is on Mastodon from `2025-12-01` onward.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Notes

- The app queries a public Mastodon hashtag timeline for `#DanmarkSkifter`.
- It defaults to `mastodon.social`, but you can switch to another instance in the sidebar.
- Mastodon APIs expose what a given instance still has available, so historical depth depends on the server and the number of pages scanned.
