# ============================================================
# ETF OPTIONS DASHBOARD  — Full Featured
# ============================================================
# Workflow:
#   Step 1 → Sector Screener  (52W range, RS vs SPY, composite
#             score, P/C signal, conflict analysis)
#   Step 2 → Holdings Drill-Down  (leading vs lagging stocks)
#   Step 3 → Options Filter  (IV, HV30, earnings, skew)
#
# New in this version:
#   • VIX context  (sidebar — calibrates all P/C readings)
#   • Relative Strength vs SPY  (1-month, in main table)
#   • Composite Score  (ranks all ETFs 0-100)
#   • Sector Rotation Heatmap  (1W / 1M / 3M returns grid)
#   • Separate P/C Signal column  (VIX-adjusted thresholds)
#   • Conflict panel — OBV divergence, MFI, volume 5/10/20d,
#     RSI, % above 50MA, put skew + plain-English interpretation
# ============================================================

import time
import requests
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="ETF Options Dashboard",
    page_icon="📊",
    layout="wide",
)

# ============================================================
# ETF UNIVERSE
# ============================================================
ETF_SECTORS = {
    "Broad Market": [
        ("IVV",  "iShares S&P 500"),
        ("VTI",  "Vanguard Total Market"),
        ("VOO",  "Vanguard S&P 500"),
        ("SPY",  "SPDR S&P 500"),
        ("IWM",  "iShares Russell 2000"),
    ],
    "Nasdaq / Growth": [
        ("QQQ",  "Invesco QQQ"),
        ("AMOM", "QRAFT AI Momentum"),
    ],
    "Technology": [
        ("SKYY", "First Trust Cloud"),
        ("XLK",  "Tech Select Sector"),
        ("CIBR", "First Trust Cybersecurity"),
        ("IYW",  "iShares US Technology"),
        ("IGV",  "iShares Software"),
        ("SOCL", "Global X Social Media"),
    ],
    "Semiconductors": [
        ("SMH",  "VanEck Semiconductors"),
        ("SOXX", "iShares Semiconductors"),
    ],
    "Robotics / AI": [
        ("BOTZ", "Global X Robotics & AI"),
    ],
    "Data Centers": [
        ("SRVR", "Pacer Data & Infrastructure"),
    ],
    "Fintech / Blockchain": [
        ("MILN", "Global X Millennials"),
        ("FINX", "Global X FinTech"),
        ("BLOK", "Amplify Blockchain"),
    ],
    "Clean Energy / EV": [
        ("TAN",  "Invesco Solar"),
        ("DRIV", "Global X Autonomous & EV"),
        ("ICLN", "iShares Clean Energy"),
        ("LIT",  "Global X Lithium"),
        ("URA",  "Global X Uranium"),
    ],
    "Energy": [
        ("OIH",  "VanEck Oil Services"),
        ("XLE",  "Energy Select Sector"),
        ("XOP",  "SPDR Oil & Gas Exploration"),
    ],
    "Space": [
        ("UFO",  "Procure Space ETF"),
    ],
    "Industrials": [
        ("IYT",  "iShares Transportation"),
        ("XLI",  "Industrials Select Sector"),
        ("ITA",  "iShares Aerospace & Defense"),
        ("PAVE", "Global X Infrastructure"),
    ],
    "Materials": [
        ("GDX",  "VanEck Gold Miners"),
        ("SIL",  "Global X Silver Miners"),
        ("XLB",  "Materials Select Sector"),
        ("REMX", "VanEck Rare Earth"),
    ],
    "Consumer Discretionary": [
        ("XRT",  "SPDR Retail"),
        ("XLY",  "Consumer Discr Select Sector"),
        ("PEJ",  "Invesco Leisure & Entertainment"),
        ("ITB",  "iShares Homebuilders"),
    ],
    "Consumer Staples": [
        ("MOO",  "VanEck Agribusiness"),
        ("DBA",  "Invesco Agriculture"),
        ("XLP",  "Consumer Staples Select Sector"),
        ("PBS",  "Invesco Dynamic Media"),
        ("PBJ",  "Invesco Food & Beverage"),
        ("PPH",  "VanEck Pharmaceutical"),
    ],
    "Healthcare": [
        ("XLV",  "Healthcare Select Sector"),
        ("IBB",  "iShares Biotech"),
        ("XBI",  "SPDR Biotech"),
        ("IHI",  "iShares Medical Devices"),
        ("ARKG", "ARK Genomics"),
        ("IXJ",  "iShares Global Healthcare"),
    ],
    "Financials": [
        ("XLF",  "Financials Select Sector"),
        ("KBE",  "SPDR Bank ETF"),
        ("KRE",  "SPDR Regional Banking"),
        ("KIE",  "SPDR Insurance ETF"),
    ],
    "Utilities": [
        ("VPU",  "Vanguard Utilities"),
        ("XLU",  "Utilities Select Sector"),
        ("PHO",  "Invesco Water Resources"),
    ],
    "Real Estate": [
        ("VNQ",  "Vanguard Real Estate"),
        ("IFGL", "iShares Intl Developed Real Estate"),
    ],
    "Communication / Media": [
        ("VOX",  "Vanguard Communication"),
        ("XLC",  "Communication Services Select"),
        ("METV", "Roundhill Metaverse"),
    ],

    # ── MACRO / RATES ─────────────────────────────────────────
    # Critical context for ALL options plays.
    # TLT falling = rates rising = headwind for growth stocks.
    # HYG falling = credit stress = risk-off, avoid naked calls.
    # GLD rising = fear in market = broad hedging driving up P/C ratios.
    "Macro / Rates": [
        ("TLT",  "iShares 20Y Treasury"),
        ("HYG",  "iShares High Yield Corp"),
        ("GLD",  "SPDR Gold"),
        ("SLV",  "iShares Silver"),
    ],

    # ── INTERNATIONAL / CHINA ────────────────────────────────
    # KWEB moves independently of US markets — useful for
    # uncorrelated plays when US sectors are all moving together.
    "International / China": [
        ("KWEB", "KraneShares China Internet"),
        ("FXI",  "iShares China Large Cap"),
        ("EEM",  "iShares Emerging Markets"),
    ],

    # ── HIGH VOL / SPECULATIVE ───────────────────────────────
    # These have elevated IV making them good for selling premium
    # or for large directional bets when momentum is clear.
    "High Vol / Speculative": [
        ("ARKK", "ARK Innovation"),
        ("JETS", "US Global Airlines"),
        ("XHB",  "SPDR Homebuilders"),
    ],
}

ALL_TICKERS = list(dict.fromkeys(
    t for etfs in ETF_SECTORS.values() for t, _ in etfs
))


# ============================================================
# HELPERS
# ============================================================

def calc_52w_range_pct(price, low_52w, high_52w):
    if not high_52w or high_52w == low_52w:
        return None
    return round((price - low_52w) / (high_52w - low_52w) * 100, 1)

