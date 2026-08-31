from __future__ import annotations

import pandas as pd


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    rename = {
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
        "날짜": "date", "시가": "open", "고가": "high", "저가": "low",
        "종가": "close", "거래량": "volume",
    }
    return df.rename(columns=rename)
