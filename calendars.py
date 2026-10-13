"""Event calendars (FOMC meetings, CPI releases, earnings dates...) for strategies to use.

Files live in calendars/<name>.csv and are committed. Required columns:
    date        event date, YYYY-MM-DD
    source_url  where the date was checked (an official page, not memory)
Optional:
    announced   date the event date became public. Without it, a strategy could
                trade on dates nobody knew yet, which is look-ahead.

Strategies must load dates through this module, never type them into code.
"""
from pathlib import Path

import pandas as pd

CAL_DIR = Path(__file__).parent / "calendars"


def load(name, cal_dir=CAL_DIR):
    df = pd.read_csv(Path(cal_dir) / f"{name}.csv", dtype=str)
    missing = {"date", "source_url"} - set(df.columns)
    if missing:
        raise ValueError(f"calendars/{name}.csv missing columns {missing}")
    if df["source_url"].isna().any() or (df["source_url"].str.strip() == "").any():
        raise ValueError(f"calendars/{name}.csv has rows with no source_url; every date must be sourced")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    if "announced" in df.columns:
        df["announced"] = pd.to_datetime(df["announced"]).dt.date
    return df.sort_values("date").reset_index(drop=True)


def known_as_of(cal, as_of):
    """Events whose date was public on as_of (a date). Rows without 'announced' count as known."""
    if "announced" not in cal.columns:
        return cal
    return cal[cal["announced"].isna() | (cal["announced"] <= as_of)]