def get_sentiment(range_pct):
    if range_pct is None: return "N/A"
    if range_pct >= 60:   return "🟢 Bullish"
    if range_pct >= 35:   return "🟡 Neutral"
    return "🔴 Bearish"

def get_pc_signal(pc_ratio, vix=None):
    if pc_ratio is None: return "N/A"
    threshold = 2.0 if (vix and vix > 35) else (1.5 if (vix and vix > 25) else 1.0)
    if pc_ratio < 0.7:        return "🟢 Bullish"
    if pc_ratio < threshold:  return "🟡 Neutral"
    return "🔴 Bearish"

def calc_composite_score(range_pct, rs_vs_spy, pc_ratio):
    if range_pct is None: return None
    range_score = float(range_pct)
    rs_score    = min(100.0, max(0.0, ((rs_vs_spy or 0) + 15) / 30 * 100))
    pc_score    = (100.0 if pc_ratio is not None and pc_ratio < 0.7 else
                   70.0  if pc_ratio is not None and pc_ratio < 1.0 else
                   40.0  if pc_ratio is not None and pc_ratio < 1.5 else
                   10.0  if pc_ratio is not None else 50.0)
    return round(0.40 * range_score + 0.35 * rs_score + 0.25 * pc_score, 1)

def vix_label(vix):
    if vix is None:   return "VIX: N/A", "grey"
    if vix < 15:      return f"VIX {vix:.1f} — Low fear", "green"
    if vix < 25:      return f"VIX {vix:.1f} — Normal", "orange"
    if vix < 35:      return f"VIX {vix:.1f} — Elevated fear", "red"
    return f"VIX {vix:.1f} — High fear ⚠️", "darkred"

def _bg(val, low, high, lo_col, hi_col, mid_col="#fef08a"):
    if val is None: return ""
    if val >= high: return f"background-color: {hi_col}"
    if val <= low:  return f"background-color: {lo_col}"
    return f"background-color: {mid_col}"


# ============================================================
# DATA FETCHING
# ============================================================

@st.cache_data(ttl=3600)
def fetch_vix():
    try:
        info = yf.Ticker("^VIX").info
        v = info.get("regularMarketPrice") or info.get("currentPrice")
        return round(float(v), 2) if v else None
    except Exception:
        return None


@st.cache_data(ttl=1800)   # 30-min cache — 1D/3D data needs to be fresh
def fetch_all_returns(tickers):
    """
    Single batch download for all ETFs + SPY.
    Returns dict: ticker -> {ret_1d, ret_3d, ret_1w, ret_1m, ret_3m, rs_vs_spy}
    One network call instead of 65 — much faster.

    Why 1D and 3D:
      In volatile markets the 1-week and 1-month picture can look fine
      while the last 1-3 days have already started rolling over.
      Catching that early is critical for options timing.
      1D = is it moving today?  3D = is there a short-term trend forming?
    """
    all_t = list(set(tickers + ["SPY"]))
    try:
        raw    = yf.download(all_t, period="6mo", auto_adjust=True, progress=False)
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw

        def safe_ret(series, n):
            s = series.dropna()
            return round((float(s.iloc[-1]) / float(s.iloc[-n]) - 1) * 100, 2) if len(s) >= n else None

        spy_1m = safe_ret(closes["SPY"], 21) if "SPY" in closes.columns else None

        results = {}
        for t in tickers:
            if t not in closes.columns:
                continue
            try:
                r1m = safe_ret(closes[t], 21)
                results[t] = {
                    "ret_1d":    safe_ret(closes[t], 1),    # today vs yesterday
                    "ret_3d":    safe_ret(closes[t], 3),    # last 3 trading days
                    "ret_1w":    safe_ret(closes[t], 5),
                    "ret_1m":    r1m,
                    "ret_3m":    safe_ret(closes[t], 63),
                    "rs_vs_spy": round(r1m - spy_1m, 2) if (r1m and spy_1m) else None,
                }
            except Exception:
                pass
        return results
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def fetch_etf_row(ticker, name, returns_data=None, vix=None):
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        price    = info.get("regularMarketPrice") or info.get("currentPrice") or 0
        low_52w  = info.get("fiftyTwoWeekLow",  0)
        high_52w = info.get("fiftyTwoWeekHigh", 0)
        range_pct = calc_52w_range_pct(price, low_52w, high_52w)

        pc_ratio = None
        try:
            dates = t.options
            if dates:
                chain = t.option_chain(dates[0])
                cv    = chain.calls["volume"].sum()
                pv    = chain.puts["volume"].sum()
                if cv > 0:
                    pc_ratio = round(pv / cv, 2)
        except Exception:
            pass

        rs_vs_spy = (returns_data or {}).get(ticker, {}).get("rs_vs_spy")
        composite = calc_composite_score(range_pct, rs_vs_spy, pc_ratio)

        return {
            "Ticker":     ticker,
            "Name":       name,
            "Price":      round(price, 2),
            "52W Range %": range_pct,
            "RS vs SPY":  rs_vs_spy,
            "Score":      composite,
            "P/C Ratio":  pc_ratio,
            "P/C Signal": get_pc_signal(pc_ratio, vix),
            "Sentiment":  get_sentiment(range_pct),
        }
    except Exception:
        return {"Ticker": ticker, "Name": name, "Price": None,
                "52W Range %": None, "RS vs SPY": None, "Score": None,
                "P/C Ratio": None, "P/C Signal": "Error", "Sentiment": "Error"}


@st.cache_data(ttl=86400)
def fetch_holdings(etf_ticker, fmp_api_key=""):
    try:
        url  = f"https://stockanalysis.com/etf/{etf_ticker.lower()}/holdings/"
        hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r    = requests.get(url, headers=hdrs, timeout=12)
        if r.status_code == 200:
            tables = pd.read_html(r.text)
            if tables:
                df = tables[0].head(15).copy()
                col_map = {}
                for c in df.columns:
                    cl = str(c).lower()
                    if "symbol" in cl or "ticker" in cl: col_map[c] = "Ticker"
                    elif "name" in cl or "company" in cl: col_map[c] = "Name"
                    elif "weight" in cl or cl == "%": col_map[c] = "Weight %"
                df = df.rename(columns=col_map)
                keep = [c for c in ["Ticker","Name","Weight %"] if c in df.columns]
                if "Ticker" in keep:
                    df = df[keep]
                    if "Weight %" in df.columns:
                        df["Weight %"] = pd.to_numeric(
                            df["Weight %"].astype(str).str.replace("%","",regex=False).str.strip(),
                            errors="coerce"
                        ).round(2)
                        df = df.sort_values("Weight %", ascending=False)
                    df["Source"] = "🟢 Live — stockanalysis.com"
                    return df.reset_index(drop=True)
    except Exception:
        pass

    if fmp_api_key:
        try:
            r    = requests.get(
                f"https://financialmodelingprep.com/api/v3/etf-holder/{etf_ticker}?apikey={fmp_api_key}",
                timeout=10
            )
            data = r.json()
            if isinstance(data, list) and data:
                df = (pd.DataFrame(data[:15])
                      .rename(columns={"asset":"Ticker","weightPercentage":"Weight %","name":"Name"}))
                df["Weight %"] = pd.to_numeric(df.get("Weight %",0), errors="coerce").round(2)
                cols = [c for c in ["Ticker","Name","Weight %"] if c in df.columns]
                df = df[cols].sort_values("Weight %", ascending=False).reset_index(drop=True)
                df["Source"] = "🟡 Live — FMP API"
                return df
        except Exception:
            pass

    return pd.DataFrame(columns=["Ticker","Name","Weight %"])


