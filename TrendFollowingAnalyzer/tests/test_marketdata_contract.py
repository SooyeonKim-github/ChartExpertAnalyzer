from MarketData.universe import normalize_market_name

def test_market_aliases_distinguish_kospi_and_kosdaq():
    assert normalize_market_name("코스닥")=="KOSDAQ"; assert normalize_market_name("KOSDAQ")=="KOSDAQ"; assert normalize_market_name("KQ")=="KOSDAQ"; assert normalize_market_name("유가증권시장")=="KOSPI"; assert normalize_market_name("코스피")=="KOSPI"; assert normalize_market_name("KOSPI")=="KOSPI"
