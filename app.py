# ============================================================
# ETF OPTIONS DASHBOARD
# ============================================================
# Workflow:
#   Step 1 → Spot which ETF subsectors are moving
#   Step 2 → Drill into ETF holdings, find leading stocks
#   Step 3 → Check those stocks for options suitability
#
# Data sources (all free, no API key required except FMP
# for live holdings — see sidebar):
#   • yfinance  → prices, 52W range, options chains
#   • FMP API   → ETF holdings (free at financialmodelingprep.com)
# ============================================================

import time
import requests
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# ── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="ETF Options Dashboard",
    page_icon="📊",
    layout="wide"
)

# ============================================================
# ETF UNIVERSE  ← YOUR EXACT ETF LIST FROM YOUR DASHBOARD
# ============================================================
# HOW TO EDIT THIS:
#   • To ADD an ETF:    copy any line and change the ticker + name
#   • To REMOVE an ETF: delete that line
#   • To ADD a SECTOR:  copy an entire block and change the name
#
# Format for each ETF line:
#   ("TICKER",  "Full Name"),
#
# The ticker MUST match Yahoo Finance exactly (e.g. "SPY" not "spy")
# ============================================================
ETF_SECTORS = {

    # ── BROAD MARKET ─────────────────────────────────────────
    "Broad Market": [
        ("IVV",  "iShares S&P 500"),
        ("VTI",  "Vanguard Total Market"),
        ("VOO",  "Vanguard S&P 500"),
        ("SPY",  "SPDR S&P 500"),
        ("IWM",  "iShares Russell 2000"),       # ← added: small cap breadth signal
    ],

    # ── NASDAQ / GROWTH ──────────────────────────────────────
    "Nasdaq / Growth": [
        ("QQQ",  "Invesco QQQ"),
        ("AMOM", "QRAFT AI Momentum"),
    ],

    # ── TECHNOLOGY ───────────────────────────────────────────
    "Technology": [
        ("SKYY", "First Trust Cloud"),
        ("XLK",  "Tech Select Sector"),
        ("CIBR", "First Trust Cybersecurity"),
        ("IYW",  "iShares US Technology"),
        ("IGV",  "iShares Software"),
        ("SOCL", "Global X Social Media"),
    ],

    # ── SEMICONDUCTORS ───────────────────────────────────────
    "Semiconductors": [
        ("SMH",  "VanEck Semiconductors"),
        ("SOXX", "iShares Semiconductors"),
    ],

    # ── ROBOTICS / AI ────────────────────────────────────────
    "Robotics / AI": [
        ("BOTZ", "Global X Robotics & AI"),
    ],

    # ── DATA CENTERS ─────────────────────────────────────────
    "Data Centers": [
        ("SRVR", "Pacer Data & Infrastructure"),
    ],

    # ── FINTECH / BLOCKCHAIN ─────────────────────────────────
    "Fintech / Blockchain": [
        ("MILN", "Global X Millennials"),
        ("FINX", "Global X FinTech"),
        ("BLOK", "Amplify Blockchain"),
    ],

    # ── CLEAN ENERGY / EV ────────────────────────────────────
    "Clean Energy / EV": [
        ("TAN",  "Invesco Solar"),
        ("DRIV", "Global X Autonomous & EV"),
        ("ICLN", "iShares Clean Energy"),
        ("LIT",  "Global X Lithium"),
        ("URA",  "Global X Uranium"),
    ],

    # ── ENERGY ───────────────────────────────────────────────
    "Energy": [
        ("OIH",  "VanEck Oil Services"),
        ("XLE",  "Energy Select Sector"),
        ("XOP",  "SPDR Oil & Gas Exploration"),  # more volatile than XLE
    ],

    # ── SPACE ────────────────────────────────────────────────
    "Space": [
        ("UFO",  "Procure Space ETF"),
    ],

    # ── INDUSTRIALS ──────────────────────────────────────────
    "Industrials": [
        ("IYT",  "iShares Transportation"),
        ("XLI",  "Industrials Select Sector"),
        ("ITA",  "iShares Aerospace & Defense"),
        ("PAVE", "Global X Infrastructure"),
    ],

    # ── MATERIALS ────────────────────────────────────────────
    "Materials": [
        ("GDX",  "VanEck Gold Miners"),
        ("SIL",  "Global X Silver Miners"),
        ("XLB",  "Materials Select Sector"),
        ("REMX", "VanEck Rare Earth"),
    ],

    # ── CONSUMER DISCRETIONARY ───────────────────────────────
    "Consumer Discretionary": [
        ("XRT",  "SPDR Retail"),
        ("XLY",  "Consumer Discr Select Sector"),
        ("PEJ",  "Invesco Leisure & Entertainment"),
        ("ITB",  "iShares Homebuilders"),
    ],

    # ── CONSUMER STAPLES ─────────────────────────────────────
    "Consumer Staples": [
        ("MOO",  "VanEck Agribusiness"),
        ("DBA",  "Invesco Agriculture"),
        ("XLP",  "Consumer Staples Select Sector"),
        ("PBS",  "Invesco Dynamic Media"),
        ("PBJ",  "Invesco Food & Beverage"),
        ("PPH",  "VanEck Pharmaceutical"),
    ],

    # ── HEALTHCARE ───────────────────────────────────────────
    "Healthcare": [
        ("XLV",  "Healthcare Select Sector"),
        ("IBB",  "iShares Biotech"),
        ("XBI",  "SPDR Biotech"),               # more volatile — better for options
        ("IHI",  "iShares Medical Devices"),
        ("ARKG", "ARK Genomics"),
        ("IXJ",  "iShares Global Healthcare"),
    ],

    # ── FINANCIALS ───────────────────────────────────────────
    "Financials": [
        ("XLF",  "Financials Select Sector"),
        ("KBE",  "SPDR Bank ETF"),
        ("KRE",  "SPDR Regional Banking"),
        ("KIE",  "SPDR Insurance ETF"),
    ],

    # ── UTILITIES ────────────────────────────────────────────
    "Utilities": [
        ("VPU",  "Vanguard Utilities"),
        ("XLU",  "Utilities Select Sector"),
        ("PHO",  "Invesco Water Resources"),
    ],

    # ── REAL ESTATE ──────────────────────────────────────────
    "Real Estate": [
        ("VNQ",  "Vanguard Real Estate"),
        ("IFGL", "iShares Intl Developed Real Estate"),
    ],

    # ── COMMUNICATION / MEDIA ────────────────────────────────
    "Communication / Media": [
        ("VOX",  "Vanguard Communication"),
        ("XLC",  "Communication Services Select"),
        ("METV", "Roundhill Metaverse"),
    ],

    # ── TO ADD A NEW SECTOR: copy this template ───────────────
    # "Your Sector Name": [
    #     ("TICK1", "ETF Full Name 1"),
    #     ("TICK2", "ETF Full Name 2"),
    # ],

}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def calc_52w_range_pct(price, low_52w, high_52w):
    """Where is price in its 52-week range? 0%=at low, 100%=at high"""
    if not high_52w or high_52w == low_52w:
        return None
    return round((price - low_52w) / (high_52w - low_52w) * 100, 1)