@st.cache_data(ttl=3600)
def calc_relative_strength(stock_tickers, etf_ticker, period="1mo"):
    all_t = list(set(stock_tickers + [etf_ticker]))
    try:
        raw    = yf.download(all_t, period=period, auto_adjust=True, progress=False)
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        rets   = ((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100).round(2)
        etf_r  = float(rets.get(etf_ticker, 0))
        rows   = []
        for t in stock_tickers:
            sr = rets.get(t)
            if sr is not None:
                vs = round(float(sr) - etf_r, 2)
                rows.append({
                    "Ticker": t,
                    f"Return ({period}) %": round(float(sr), 2),
                    "ETF Return %": round(etf_r, 2),
                    "vs ETF %": vs,
                    "Status": "✅ Leading" if vs > 0 else "⚠️ Lagging",
                })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def fetch_options_data(tickers):
    rows = []
    for ticker in tickers:
        try:
            t     = yf.Ticker(ticker)
            info  = t.info
            price = info.get("regularMarketPrice") or info.get("currentPrice") or 0

            hist = t.history(period="3mo")
            hv30 = None
            if len(hist) >= 30:
                lr   = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
                hv30 = round(lr.tail(30).std() * np.sqrt(252) * 100, 1)

            iv, options_volume = None, None
            try:
                dates = t.options
                if dates:
                    chain = t.option_chain(dates[0])
                    atm_c = chain.calls.iloc[(chain.calls["strike"] - price).abs().argsort()[:1]]
                    if not atm_c.empty:
                        iv = round(float(atm_c["impliedVolatility"].values[0]) * 100, 1)
                    options_volume = int(
                        chain.calls["volume"].fillna(0).sum() + chain.puts["volume"].fillna(0).sum()
                    )
            except Exception:
                pass

            iv_hv, signal = None, "N/A"
            if iv and hv30:
                iv_hv = round(iv / hv30, 2)
                signal = ("🔴 Expensive — Sell Premium" if iv_hv > 1.2 else
                          "🟢 Cheap — Buy Options"     if iv_hv < 0.8 else "🟡 Fair Value")

            earnings = "⚠️ Check manually"
            try:
                ts = info.get("earningsTimestampNext") or info.get("earningsTimestamp")
                if ts:
                    dt = pd.Timestamp(ts, unit="s")
                    if dt > pd.Timestamp.now():
                        earnings = str(dt.date())
            except Exception:
                pass
            if earnings == "⚠️ Check manually":
                try:
                    cal = t.calendar
                    if cal and "Earnings Date" in cal:
                        now, future = pd.Timestamp.now(), []
                        for d in cal["Earnings Date"]:
                            ts = pd.Timestamp(d)
                            if ts.tzinfo is not None: ts = ts.tz_localize(None)
                            if ts > now: future.append(ts)
                        if future: earnings = str(sorted(future)[0].date())
                except Exception:
                    pass
            if earnings == "⚠️ Check manually":
                try:
                    ed = t.get_earnings_dates(limit=10)
                    if ed is not None and not ed.empty:
                        now = pd.Timestamp.now()
                        idx = ed.index
                        try:    idx = idx.tz_localize(None)
                        except Exception:
                            try: idx = idx.tz_convert("UTC").tz_localize(None)
                            except Exception: pass
                        future = idx[idx > now]
                        if len(future): earnings = str(future[-1].date())
                except Exception:
                    pass

            rows.append({"Ticker": ticker, "Price": round(price,2), "IV %": iv,
                         "HV30 %": hv30, "IV / HV": iv_hv, "Signal": signal,
                         "Options Vol": options_volume, "Next Earnings": earnings})
            time.sleep(0.3)
        except Exception:
            rows.append({"Ticker": ticker, "Price": None, "IV %": None, "HV30 %": None,
                         "IV / HV": None, "Signal": "Error", "Options Vol": None, "Next Earnings": "N/A"})
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def fetch_conflict_data(ticker):
    """
    Calculates 6 indicators for conflict analysis:
    RSI, MFI (volume-weighted RSI), OBV divergence,
    % above 50-day MA, put skew, and volume 5/10/20-day.
    """
    try:
        t     = yf.Ticker(ticker)
        info  = t.info
        price = info.get("regularMarketPrice") or info.get("currentPrice") or 0
        hist  = t.history(period="6mo")
        if hist.empty or price == 0: return None

        closes, highs, lows, volumes = hist["Close"], hist["High"], hist["Low"], hist["Volume"]

        # RSI 14
        delta = closes.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rsi   = round(float((100 - 100 / (1 + gain / loss)).iloc[-1]), 1)

        # MFI 14 — RSI weighted by volume, can't be faked by thin-air price moves
        tp     = (highs + lows + closes) / 3
        mf     = tp * volumes
        pos_mf = mf.where(tp > tp.shift(1), 0.0).rolling(14).sum()
        neg_mf = mf.where(tp <= tp.shift(1), 0.0).rolling(14).sum()
        mfi    = round(float((100 - 100 / (1 + pos_mf / neg_mf.replace(0, np.nan))).iloc[-1]), 1)

        # OBV divergence over last 20 days
        obv       = (np.sign(closes.diff()) * volumes).fillna(0).cumsum()
        lb        = min(20, len(obv) - 1)
        price_up  = float(closes.iloc[-1]) > float(closes.iloc[-lb])
        obv_up    = float(obv.iloc[-1])   > float(obv.iloc[-lb])
        obv_signal = ("confirming"     if price_up and obv_up  else
                      "diverging"      if price_up and not obv_up else
                      "accumulating"   if not price_up and obv_up else "confirming_down")

        # % above 50-day MA
        ma50         = float(closes.rolling(50).mean().iloc[-1])
        pct_above_ma = round((price - ma50) / ma50 * 100, 1)

        # Put skew — ATM put IV / ATM call IV
        put_skew = None
        try:
            dates = t.options
            if dates:
                chain   = t.option_chain(dates[0])
                atm_c   = chain.calls.iloc[(chain.calls["strike"] - price).abs().argsort()[:1]]
                atm_p   = chain.puts.iloc[(chain.puts["strike"]  - price).abs().argsort()[:1]]
                civ     = float(atm_c["impliedVolatility"].values[0])
                piv     = float(atm_p["impliedVolatility"].values[0])
                if civ > 0: put_skew = round(piv / civ, 2)
        except Exception:
            pass

        # Volume vs 5 / 10 / 20-day averages
        rv = float(volumes.iloc[-1])
        def vol_ratio(n):
            return round(rv / float(volumes.tail(n).mean()), 2) if len(volumes) >= n else None

        return {
            "ticker": ticker, "rsi": rsi, "mfi": mfi, "obv_signal": obv_signal,
            "pct_above_ma": pct_above_ma, "put_skew": put_skew,
            "vol5": vol_ratio(5), "vol10": vol_ratio(10), "vol20": vol_ratio(20),
        }
    except Exception:
        return None


def interpret_conflict(data, vix=None):
    """Returns plain-English cards and overall conclusion for the conflict panel."""
    if not data: return None

    rsi, mfi      = data["rsi"], data["mfi"]
    obv_signal    = data["obv_signal"]
    pct_above_ma  = data["pct_above_ma"]
    put_skew      = data["put_skew"]
    vol5, vol10, vol20 = data["vol5"], data["vol10"], data["vol20"]
    warnings = 0
    cards    = []

    # ── RSI ──────────────────────────────────────────────────
    if rsi >= 75:
        cards.append(("🔴","RSI",f"{rsi} — Overbought",
            "Price has risen too far too fast. Momentum is stretched. "
            "Heavy put buying here is a genuine warning — not routine hedging. "
            "A pullback is increasingly likely.")); warnings += 1
    elif rsi >= 60:
        cards.append(("🟡","RSI",f"{rsi} — Elevated",
            "Momentum is firm but not extreme. Put buying at this level "
            "could still be cautious hedging by long holders."))
    else:
        cards.append(("🟢","RSI",f"{rsi} — Not overbought",
            "No momentum excess. The high P/C ratio is most likely "
            "routine protection buying, not a directional warning."))

    # ── MFI ──────────────────────────────────────────────────
    if mfi >= 80:
        cards.append(("🔴","MFI",f"{mfi} — Overbought (volume-weighted)",
            "Unlike RSI, MFI weights momentum by volume — it can't be fooled by "
            "price rising on thin air. Above 80 means buyers are genuinely stretched "
            "even accounting for actual money flowing in. This strengthens the bearish put signal."
        )); warnings += 1
    elif mfi >= 60:
        cards.append(("🟡","MFI",f"{mfi} — Elevated",
            "Volume-weighted momentum is firm but not extreme. Worth monitoring."))
    elif mfi <= 20:
        cards.append(("🟢","MFI",f"{mfi} — Oversold (volume-weighted)",
            "Despite the high P/C ratio, volume-weighted momentum is actually weak. "
            "Put buying here may be badly timed — a bounce is possible."))
    else:
        cards.append(("🟢","MFI",f"{mfi} — Normal",
            "Volume-weighted momentum is healthy. No distribution signal here."))

    # ── OBV ──────────────────────────────────────────────────
    if obv_signal == "diverging":
        cards.append(("🔴","OBV","Bearish divergence — price up, volume out",
            "On-Balance Volume is falling while price is rising. "
            "More volume is occurring on down days than up days — sellers are more active "
            "than buyers even as price holds high. "
            "This is one of the clearest distribution signals available."
        )); warnings += 1
    elif obv_signal == "confirming":
        cards.append(("🟢","OBV","Confirming the move",
            "OBV is rising alongside price — volume is on the up days. "
            "Real buyers are participating. Put buying is likely just hedging."))
    elif obv_signal == "accumulating":
        cards.append(("🟢","OBV","Bullish accumulation beneath the surface",
            "OBV is rising even though price has dipped — buyers quietly accumulating. "
            "The conflict is likely a false alarm."))
    else:
        cards.append(("🟡","OBV","Confirming weakness",
            "Both price and OBV falling together — a clean downtrend. "
            "Put buying reflects the existing trend."))

    # ── % above 50MA ─────────────────────────────────────────
    if pct_above_ma >= 15:
        cards.append(("🔴","50-Day MA",f"{pct_above_ma:+.1f}% above — Very stretched",
            f"Price is {pct_above_ma:.1f}% above its 50-day moving average — like a rubber band "
            "pulled very tight. When large investors buy heavy puts while price is this extended, "
            "it often signals **distribution**: they are quietly selling their shares to retail "
            "buyers still chasing the move. Price holds high because buyers keep arriving — "
            "but the smart money is already leaving."
        )); warnings += 1
    elif pct_above_ma >= 7:
        cards.append(("🟡","50-Day MA",f"{pct_above_ma:+.1f}% above — Moderately stretched",
            "Some distance from the average but not extreme enough to signal distribution on its own."))
    elif pct_above_ma < 0:
        cards.append(("🟢","50-Day MA",f"{pct_above_ma:+.1f}% — Below average",
            "Price is below its 50-day average — no overextension. "
            "The put buying may be a lagging response to prior weakness."))
    else:
        cards.append(("🟢","50-Day MA",f"{pct_above_ma:+.1f}% above — Not stretched",
            "Price is close to its moving average. Overextension is not the cause of this conflict."))

    # ── Put Skew ─────────────────────────────────────────────
    if put_skew is not None:
        if put_skew >= 1.3:
            cards.append(("🔴","Put Skew",f"{put_skew:.2f}x — Significant",
                f"The market is paying {put_skew:.2f}x more for downside protection than for "
                "equivalent upside exposure. This is genuine institutional fear, not routine hedging. "
                "Large players are specifically pricing in a downside scenario."
            )); warnings += 1
        elif put_skew >= 1.1:
            cards.append(("🟡","Put Skew",f"{put_skew:.2f}x — Mild",
                "A slight premium for puts but not alarming. Some caution without serious conviction."))
        else:
            cards.append(("🟢","Put Skew",f"{put_skew:.2f}x — Neutral",
                "Puts and calls are priced similarly. High P/C volume is likely hedging."))
    else:
        cards.append(("⚪","Put Skew","Could not fetch",
            "Check your broker's options chain for put vs call implied volatility."))

    # ── Volume 5 / 10 / 20 ───────────────────────────────────
    # Three windows give you a TREND, not just a snapshot.
    # 20-day alone can be inflated by a volatile spike weeks ago —
    # making today's volume look falsely low. The three together show direction.
    def _vi(r): return "🟢" if r and r >= 0.9 else ("🟡" if r and r >= 0.7 else "🔴")
    def _vl(r, label): return f"  • {label}: {r:.2f}x  {_vi(r)}" if r else f"  • {label}: N/A"

    vol_lines = "\n".join([_vl(vol5,"5-day avg "), _vl(vol10,"10-day avg"), _vl(vol20,"20-day avg")])
    vol_warn  = False

    if vol10 and vol10 < 0.8 and vol20 and vol20 < 0.8:
        detail = (
            f"🔴 Volume fading for 2+ weeks while price stays high.\n\n{vol_lines}\n\n"
            "This is a classic distribution pattern: fewer buyers are showing up to push price "
            "higher, but sellers haven't yet pushed it down. "
            "Both the 10-day and 20-day below 0.8 confirms this is not a one-day blip — "
            "the buying pressure has been fading for at least two weeks."
        )
        warnings += 1; vol_warn = True
    elif vol5 and vol5 >= 1.0 and vol20 and vol20 < 0.8:
        detail = (
            f"🟡 Volume recovering this week after a fading period.\n\n{vol_lines}\n\n"
            "The 5-day is healthy but the 20-day baseline is still below normal. "
            "Watch whether this week's pickup is sustained — a genuine recovery in "
            "buying pressure would reduce the distribution concern."
        )
    elif all(v is not None and v >= 0.9 for v in [vol5, vol10, vol20] if v is not None):
        detail = (
            f"🟢 Volume healthy across all three windows.\n\n{vol_lines}\n\n"
            "Buyers are consistently participating. The put buying is most likely "
            "hedging, not a distribution warning."
        )
    else:
        detail = vol_lines or "Insufficient data."

    cards.append(("🔴" if vol_warn else "🟢", "Volume (5 / 10 / 20-day)", "", detail))

    # VIX note
    vix_note = (
        f"\n\n> **VIX context ({vix:.1f}):** In an elevated-fear environment, P/C ratios rise "
        "across the whole market as everyone buys general insurance puts. Some of the bearish "
        "put signal here is market-wide hedging, not specific to this ETF. "
        "The indicators above help you separate the two."
    ) if (vix and vix > 25) else ""

    # Conclusion
    if warnings >= 4:
        conclusion = ("🚨 **Strong Distribution Warning** — Four or more indicators align with "
            "the bearish put signal. Large investors appear to be selling into strength. "
            "The 52W range reflects where price HAS been, not where it is going. "
            "Avoid new long entries. If already long, consider protective puts or reducing size." + vix_note)
    elif warnings == 3:
        conclusion = ("🚨 **Distribution Likely** — Three indicators confirm the bearish put signal. "
            "Use defined-risk strategies only (spreads), not naked long calls. "
            "Wait for a pullback before entering." + vix_note)
    elif warnings == 2:
        conclusion = ("⚠️ **Genuine Caution** — Two indicators back up the bearish put signal. "
            "Be selective — wait for a pullback or use spreads rather than naked long calls." + vix_note)
    elif warnings == 1:
        conclusion = ("🟡 **Mixed Signal** — One indicator is flashing but others are fine. "
            "Monitor the flagged indicator over the next few days before acting." + vix_note)
    else:
        conclusion = ("✅ **Likely Routine Hedging** — The indicators don't support distribution. "
            "Large holders near the 52W high are simply protecting gains. "
            "The bullish trend is still intact — the conflict is not a serious warning." + vix_note)

    return {"cards": cards, "conclusion": conclusion, "warnings": warnings}


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("⚙️ Settings")
    fmp_key = st.text_input("FMP API Key (optional)", type="password",
        help="Free at financialmodelingprep.com — enables live holdings in Step 2.")
    st.divider()

    st.markdown("**📡 Live VIX**")
    vix = fetch_vix()
    lbl, col = vix_label(vix)
    st.markdown(f"<span style='color:{col}; font-weight:bold'>{lbl}</span>",
                unsafe_allow_html=True)
    if vix and vix > 25:
        st.caption("High VIX → P/C conflict thresholds automatically raised.")
    st.divider()

    st.markdown("**52W Range %**")
    st.markdown("🟢 ≥60% Strong  🟡 35–60% Mid  🔴 <35% Weak")
    st.divider()

    st.markdown("**Composite Score (0–100)**")
    st.markdown("🟢 ≥65 Strong  🟡 40–65 Mixed  🔴 <40 Weak")
    st.caption("40% 52W Range + 35% RS vs SPY + 25% P/C signal")
    st.divider()

    st.markdown("**RS vs SPY (1 Month)**")
    st.markdown("🟢 >+3% Outperforming  🟡 ±3% In line  🔴 <-3% Lagging")
    st.divider()

    st.markdown("**P/C Signal**")
    st.markdown("🟢 <0.7 Bullish  🟡 Neutral  🔴 Bearish")
    st.caption("Bearish threshold rises automatically when VIX is elevated.")
    st.divider()

    st.markdown("**IV Signal (Step 3)**")
    st.markdown("🟢 IV/HV <0.8 Buy  🟡 0.8–1.2 Fair  🔴 >1.2 Sell premium")

    st.divider()
    st.markdown("**➕ Add Custom ETFs to Step 1**")
    st.caption(
        "Type any ETF tickers here to add them to the screener. "
        "Useful for ETFs not in the default list, "
        "or to quickly check a specific ETF you have in mind."
    )
    custom_input = st.text_input(
        "Extra tickers (comma separated)",
        placeholder="e.g. ARKK, HACK, MSOS",
        key="custom_tickers",
    )
    if custom_input:
        custom_tickers = [t.strip().upper() for t in custom_input.split(",") if t.strip()]
        st.caption(f"Will scan: {', '.join(custom_tickers)}")
    else:
        custom_tickers = []


# ============================================================
# MAIN
# ============================================================
st.title("📊 ETF Options Trading Dashboard")
st.caption("**Step 1** → Find strong sectors  |  **Step 2** → Holdings drill-down  |  **Step 3** → Options filter")

tab1, tab2, tab3 = st.tabs([
    "📈 Step 1 — Sector Screener",
    "🔍 Step 2 — Holdings Drill-Down",
    "⚡ Step 3 — Options Filter",
])

# Session state — lets Top Picks cards pre-fill the Step 2 dropdowns
if "drill_sector" not in st.session_state:
    st.session_state["drill_sector"] = None
if "drill_ticker" not in st.session_state:
    st.session_state["drill_ticker"] = None


# ============================================================
# TAB 1
# ============================================================
with tab1:
    st.subheader("ETF Sector Screener")
    st.caption("⚡ = conflict between price strength and put/call ratio — click to analyse")

    col_a, col_b = st.columns([3, 1])
    with col_a:
        selected_sectors = st.multiselect("Sectors to show",
            list(ETF_SECTORS.keys()), default=list(ETF_SECTORS.keys()))
    with col_b:
        sentiment_filter = st.selectbox("Filter Sentiment",
            ["All", "Bullish", "Neutral", "Bearish"])

    if st.button("🔄 Load / Refresh Data", key="btn_step1"):

        with st.spinner("Downloading price history for all ETFs..."):
            returns_data = fetch_all_returns(ALL_TICKERS)

        # ── Sector Rotation Heatmap ───────────────────────────
        if returns_data:
            st.subheader("🌡️ Sector Rotation Heatmap")
            st.caption(
                "1W / 1M / 3M returns + RS vs SPY for every ETF. "
                "Sectors accelerating = getting greener left to right. "
                "Sectors stalling = green on left, fading on right."
            )
            hm_rows = []
            for sector, etfs in ETF_SECTORS.items():
                for ticker, _ in etfs:
                    if ticker in returns_data:
                        d = returns_data[ticker]
                        hm_rows.append({
                            "Sector":     sector,
                            "Ticker":     ticker,
                            "1D %":       d.get("ret_1d"),
                            "3D %":       d.get("ret_3d"),
                            "1W %":       d.get("ret_1w"),
                            "1M %":       d.get("ret_1m"),
                            "3M %":       d.get("ret_3m"),
                            "RS vs SPY":  d.get("rs_vs_spy"),
                        })
            hm_df = pd.DataFrame(hm_rows).dropna(subset=["1D %","1W %","1M %"], how="all")

            if not hm_df.empty:
                def _hm(val):
                    if pd.isna(val): return ""
                    if val >= 5:   return "background-color:#166534;color:white"
                    if val >= 2:   return "background-color:#bbf7d0"
                    if val >= -2:  return "background-color:#fef08a"
                    if val >= -5:  return "background-color:#fecaca"
                    return "background-color:#991b1b;color:white"

                num_cols = ["1D %","3D %","1W %","1M %","3M %","RS vs SPY"]
                st.caption(
                    "**Reading the heatmap in volatile markets:** "
                    "Look left to right — if 1D and 3D are green but 1M is red, "
                    "the sector is recovering. If 1D/3D are red but 1M is green, "
                    "the sector may be topping out. "
                    "The most actionable plays have green across ALL columns."
                )
                st.dataframe(
                    hm_df.style.map(_hm, subset=num_cols)
                    .format({c: "{:+.1f}%" for c in num_cols}, na_rep="N/A"),
                    use_container_width=True, hide_index=True, height=400,
                )
            st.divider()

        # ── Top Picks panel ──────────────────────────────────
        # Scans every ETF across every sector and surfaces the top 5
        # options opportunities based on composite score + quality filters.
        # Appears before the sector tables so you can act without scrolling.

        st.subheader("🎯 Best for Options Right Now")
        st.caption(
            "Top-ranked ETFs that pass all quality filters: "
            "strong momentum, beating SPY, P/C not heavily bearish, "
            "no distribution warning. "
            "Click **Select →** on any card — the Step 2 dropdowns will auto-fill. "
            "Then click the **Step 2** tab."
        )

        # Show currently selected ETF as a banner
        _sel = st.session_state.get("drill_ticker")
        _sel_sector = st.session_state.get("drill_sector")
        if _sel:
            st.success(
                f"✅ **{_sel}** ({_sel_sector}) is selected for drill-down. "
                "Click the **🔍 Step 2 — Holdings Drill-Down** tab above, "
                "then click **Drill Down** — it will be pre-filled."
            )

        with st.spinner("Scanning all ETFs for top picks..."):
            picks_rows = []
            for sector, etfs in ETF_SECTORS.items():
                for ticker, name in etfs:
                    if ticker == "SPY":
                        continue
                    row = fetch_etf_row(ticker, name, returns_data=returns_data, vix=vix)
                    row["Sector"] = sector
                    picks_rows.append(row)
            # Also scan any custom tickers added in the sidebar
            for ticker in custom_tickers:
                if not any(r["Ticker"] == ticker for r in picks_rows):
                    row = fetch_etf_row(ticker, ticker, returns_data=returns_data, vix=vix)
                    row["Sector"] = "📌 Custom"
                    picks_rows.append(row)

        if picks_rows:
            picks_df = pd.DataFrame(picks_rows)

            # ── Quality filter ────────────────────────────────
            # Must pass ALL of these to surface as a top pick
            filtered = picks_df[
                (picks_df["Score"].fillna(0)        >= 60)   &   # strong composite
                (picks_df["RS vs SPY"].fillna(-99)  >= 0)    &   # beating the market
                (picks_df["52W Range %"].fillna(0)  >= 55)   &   # near annual high
                (~picks_df["P/C Signal"].str.contains("Bearish", na=False))  # P/C not bearish
            ].copy()

            # ── Sort by composite score ───────────────────────
            filtered = filtered.sort_values("Score", ascending=False).head(5)

            if filtered.empty:
                st.info(
                    "No ETFs currently pass all quality filters. "
                    "This typically happens during broad market weakness or high VIX. "
                    "Check the sector tables below for the best available options."
                )
            else:
                # ── Render one card per top pick ─────────────
                for rank, (_, r) in enumerate(filtered.iterrows(), 1):
                    ticker  = r["Ticker"]
                    sector  = r["Sector"]
                    score   = r["Score"]
                    rng     = r["52W Range %"]
                    rs      = r["RS vs SPY"]
                    pc_sig  = r["P/C Signal"]
                    pc_val  = r["P/C Ratio"]
                    price   = r["Price"]

                    medals = {1:"🥇", 2:"🥈", 3:"🥉", 4:"4️⃣", 5:"5️⃣"}
                    medal  = medals.get(rank, "▶")

                    # Score bar — convert 0-100 to filled blocks
                    filled = int(round(score / 10))
                    bar    = "█" * filled + "░" * (10 - filled)

                    # Build signal tags
                    tags = []
                    tags.append(f"✅ 52W Range {rng:.1f}%")
                    tags.append(f"✅ RS vs SPY {rs:+.1f}%")
                    tags.append(f"✅ {pc_sig}")

                    # Plain-English why this pick
                    if rs >= 5 and rng >= 80:
                        reason = (
                            f"**{ticker}** is one of the strongest ETFs in the market right now — "
                            f"near its annual high and running {rs:+.1f}% ahead of SPY. "
                            "The holdings in this ETF are where institutional money is flowing. "
                            "Drill down to find the leading stocks."
                        )
                    elif rs >= 2 and rng >= 65:
                        reason = (
                            f"**{ticker}** has solid momentum and is outperforming the market. "
                            f"At {rng:.1f}% of its 52W range with no bearish options signal, "
                            "this sector has clear directional conviction worth following into individual names."
                        )
                    else:
                        reason = (
                            f"**{ticker}** passes all quality filters with a composite score of {score:.0f}. "
                            "Momentum is positive and the options market is not flagging concern. "
                            "Worth drilling into for individual stock opportunities."
                        )

                    with st.container(border=True):
                        col_rank, col_info, col_btn = st.columns([0.5, 5, 1.5])

                        with col_rank:
                            st.markdown(f"## {medal}")

                        with col_info:
                            st.markdown(
                                f"**{ticker}** &nbsp;&nbsp; "
                                f"<span style='color:gray'>{sector}</span> &nbsp;&nbsp; "
                                f"${price:.2f}",
                                unsafe_allow_html=True
                            )
                            st.markdown(
                                f"`{bar}` &nbsp; Score **{score:.0f} / 100**",
                                unsafe_allow_html=True
                            )
                            st.markdown("  ".join(tags))
                            st.markdown(reason)

                        with col_btn:
                            st.markdown("&nbsp;", unsafe_allow_html=True)
                            # Store selection — Step 2 dropdowns will auto-select this ETF
                            if st.button(
                                "Select →",
                                key=f"pick_drill_{ticker}",
                                use_container_width=True,
                                type="primary",
                            ):
                                st.session_state["drill_sector"] = sector
                                st.session_state["drill_ticker"] = ticker
                                st.rerun()

        st.divider()

        # ── Per-sector tables ─────────────────────────────────
        all_rows = []

        for sector in selected_sectors:
            etfs        = ETF_SECTORS[sector]
            sector_rows = []
            bar = st.progress(0, text=f"Fetching {sector}...")
            for i, (ticker, name) in enumerate(etfs):
                row = fetch_etf_row(ticker, name, returns_data=returns_data, vix=vix)
                sector_rows.append(row)
                bar.progress((i+1)/len(etfs), text=f"Fetching {sector}...")
                time.sleep(0.1)
            bar.empty()

            df_sector = pd.DataFrame(sector_rows)
            if sentiment_filter != "All":
                df_sector = df_sector[df_sector["Sentiment"].str.contains(sentiment_filter, na=False)]
            if df_sector.empty:
                continue

            all_rows.extend(sector_rows)
            st.markdown(f"### {sector}  —  {len(df_sector)} ETF(s)")

            def _style(row):
                styles = [""] * len(row)
                idx_map = {c: i for i, c in enumerate(row.index)}
                for col, fn in [("52W Range %", lambda v: _bg(v,35,60,"#fecaca","#bbf7d0")),
                                 ("RS vs SPY",  lambda v: _bg(v,-3,3,"#fecaca","#bbf7d0")),
                                 ("Score",       lambda v: _bg(v,40,65,"#fecaca","#bbf7d0"))]:
                    if col in idx_map and pd.notna(row.get(col)):
                        styles[idx_map[col]] = fn(row[col])
                return styles

            display_cols = ["Ticker","Name","Price","52W Range %","RS vs SPY","Score","P/C Ratio","P/C Signal","Sentiment"]
            display_df   = df_sector[[c for c in display_cols if c in df_sector.columns]]

            st.dataframe(
                display_df.style.apply(_style, axis=1).format({
                    "Price":       "${:.2f}",
                    "52W Range %": lambda v: f"{v:.1f}%" if v is not None else "N/A",
                    "RS vs SPY":   lambda v: f"{v:+.2f}%" if v is not None else "N/A",
                    "Score":       lambda v: f"{v:.1f}" if v is not None else "N/A",
                    "P/C Ratio":   lambda v: f"{v:.2f}" if v is not None else "N/A",
                }, na_rep="N/A"),
                use_container_width=True, hide_index=True,
            )

            # ── Conflict panels ───────────────────────────────
            conflicts = df_sector[
                (df_sector["52W Range %"].fillna(0) >= 60) &
                (df_sector["P/C Signal"].str.contains("Bearish", na=False))
            ]
            for _, row in conflicts.iterrows():
                ticker = row["Ticker"]
                pc     = row["P/C Ratio"]
                rng    = row["52W Range %"]
                score  = row.get("Score")
                rs     = row.get("RS vs SPY")

                with st.expander(
                    f"⚡ Conflict — **{ticker}**  "
                    f"| 52W Range {rng:.1f}%  "
                    f"| P/C {pc:.2f} Bearish  "
                    f"| Score {score:.1f}  "
                    f"{'| RS vs SPY ' + f'{rs:+.1f}%' if rs is not None else ''}  "
                    "— click to analyse",
                    expanded=False,
                ):
                    with st.spinner(f"Fetching conflict indicators for {ticker}..."):
                        cdata  = fetch_conflict_data(ticker)
                        interp = interpret_conflict(cdata, vix=vix)

                    if not interp:
                        st.warning("Could not fetch data — try again in a moment.")
                    else:
                        st.markdown(
                            f"**What is happening:** {ticker} is near its 52-week high "
                            f"(52W Range **{rng:.1f}%**) which looks bullish. But the "
                            f"options market has a P/C ratio of **{pc:.2f}** — meaning "
                            f"{pc:.1f}x more puts than calls are being bought — which is bearish. "
                            "The 6 indicators below explain whether this is genuine distribution "
                            "or just routine hedging by long holders protecting gains."
                        )
                        st.divider()

                        cols3 = st.columns(3)
                        for i, (icon, label, headline, detail) in enumerate(interp["cards"]):
                            with cols3[i % 3]:
                                hdr = f"{icon} **{label}**"
                                if headline: hdr += f" — *{headline}*"
                                st.markdown(hdr)
                                st.markdown(detail)
                                st.markdown("")

                        st.divider()
                        st.markdown("### 🎯 Overall Interpretation")
                        st.markdown(interp["conclusion"])

        # ── Custom tickers section ───────────────────────────
        if custom_tickers:
            st.markdown("### 📌 Custom ETFs")
            custom_rows = []
            bar = st.progress(0, text="Fetching custom tickers...")
            for i, ticker in enumerate(custom_tickers):
                row = fetch_etf_row(ticker, ticker, returns_data=returns_data, vix=vix)
                custom_rows.append(row)
                all_rows.append(row)
                bar.progress((i+1)/len(custom_tickers), text=f"Fetching {ticker}...")
                time.sleep(0.1)
            bar.empty()
            custom_df = pd.DataFrame(custom_rows)
            display_cols = ["Ticker","Name","Price","52W Range %","RS vs SPY","Score","P/C Ratio","P/C Signal","Sentiment"]
            custom_display = custom_df[[c for c in display_cols if c in custom_df.columns]]
            st.dataframe(custom_display, use_container_width=True, hide_index=True)

        # ── Bar chart ─────────────────────────────────────────
        if all_rows:
            st.divider()
            st.subheader("📊 52-Week Range — All ETFs")
            all_df = (pd.DataFrame(all_rows).dropna(subset=["52W Range %"])
                      .sort_values("52W Range %", ascending=True))
            all_df["Zone"] = all_df["52W Range %"].apply(
                lambda v: "Strong (≥60%)" if v >= 60 else ("Mid (35–60%)" if v >= 35 else "Weak (<35%)")
            )
            fig = px.bar(
                all_df, x="52W Range %", y="Ticker", color="Zone", orientation="h",
                color_discrete_map={"Strong (≥60%)":"#22c55e","Mid (35–60%)":"#eab308","Weak (<35%)":"#ef4444"},
                text="52W Range %",
                hover_data=["Name","Price","Score","RS vs SPY","P/C Signal"],
                height=max(500, len(all_df) * 22),
                title="ETF Position in 52-Week Range  (100 = at 52W High · 0 = at 52W Low)",
            )
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(xaxis_range=[0,125], xaxis_title="Position in 52-Week Range (%)")
            st.plotly_chart(fig, use_container_width=True)


# ============================================================
# TAB 2
# ============================================================
with tab2:
    st.subheader("ETF Holdings Drill-Down")
    st.caption("See top holdings and which stocks are leading vs lagging the ETF.")

    # Pre-fill from Top Picks if user clicked Drill Down there
    _default_sector = st.session_state.get("drill_sector")
    _default_ticker = st.session_state.get("drill_ticker")
    sector_names    = list(ETF_SECTORS.keys())
    sector_idx      = sector_names.index(_default_sector) if _default_sector in sector_names else 0

    col_c, col_d = st.columns(2)
    with col_c:
        sector_choice = st.selectbox("Sector", sector_names, index=sector_idx, key="s2_sector")
    with col_d:
        etf_labels = [f"{t}  —  {n}" for t, n in ETF_SECTORS[sector_choice]]
        # find default index for the ticker if set
        etf_tickers_only = [t for t, _ in ETF_SECTORS[sector_choice]]
        etf_idx    = etf_tickers_only.index(_default_ticker) if _default_ticker in etf_tickers_only else 0
        etf_choice = st.selectbox("ETF", etf_labels, index=etf_idx, key="s2_etf")
        etf_ticker = etf_choice.split("  —  ")[0].strip()

    period = st.radio("Comparison period", ["1wk","1mo","3mo"], index=1, horizontal=True, key="s2_period")

    if st.button("🔍 Drill Down", key="btn_step2"):
        with st.spinner(f"Loading {etf_ticker} holdings..."):
            holdings = fetch_holdings(etf_ticker, fmp_key)

        if holdings.empty:
            st.error(f"⚠️ Could not fetch live holdings for **{etf_ticker}**")
            st.markdown("**Look it up here and paste the tickers into Step 3:**")
            c1, c2 = st.columns(2)
            with c1:
                st.link_button(f"🔍 stockanalysis.com — {etf_ticker}",
                    f"https://stockanalysis.com/etf/{etf_ticker.lower()}/holdings/",
                    use_container_width=True)
            with c2:
                st.link_button(f"🔍 ETF Database — {etf_ticker}",
                    f"https://etfdb.com/etf/{etf_ticker}/#holdings",
                    use_container_width=True)
            st.info("Copy the top 10 tickers, then paste them into Step 3.")
        else:
            tickers_list = holdings["Ticker"].tolist()
            with st.spinner("Calculating relative strength vs ETF..."):
                rs_df = calc_relative_strength(tickers_list, etf_ticker, period=period)

            merged = (holdings.merge(
                rs_df[["Ticker", f"Return ({period}) %","vs ETF %","Status"]], on="Ticker", how="left"
            ) if not rs_df.empty else holdings.copy())

            if "Source" in merged.columns:
                st.caption(merged["Source"].iloc[0])

            def _sh(row):
                styles = [""] * len(row)
                if "Status" in row.index:
                    i = list(row.index).index("Status")
                    styles[i] = ("background-color:#bbf7d0" if row["Status"] == "✅ Leading"
                                 else "background-color:#fecaca" if row["Status"] == "⚠️ Lagging" else "")
                return styles

            st.markdown(f"#### Top Holdings of **{etf_ticker}**")
            st.dataframe(merged.style.apply(_sh, axis=1), use_container_width=True, hide_index=True)

            if not rs_df.empty:
                st.markdown(f"#### Returns vs {etf_ticker}  ({period})")
                rs_s = rs_df.sort_values("vs ETF %")
                rs_s["Col"] = rs_s["vs ETF %"].apply(lambda v: "Leading" if v > 0 else "Lagging")
                fig2 = px.bar(rs_s, x="vs ETF %", y="Ticker", color="Col", orientation="h",
                    color_discrete_map={"Leading":"#22c55e","Lagging":"#ef4444"},
                    text="vs ETF %", height=max(300, len(rs_s)*38))
                fig2.update_traces(texttemplate="%{text:+.2f}%", textposition="outside")
                fig2.add_vline(x=0, line_dash="dash", line_color="gray")
                fig2.update_layout(xaxis_title=f"Return vs {etf_ticker} (%)", showlegend=False)
                st.plotly_chart(fig2, use_container_width=True)

            leading = (merged[merged["Status"] == "✅ Leading"]["Ticker"].tolist()
                       if "Status" in merged.columns else tickers_list)
            if leading:
                st.success(f"✅ Leading stocks: **{', '.join(leading)}**")
                st.info("👉 Copy these tickers into **Step 3** to check options suitability.")


# ============================================================
# TAB 3
# ============================================================
with tab3:
    st.subheader("Options Suitability Filter")
    st.caption("Paste in the leading stocks from Step 2.")

    ticker_input = st.text_input("Tickers (comma separated)", placeholder="e.g.  NVDA, AMD, AVGO")

    if st.button("⚡ Analyse", key="btn_step3") and ticker_input:
        raw_tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]

        with st.spinner(f"Fetching options data for {', '.join(raw_tickers)}..."):
            opt_df = fetch_options_data(raw_tickers)

        if opt_df.empty:
            st.error("Could not fetch data. Check your tickers and try again.")
        else:
            st.markdown("#### Options Data")

            def _so(row):
                styles = [""] * len(row)
                if "Signal" in row.index:
                    i   = list(row.index).index("Signal")
                    sig = str(row["Signal"])
                    styles[i] = ("background-color:#bbf7d0" if "Cheap"     in sig else
                                 "background-color:#fecaca" if "Expensive" in sig else
                                 "background-color:#fef08a" if "Fair"      in sig else "")
                return styles

            st.dataframe(opt_df.style.apply(_so, axis=1), use_container_width=True, hide_index=True)

            st.markdown("#### ⚠️ Earnings Risk")
            shown, check_manual = False, []
            for _, row in opt_df.iterrows():
                s = str(row["Next Earnings"])
                if "Check manually" in s:
                    check_manual.append(row["Ticker"]); continue
                try:
                    days = (pd.to_datetime(s) - pd.Timestamp.now()).days
                    if 0 <= days <= 21:
                        st.warning(f"**{row['Ticker']}** — earnings in **{days} days** ({s}).  "
                                   "IV will spike into this date — be careful with long options.")
                        shown = True
                    elif days > 21:
                        st.success(f"**{row['Ticker']}** — next earnings {s} ({days} days away) ✅")
                        shown = True
                except Exception:
                    check_manual.append(row["Ticker"])

            if check_manual:
                st.error(f"**Could not fetch earnings date for: {', '.join(check_manual)}** — "
                         "check [Earnings Whispers](https://www.earningswhispers.com) before trading.")
                shown = True
            if not shown:
                st.success("No earnings within 21 days for the tickers checked. ✅")

            st.markdown("#### 🎯 Summary")
            c1, c2 = st.columns(2)
            with c1:
                bl = opt_df[opt_df["Signal"].str.contains("Cheap|Fair", na=False)]["Ticker"].tolist()
                if bl:
                    st.success(f"**Best for buying options:**\n\n{', '.join(bl)}\n\n"
                               "(IV not expensive relative to actual movement)")
            with c2:
                sl = opt_df[opt_df["Signal"].str.contains("Expensive", na=False)]["Ticker"].tolist()
                if sl:
                    st.info(f"**Consider selling premium:**\n\n{', '.join(sl)}\n\n"
                            "(IV elevated vs HV30)")
