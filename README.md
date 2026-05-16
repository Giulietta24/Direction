# 📊 ETF Options Trading Dashboard

A 3-step Streamlit dashboard to find options trade candidates using ETF sector momentum.

## How it works

| Step | What it does |
|------|-------------|
| **Step 1** | Shows all ETFs by sector with 52-week range position, P/C ratio, and sentiment — so you can instantly see which subsectors are strong |
| **Step 2** | Pick a strong ETF → see its top holdings ranked by weight → bar chart shows which individual stocks are *leading* vs lagging the ETF |
| **Step 3** | Paste in the leading stocks → checks IV, HV30, IV/HV ratio, earnings dates, and options volume so you know whether to buy or sell premium |

---

## Setup (one time only)

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/etf-dashboard.git
cd etf-dashboard
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Mac / Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the app
```bash
streamlit run app.py
```

The dashboard will open automatically in your browser at `http://localhost:8501`

---

## Optional: Live ETF Holdings (Step 2)

By default, Step 2 uses static fallback data for major ETFs (SPY, QQQ, XLK, SMH, SOXX, XLE, XLF, XLV, XLI, XLY, IBB).

To get **live holdings for all ETFs**:

1. Go to [financialmodelingprep.com](https://financialmodelingprep.com) — create a free account
2. Copy your API key
3. Paste it into the **sidebar** of the dashboard when running

The free tier gives 250 requests/day which is plenty for this use case.

---

## Deploying to Streamlit Cloud (share with others)

1. Push your code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set main file to `app.py`
5. Click Deploy

Your dashboard will be live at a public URL within a few minutes.

> **Tip:** If using an FMP API key, add it as a **Secret** in Streamlit Cloud settings rather than hardcoding it.

---

## Adding / removing ETFs

Open `app.py` and find the `ETF_SECTORS` dictionary near the top.
Each entry looks like this:

```python
"Technology": [
    ("XLK",  "Tech Select Sector"),
    ("SKYY", "First Trust Cloud"),
    ...
],
```

Just add or remove lines. Tickers must match Yahoo Finance symbols.

---

## Understanding the signals

### 52W Range %
| Colour | Range | Meaning |
|--------|-------|---------|
| 🟢 Green | ≥ 60% | Strong — price near its annual high |
| 🟡 Yellow | 35–60% | Mid — no clear direction |
| 🔴 Red | < 35% | Weak — price near its annual low |

### IV Signal (Step 3)
| Signal | IV/HV ratio | What to do |
|--------|-------------|------------|
| 🟢 Cheap | < 0.8 | Options underpriced → consider buying calls/puts |
| 🟡 Fair | 0.8–1.2 | Normal — trade direction |
| 🔴 Expensive | > 1.2 | Options overpriced → consider selling premium (spreads, covered calls) |

### P/C Ratio
| Value | Meaning |
|-------|---------|
| < 0.7 | Bullish (more calls than puts) |
| 0.7–0.85 | Neutral |
| > 0.85 | Bearish (more puts than calls) |

---

## Data sources

| Data | Source | Cost |
|------|--------|------|
| Prices, 52W range, options chains | Yahoo Finance via `yfinance` | Free |
| ETF holdings | Financial Modeling Prep | Free (250 req/day) |

---

## Limitations

- `yfinance` can occasionally be slow or return missing data — clicking Refresh usually fixes it
- IV/HV ratio is a *proxy* for IV Rank, not a true percentile calculation. For precise IV Rank use Market Chameleon or your broker
- Earnings dates from yfinance are estimates — always verify before trading