def get_sentiment(range_pct):
    if range_pct is None:
        return "N/A"
    if range_pct >= 60:
        return "🟢 Bullish"
    elif range_pct >= 35:
        return "🟡 Neutral"
    return "🔴 Bearish"

def color_range_cell(val):
    """Background colour for 52W Range % cells"""
    if val is None:
        return ""
    if val >= 60:
        return "background-color: #bbf7d0"
    elif val >= 35:
        return "background-color: #fef08a"
    return "background-color: #fecaca"


# ============================================================
# DATA FETCHING  (all cached so the app doesn't re-fetch
#                 every time you click something)
# ============================================================

@st.cache_data(ttl=3600)   # cache for 1 hour
def fetch_etf_row(ticker, name):
    """Fetch one ETF's key stats from yfinance."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        price    = info.get("regularMarketPrice") or info.get("currentPrice") or 0
        low_52w  = info.get("fiftyTwoWeekLow",  0)
        high_52w = info.get("fiftyTwoWeekHigh", 0)
        pct_from_high = round((price - high_52w) / high_52w * 100, 2) if high_52w else None
        range_pct     = calc_52w_range_pct(price, low_52w, high_52w)

        # Put/Call ratio from nearest expiry options
        pc_ratio = None
        try:
            dates = t.options
            if dates:
                chain = t.option_chain(dates[0])
                calls_vol = chain.calls["volume"].sum()
                puts_vol  = chain.puts["volume"].sum()
                if calls_vol > 0:
                    pc_ratio = round(puts_vol / calls_vol, 2)
        except Exception:
            pass

        return {
            "Ticker":       ticker,
            "Name":         name,
            "Price":        round(price, 2),
            "52W Low":      round(low_52w, 2),
            "52W High":     round(high_52w, 2),
            "% From High":  pct_from_high,
            "52W Range %":  range_pct,
            "P/C Ratio":    pc_ratio,
            "Sentiment":    get_sentiment(range_pct),
        }
    except Exception:
        return {"Ticker": ticker, "Name": name, "Price": None,
                "52W Low": None, "52W High": None, "% From High": None,
                "52W Range %": None, "P/C Ratio": None, "Sentiment": "Error"}


@st.cache_data(ttl=86400)   # refresh once per day — holdings rarely change intraday
def fetch_holdings(etf_ticker, fmp_api_key=""):
    """
    Fetches live ETF holdings using two sources (no static fallback):

    Source 1 — stockanalysis.com  (free, live, covers every ETF, no key needed)
    Source 2 — FMP API            (if you added a key in the sidebar)

    If both fail the app tells you exactly where to look it up yourself.
    Holdings are cached for 24 hours so the app doesn't fetch on every click.
    """

    # ── Source 1: stockanalysis.com ──────────────────────────
    try:
        url = f"https://stockanalysis.com/etf/{etf_ticker.lower()}/holdings/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 200:
            tables = pd.read_html(r.text)
            if tables:
                df = tables[0].head(15).copy()

                # Normalise column names — stockanalysis uses slightly different labels
                col_map = {}
                for c in df.columns:
                    cl = str(c).lower()
                    if "symbol" in cl or "ticker" in cl:
                        col_map[c] = "Ticker"
                    elif "name" in cl or "company" in cl:
                        col_map[c] = "Name"
                    elif "weight" in cl or cl == "%":
                        col_map[c] = "Weight %"
                df = df.rename(columns=col_map)

                keep = [c for c in ["Ticker", "Name", "Weight %"] if c in df.columns]
                if "Ticker" in keep:
                    df = df[keep]
                    if "Weight %" in df.columns:
                        df["Weight %"] = (
                            df["Weight %"].astype(str)
                            .str.replace("%", "", regex=False).str.strip()
                        )
                        df["Weight %"] = pd.to_numeric(df["Weight %"], errors="coerce").round(2)
                        df = df.sort_values("Weight %", ascending=False)
                    df = df.reset_index(drop=True)
                    df["Source"] = "🟢 Live — stockanalysis.com"
                    return df
    except Exception:
        pass

    # ── Source 2: FMP API (only if key provided) ─────────────
    if fmp_api_key:
        try:
            url = (f"https://financialmodelingprep.com/api/v3/etf-holder/"
                   f"{etf_ticker}?apikey={fmp_api_key}")
            r = requests.get(url, timeout=10)
            data = r.json()
            if isinstance(data, list) and data:
                df = pd.DataFrame(data[:15])
                df = df.rename(columns={
                    "asset":            "Ticker",
                    "weightPercentage": "Weight %",
                    "name":             "Name",
                })
                df["Weight %"] = pd.to_numeric(
                    df.get("Weight %", 0), errors="coerce"
                ).round(2)
                cols = [c for c in ["Ticker", "Name", "Weight %"] if c in df.columns]
                df = df[cols].sort_values("Weight %", ascending=False).reset_index(drop=True)
                df["Source"] = "🟡 Live — FMP API"
                return df
        except Exception:
            pass

    # ── Both sources failed — return empty so UI can show instructions ──
    return pd.DataFrame(columns=["Ticker", "Name", "Weight %"])


@st.cache_data(ttl=3600)
def calc_relative_strength(stock_tickers, etf_ticker, period="1mo"):
    """
    Downloads price history and calculates each stock's return
    relative to the ETF.  Positive = stock is LEADING the ETF.
    """
    all_tickers = list(set(stock_tickers + [etf_ticker]))
    try:
        raw = yf.download(all_tickers, period=period,
                          auto_adjust=True, progress=False)
        # handle single vs multi ticker download shape
        if isinstance(raw.columns, pd.MultiIndex):
            closes = raw["Close"]
        else:
            closes = raw[["Close"]]
            closes.columns = all_tickers

        returns = ((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100).round(2)
        etf_return = float(returns.get(etf_ticker, 0))

        rows = []
        for t in stock_tickers:
            sr = returns.get(t)
            if sr is not None:
                vs = round(float(sr) - etf_return, 2)
                rows.append({
                    "Ticker":      t,
                    f"Return ({period}) %": round(float(sr), 2),
                    "ETF Return %": round(etf_return, 2),
                    "vs ETF %":    vs,
                    "Status":      "✅ Leading" if vs > 0 else "⚠️ Lagging",
                })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def fetch_options_data(tickers):
    """
    For each stock fetches:
      IV      — implied vol from ATM call, nearest expiry
      HV30    — 30-day historical (realised) volatility
      IV/HV   — ratio: >1.2 means options are expensive (sell)
                        <0.8 means options are cheap (buy)
      Earnings — next earnings date
      Options Volume — total near-term options activity
    """
    rows = []
    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker)
            info = t.info
            price = info.get("regularMarketPrice") or info.get("currentPrice") or 0

            # ── 30-day Historical Volatility ─────────────────
            hist = t.history(period="3mo")
            hv30 = None
            if len(hist) >= 30:
                log_ret = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
                hv30 = round(log_ret.tail(30).std() * np.sqrt(252) * 100, 1)

            # ── Implied Vol from ATM options ──────────────────
            iv = None
            options_volume = None
            try:
                dates = t.options
                if dates:
                    chain     = t.option_chain(dates[0])
                    calls     = chain.calls
                    puts      = chain.puts
                    atm_call  = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
                    if not atm_call.empty:
                        iv = round(float(atm_call["impliedVolatility"].values[0]) * 100, 1)
                    options_volume = int(calls["volume"].fillna(0).sum() +
                                        puts["volume"].fillna(0).sum())
            except Exception:
                pass

            # ── IV vs HV signal ───────────────────────────────
            iv_hv, signal = None, "N/A"
            if iv and hv30:
                iv_hv = round(iv / hv30, 2)
                if iv_hv > 1.2:
                    signal = "🔴 Expensive — Sell Premium"
                elif iv_hv < 0.8:
                    signal = "🟢 Cheap — Buy Options"
                else:
                    signal = "🟡 Fair Value"

            # ── Next Earnings Date ────────────────────────────
            # Three methods tried in order — stops as soon as one works.
            # "⚠️ Check manually" means we couldn't fetch the date.
            # That does NOT mean there are no earnings — always verify before trading.
            earnings = "⚠️ Check manually"

            # Method 1: earningsTimestampNext from info dict
            # (fastest — info is already fetched above, no extra network call)
            try:
                ts = info.get("earningsTimestampNext") or info.get("earningsTimestamp")
                if ts:
                    dt = pd.Timestamp(ts, unit="s")
                    if dt > pd.Timestamp.now():
                        earnings = str(dt.date())
            except Exception:
                pass

            # Method 2: ticker.calendar — contains a date range for the earnings window
            if earnings == "⚠️ Check manually":
                try:
                    cal = t.calendar
                    if cal and "Earnings Date" in cal:
                        dates = cal["Earnings Date"]
                        now   = pd.Timestamp.now()
                        future_dates = []
                        for d in dates:
                            ts = pd.Timestamp(d)
                            if ts.tzinfo is not None:
                                ts = ts.tz_localize(None)
                            if ts > now:
                                future_dates.append(ts)
                        if future_dates:
                            earnings = str(sorted(future_dates)[0].date())
                except Exception:
                    pass

            # Method 3: get_earnings_dates (least reliable — yfinance bug often omits future dates)
            if earnings == "⚠️ Check manually":
                try:
                    ed = t.get_earnings_dates(limit=10)
                    if ed is not None and not ed.empty:
                        now = pd.Timestamp.now()
                        idx = ed.index
                        try:
                            idx = idx.tz_localize(None)
                        except Exception:
                            try:
                                idx = idx.tz_convert("UTC").tz_localize(None)
                            except Exception:
                                pass
                        future = idx[idx > now]
                        if len(future):
                            earnings = str(future[-1].date())
                except Exception:
                    pass

            rows.append({
                "Ticker":       ticker,
                "Price":        round(price, 2),
                "IV %":         iv,
                "HV30 %":       hv30,
                "IV / HV":      iv_hv,
                "Signal":       signal,
                "Options Vol":  options_volume,
                "Next Earnings": earnings,
            })
            time.sleep(0.3)   # avoid rate-limiting yfinance

        except Exception:
            rows.append({
                "Ticker": ticker, "Price": None, "IV %": None,
                "HV30 %": None, "IV / HV": None, "Signal": "Error",
                "Options Vol": None, "Next Earnings": "N/A",
            })

    return pd.DataFrame(rows)


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("⚙️ Settings")

    fmp_key = st.text_input(
        "FMP API Key (optional)",
        type="password",
        help="Free at financialmodelingprep.com — enables live ETF holdings in Step 2."
    )

    st.divider()
    st.markdown("**52W Range % Legend**")
    st.markdown("🟢  ≥ 60%  — Strong / Bullish")
    st.markdown("🟡  35–60% — Mid / Neutral")
    st.markdown("🔴  < 35%  — Weak / Bearish")

    st.divider()
    st.markdown("**IV Signal Legend**")
    st.markdown("🟢  IV/HV < 0.8  → Options cheap, buy")
    st.markdown("🟡  IV/HV 0.8–1.2 → Fair value")
    st.markdown("🔴  IV/HV > 1.2  → Options expensive, sell premium")

    st.divider()
    st.caption("Data: Yahoo Finance (free). Holdings: FMP free tier.")


# ============================================================
# MAIN TITLE
# ============================================================
st.title("📊 ETF Options Trading Dashboard")
st.caption(
    "**Step 1** → Find strong sectors  |  "
    "**Step 2** → Drill into holdings, find leading stocks  |  "
    "**Step 3** → Check options suitability"
)

tab1, tab2, tab3 = st.tabs([
    "📈 Step 1 — Sector Screener",
    "🔍 Step 2 — Holdings Drill-Down",
    "⚡ Step 3 — Options Filter",
])


# ============================================================
# TAB 1 — SECTOR SCREENER
# ============================================================
with tab1:
    st.subheader("ETF Sector Screener")
    st.caption("Spot which subsectors are strong (green), mid (yellow), or weak (red) right now.")

    col_a, col_b = st.columns([3, 1])
    with col_a:
        selected_sectors = st.multiselect(
            "Sectors to show",
            list(ETF_SECTORS.keys()),
            default=list(ETF_SECTORS.keys()),
        )
    with col_b:
        sentiment_filter = st.selectbox("Filter Sentiment", ["All", "Bullish", "Neutral", "Bearish"])

    if st.button("🔄 Load / Refresh Data", key="btn_step1"):
        all_rows = []

        for sector in selected_sectors:
            etfs = ETF_SECTORS[sector]
            sector_rows = []

            progress_text = f"Fetching {sector}..."
            bar = st.progress(0, text=progress_text)

            for i, (ticker, name) in enumerate(etfs):
                row = fetch_etf_row(ticker, name)
                sector_rows.append(row)
                bar.progress((i + 1) / len(etfs), text=progress_text)
                time.sleep(0.1)

            bar.empty()

            df_sector = pd.DataFrame(sector_rows)

            # Apply sentiment filter
            if sentiment_filter != "All":
                df_sector = df_sector[df_sector["Sentiment"].str.contains(sentiment_filter, na=False)]

            if df_sector.empty:
                continue

            all_rows.extend(sector_rows)

            # ── Section header ────────────────────────────────
            st.markdown(f"### {sector}  —  {len(df_sector)} ETF(s)")

            # ── Style the table ───────────────────────────────
            def _style(row):
                base = [""] * len(row)
                if pd.notna(row.get("52W Range %")):
                    idx = list(row.index).index("52W Range %")
                    base[idx] = color_range_cell(row["52W Range %"])
                return base

            styled = (
                df_sector.style
                .apply(_style, axis=1)
                .format({
                    "Price":       "${:.2f}",
                    "52W Low":     "${:.2f}",
                    "52W High":    "${:.2f}",
                    "% From High": lambda v: f"{v:.2f}%" if v is not None else "N/A",
                    "52W Range %": lambda v: f"{v:.1f}%" if v is not None else "N/A",
                    "P/C Ratio":   lambda v: f"{v:.2f}" if v is not None else "N/A",
                }, na_rep="N/A")
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)

        # ── Full bar chart ────────────────────────────────────
        if all_rows:
            st.divider()
            st.subheader("📊 52-Week Range — All ETFs")

            all_df = pd.DataFrame(all_rows).dropna(subset=["52W Range %"])
            all_df = all_df.sort_values("52W Range %", ascending=True)
            all_df["Zone"] = all_df["52W Range %"].apply(
                lambda v: "Strong (≥60%)" if v >= 60 else "Mid (35–60%)" if v >= 35 else "Weak (<35%)"
            )

            fig = px.bar(
                all_df, x="52W Range %", y="Ticker",
                color="Zone",
                color_discrete_map={
                    "Strong (≥60%)": "#22c55e",
                    "Mid (35–60%)":  "#eab308",
                    "Weak (<35%)":   "#ef4444",
                },
                orientation="h",
                text="52W Range %",
                hover_data=["Name", "Price", "Sentiment"],
                height=max(500, len(all_df) * 22),
                title="ETF Position in 52-Week Range  (100 = at 52W High  ·  0 = at 52W Low)",
            )
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(xaxis_range=[0, 125], xaxis_title="Position in 52-Week Range (%)")
            st.plotly_chart(fig, use_container_width=True)


# ============================================================
# TAB 2 — HOLDINGS DRILL-DOWN
# ============================================================
with tab2:
    st.subheader("ETF Holdings Drill-Down")
    st.caption(
        "Select an ETF from a strong sector. "
        "See its top holdings and which stocks are **leading** vs lagging the ETF."
    )

    col_c, col_d = st.columns(2)
    with col_c:
        sector_choice = st.selectbox("Sector", list(ETF_SECTORS.keys()), key="s2_sector")
    with col_d:
        etf_list    = ETF_SECTORS[sector_choice]
        etf_labels  = [f"{t}  —  {n}" for t, n in etf_list]
        etf_choice  = st.selectbox("ETF", etf_labels, key="s2_etf")
        etf_ticker  = etf_choice.split("  —  ")[0].strip()

    period = st.radio(
        "Comparison period",
        ["1wk", "1mo", "3mo"],
        index=1, horizontal=True, key="s2_period"
    )

    if st.button("🔍 Drill Down", key="btn_step2"):
        with st.spinner(f"Loading {etf_ticker} holdings..."):
            holdings = fetch_holdings(etf_ticker, fmp_key)

        if holdings.empty:
            st.error(f"⚠️ Could not fetch live holdings for **{etf_ticker}**")
            st.markdown("---")
            st.markdown("**Look it up here and paste the tickers into Step 3 manually:**")

            lookup_url = f"https://stockanalysis.com/etf/{etf_ticker.lower()}/holdings/"
            etfdb_url  = f"https://etfdb.com/etf/{etf_ticker}/#holdings"

            col1, col2 = st.columns(2)
            with col1:
                st.link_button(
                    f"🔍 stockanalysis.com — {etf_ticker}",
                    lookup_url,
                    use_container_width=True,
                )
            with col2:
                st.link_button(
                    f"🔍 ETF Database — {etf_ticker}",
                    etfdb_url,
                    use_container_width=True,
                )

            st.info(
                "Copy the top 10 ticker symbols from either site, "
                "then paste them comma-separated into **Step 3** to run the options filter."
            )
        else:
            tickers_list = holdings["Ticker"].tolist()

            with st.spinner("Calculating relative strength vs ETF..."):
                rs_df = calc_relative_strength(tickers_list, etf_ticker, period=period)

            # Merge holdings + relative strength
            if not rs_df.empty:
                merged = holdings.merge(
                    rs_df[["Ticker", f"Return ({period}) %", "vs ETF %", "Status"]],
                    on="Ticker", how="left"
                )
            else:
                merged = holdings.copy()

            # ── Table ─────────────────────────────────────────
            st.markdown(f"#### Top Holdings of **{etf_ticker}**")

            def _style_holdings(row):
                styles = [""] * len(row)
                if "Status" in row.index:
                    idx = list(row.index).index("Status")
                    if row["Status"] == "✅ Leading":
                        styles[idx] = "background-color: #bbf7d0"
                    elif row["Status"] == "⚠️ Lagging":
                        styles[idx] = "background-color: #fecaca"
                return styles

            st.dataframe(
                merged.style.apply(_style_holdings, axis=1),
                use_container_width=True, hide_index=True
            )

            # ── Bar chart: vs ETF ─────────────────────────────
            if not rs_df.empty:
                st.markdown(f"#### Returns vs {etf_ticker}  ({period})")

                rs_sorted = rs_df.sort_values("vs ETF %")
                rs_sorted["Color"] = rs_sorted["vs ETF %"].apply(
                    lambda v: "Leading" if v > 0 else "Lagging"
                )

                fig2 = px.bar(
                    rs_sorted, x="vs ETF %", y="Ticker",
                    color="Color",
                    color_discrete_map={"Leading": "#22c55e", "Lagging": "#ef4444"},
                    orientation="h",
                    text="vs ETF %",
                    height=max(300, len(rs_sorted) * 38),
                )
                fig2.update_traces(texttemplate="%{text:+.2f}%", textposition="outside")
                fig2.add_vline(x=0, line_dash="dash", line_color="gray")
                fig2.update_layout(xaxis_title=f"Return vs {etf_ticker} (%)", showlegend=False)
                st.plotly_chart(fig2, use_container_width=True)

            # ── Pass to Step 3 ────────────────────────────────
            if "Status" in merged.columns:
                leading = merged[merged["Status"] == "✅ Leading"]["Ticker"].tolist()
            else:
                leading = tickers_list

            if leading:
                st.success(f"✅ Leading stocks: **{', '.join(leading)}**")
                st.info("👉 Copy these tickers into **Step 3** to check options suitability.")


# ============================================================
# TAB 3 — OPTIONS FILTER
# ============================================================
with tab3:
    st.subheader("Options Suitability Filter")
    st.caption(
        "Paste in the leading stocks from Step 2. "
        "The dashboard checks IV, historical vol, earnings risk, and options liquidity."
    )

    ticker_input = st.text_input(
        "Tickers (comma separated)",
        placeholder="e.g.  NVDA, AMD, AVGO, TSM",
        help="Paste the leading stocks from Step 2 here.",
    )

    if st.button("⚡ Analyse", key="btn_step3") and ticker_input:
        raw_tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]

        with st.spinner(f"Fetching options data for {', '.join(raw_tickers)}..."):
            opt_df = fetch_options_data(raw_tickers)

        if opt_df.empty:
            st.error("Could not fetch data. Check your tickers and try again.")
        else:
            # ── Main table ────────────────────────────────────
            st.markdown("#### Options Data")

            def _style_options(row):
                styles = [""] * len(row)
                if "Signal" in row.index:
                    idx = list(row.index).index("Signal")
                    sig = str(row["Signal"])
                    if "Cheap" in sig:
                        styles[idx] = "background-color: #bbf7d0"
                    elif "Expensive" in sig:
                        styles[idx] = "background-color: #fecaca"
                    elif "Fair" in sig:
                        styles[idx] = "background-color: #fef08a"
                return styles

            st.dataframe(
                opt_df.style.apply(_style_options, axis=1),
                use_container_width=True, hide_index=True
            )

            # ── Earnings warning ──────────────────────────────
            st.markdown("#### ⚠️ Earnings Risk")
            warnings_shown   = False
            check_manual     = []

            for _, row in opt_df.iterrows():
                earned_str = str(row["Next Earnings"])

                # Flag if we couldn't fetch the date — don't assume it's safe
                if "Check manually" in earned_str:
                    check_manual.append(row["Ticker"])
                    continue

                # If we got a real date, check if it's within 21 days
                try:
                    days = (pd.to_datetime(earned_str) - pd.Timestamp.now()).days
                    if 0 <= days <= 21:
                        st.warning(
                            f"**{row['Ticker']}** — earnings in **{days} days** "
                            f"({earned_str}).  "
                            "IV will spike into this date — be careful with long options."
                        )
                        warnings_shown = True
                    elif days > 21:
                        st.success(f"**{row['Ticker']}** — next earnings {earned_str} ({days} days away) ✅")
                        warnings_shown = True
                except Exception:
                    check_manual.append(row["Ticker"])

            # Tickers where we couldn't get a date at all
            if check_manual:
                st.error(
                    f"**Could not fetch earnings date for: {', '.join(check_manual)}** — "
                    "check [Earnings Whispers](https://www.earningswhispers.com) or "
                    "[Yahoo Finance](https://finance.yahoo.com) before trading."
                )
                warnings_shown = True

            if not warnings_shown:
                st.success("No earnings within 21 days for the tickers checked. ✅")

            # ── Summary ───────────────────────────────────────
            st.markdown("#### 🎯 Summary")
            col_e, col_f = st.columns(2)

            with col_e:
                buy_list = opt_df[opt_df["Signal"].str.contains("Cheap|Fair", na=False)]["Ticker"].tolist()
                if buy_list:
                    st.success(f"**Best for buying options:**\n\n{', '.join(buy_list)}\n\n(IV not expensive)")

            with col_f:
                sell_list = opt_df[opt_df["Signal"].str.contains("Expensive", na=False)]["Ticker"].tolist()
                if sell_list:
                    st.info(f"**Consider selling premium:**\n\n{', '.join(sell_list)}\n\n(IV elevated vs HV30)")
