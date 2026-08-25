from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
from reporting.writer import write_daily
from services.scanner import BullishPatternScanner


def main() -> None:
    p=argparse.ArgumentParser(description="Bullish chart-pattern scanner for KOSPI/KOSDAQ"); p.add_argument("--date",default=pd.Timestamp.today().strftime("%Y%m%d")); p.add_argument("--top-n",type=int,default=100); a=p.parse_args(); scanner=BullishPatternScanner(); candidates=scanner.scan(a.date,a.top_n); out=Path(__file__).resolve().parent/"results"/a.date; write_daily(out,candidates); print(f"[DONE] {len(candidates)} pattern observations -> {out}")


if __name__ == "__main__": main()
