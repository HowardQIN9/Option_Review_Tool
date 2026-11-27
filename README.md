# Short-Dated Option Trade Review: Robinhood Fills + Alpaca Minute Bars

**English** | [简体中文](README.zh-CN.md)

Line up my own option trades with the minute-by-minute market data at the time each one was placed, then use statistics to find the patterns and problems in them.

The project includes a dashboard that runs on your own computer:
- **Filters**: date (a range or a single day), ticker (searchable), Call/Put, DTE, entry time of day, holding time, win/loss, overnight holds, and how the position was built.
- **Statistics**: trade count, win rate, expectancy per trade, Profit Factor and more. They update as you filter, come with 95% confidence intervals, and show a warning when the sample is too small.
- **Calendar**: a small Mon–Fri month view coloured by daily P&L, with days that have a note marked. Click a day, a week or the month to filter, or "All" to go back to every date.
- **Journal**: a note for each day (market conditions, mindset, plan) and for each trade (reasoning, execution, lessons), with quick tags such as Planned, Impulsive or Cut loss late. Notes are saved only on your computer.
- **Trade replay**: pick any trade to see the option and the underlying minute by minute, with every buy and sell marked.
- **Export for LLM analysis**: package the filtered trades as a folder that Claude Code or Codex can open and analyse. You choose whether dollar amounts, position sizes and your notes are included.
- **Chinese / English**: both the interface and the exported analysis pack.

> This README is written for readers who know trading but not necessarily code. The first half explains what was done and how. Installation and usage come after that.
> You can also hand the whole document to an LLM such as ChatGPT or Claude and ask it questions.

---

## 1. The problem

A Robinhood statement records **which day** a contract was bought or sold and at what price. It does not record **the time of day** of the fill.

Without exact times, you can't answer the questions that matter most in a review:

- When I entered, was the underlying rising, falling or flat?
- While I held it, how far was I up at best, and down at worst?
- After I sold, where did the price go?
- Did the loss come from calling the direction wrong, or from time decay (Theta)?

So the core of the project is **adding the time dimension back**: putting every fill exactly where it happened in the market data.

---

## 2. Data sources

| Data | Source | Contents |
|---|---|---|
| Trade history | Robinhood statement CSV | Date, contract, side, quantity, price, amount (incl. fees) |
| Exact fill times | Robinhood API (read-only) | Timestamp of every fill (millisecond precision), order type (limit/market), limit price |
| Underlying 1-minute bars | Alpaca market data API (free account) | OHLC, volume, trade count, VWAP; SIP consolidated feed |
| 1-minute bars of each option contract | Alpaca market data API (free account) | Minute-by-minute trade prices of every contract traded, over the holding period |

- **Robinhood API**: the code only reads order history. It never places, changes or cancels orders. Robinhood has no official public API, so this uses the open-source library `robin_stocks`, and you log in to your own account.
- **What gets downloaded is decided automatically.** The scripts read the statement to find the tickers, days and contracts you traded, and download only those.
  - SPY, QQQ and IWM: every trading day in the period, so the moments you traded can be compared with the moments you didn't.
  - Other stocks: only the days you traded them.
  - Option contracts: from the first buy to the last sell, including days held overnight.

---

## 3. Pipeline

```
Robinhood statement CSV ──┐
                           ├─ match fill by fill ─→ fills with exact times
Robinhood API fill times ──┘                            │
                                                         ├─ align by time ─→ per-trade minute data ─→ statistics & report
Alpaca 1-min bars (underlying + options) ────────────────┘
```

1. **Match fill times**: each statement row is matched to an API fill on date, contract, open/close side, quantity and price.
2. **Build round trips**: one contract going from flat to a position and back to flat counts as one trade. Adding to the position and scaling out stay in the same trade.
3. **Align with market data**: each trade gets the underlying and option minute prices before entry, during the hold and after exit.
4. **Compute metrics and run statistical tests**, then produce the report and charts.

---

## 4. Metrics computed for each trade

| Metric | Meaning |
|---|---|
| MFE (maximum favourable excursion) | How far the option's high during the hold rose above the average entry price |
| MAE (maximum adverse excursion) | How far the option's low during the hold fell below the average entry price |
| Capture ratio | Realized gain ÷ maximum open profit during the hold |
| Price after exit | How much the option rose or fell 5 / 15 / 30 / 60 minutes after selling (sold too early or too late?) |
| Underlying before and after entry | How far the underlying had moved in the 15 minutes before entry, and in the 15 minutes after (entering at the start of a move, or chasing its end?) |
| RVOL (relative volume) | Volume at entry vs. the normal level for that time of day |
| DTE, Delta, implied volatility | Days to expiry, the contract's Delta and IV at entry (IV and Greeks are backed out of fill prices with Black-Scholes) |
| P&L attribution | Each trade's P&L split into underlying price move, time decay (Theta) and change in implied volatility |

**Statistical methods**

- Expectancy and win rate come with **95% confidence intervals**. The expectancy interval resamples whole trading days, which keeps the correlation between trades on the same day.
- **Control group**: minutes on the same day, in the same ticker, under similar conditions, when I did **not** trade. This tests whether my timing beats a mechanical rule.
- **In-sample / out-of-sample testing**: rules are found on the first half of the data and checked on the second half, to avoid fitting parameters to known answers.

---

## 5. Data checks

- All 650 option fills **were matched to an exact fill time**.
- Fees were checked row by row: $0.04–$0.08 per contract, with no anomalies.
- 41 statement rows that look identical turned out, when checked against the API, to be partial fills of the same order rather than duplicates.
- 6 contracts that expired worthless are treated as closed at a price of 0 at 16:00 on the expiry date.
- No positions were left open, and no records failed to match.

---

## 6. Limitations

- **No bid/ask quotes.** Option bars only have trade prices, so the real spread and slippage can't be measured, and take-profit fills in backtests may be optimistic.
- **Sparse data for illiquid contracts.** A minute with no trades has no bar.
- **No account equity data.** Only per-trade P&L can be computed, not account returns.
- **IV and Greeks are estimates.** They are backed out of fill prices with Black-Scholes, assuming a 4% rate, no dividends and European exercise.
- **Limited sample.** 265 trades over about 9 months. Many subgroups have only a few dozen trades, so their conclusions are hypotheses.
- **Style and time period are mixed together.** Early on I traded more single stocks and longer-dated contracts, later more short-dated ETF options, so before/after comparisons can't be attributed to style alone.
- The analysis was written by an LLM as code. **Every number is computed by the code**, and re-running it gives the same results. They are not the LLM's subjective judgement.

---

## 7. Installation for beginners (no programming experience)

If you only want to understand the project, you can stop here; nothing needs to be installed. The steps below are for people who want to **run it on their own Robinhood history**.

### What you need

| Item | Notes | Cost |
|---|---|---|
| Python | The software that runs the programs. Installing Anaconda is recommended; it includes Python and most of the libraries used here | Free |
| This project's files | On the GitHub page, click the green **Code** button → **Download ZIP**, then unzip it | Free |
| An Alpaca account | Used to download historical market data. You get an API key (a pair of secret strings) after signing up | Free |
| A Robinhood statement | Export your trade history as a CSV from Robinhood | Free |

### Easiest: let an AI install and run it

1. Install the [Claude desktop app](https://claude.ai/download) and open the **Code** tab.
2. Choose the unzipped project folder.
3. Tell Claude: "Install and run this project following the README."
4. Claude installs Python and the dependencies and runs the scripts. It asks you before steps that need your confirmation.

**Two things you should do yourself, not the AI:**
- **Logging in to Robinhood**: type your username, password and two-factor code into the terminal window yourself.
- **Setting the Alpaca API key**: set it yourself, and don't paste the key into the chat.

### Manual installation (Windows)

**Step 1: Install Anaconda**

Download the Windows version from [anaconda.com/download](https://www.anaconda.com/download) and install it with the default options.

**Step 2: Open a command window**

Search the Start menu for **Anaconda Prompt** and open it. Type the commands below into this window, pressing Enter after each line.

**Step 3: Go to the project folder**

```powershell
cd "C:\Users\your-username\Downloads\project-folder"
```

Replace the path in quotes with where you unzipped the project. A shortcut: type `cd ` followed by a space, then drag the folder from File Explorer into the window and the path is filled in for you.

**Step 4: Create a separate environment and install the libraries**

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

- The first line creates a separate Python environment inside the project folder. The project's libraries are installed there and don't affect other programs on your computer.
- The second line enters that environment. When it works, the prompt starts with `(.venv)`. **Every time you open a new window, go to the project folder and run this line first.**
- The third line downloads all the libraries the project needs. It may take a few minutes.

**Step 5: Sign up for Alpaca and get an API key**

1. Create a free account at [alpaca.markets](https://alpaca.markets/).
2. After logging in, find API Keys in the dashboard and generate a key. You get two strings: a **Key** and a **Secret**.
3. The Secret is shown only once, so save it first. Don't share it with anyone or upload it anywhere.

**Step 6: Add your statement**

Put the CSV exported from Robinhood into the project folder (next to `README.md`). It must be the only `.csv` file there.

**Step 7: Continue from step 3 of the next section**

Start at "Export exact fill times" and work through the steps in order.

### Common problems

- **`'python' is not recognized as an internal or external command`**: you are not in Anaconda Prompt, or Python isn't installed correctly. Close the window, reopen Anaconda Prompt from the Start menu and try again.
- **`No module named ...`**: usually the environment isn't active. Run `.venv\Scripts\activate`, check that the prompt starts with `(.venv)`, and try again. If it still fails, run `pip install -r requirements.txt` once more.
- **`set ALPACA_API_KEY and ALPACA_API_SECRET`**: the Alpaca key isn't set, or it was lost when the window closed. It must be set again in every new window.
- **Robinhood login fails**: check your username and password, and watch your phone for the two-factor prompt.

**Security note:** after a successful Robinhood login, a login token is saved in your user folder (`.tokens\robinhood.pickle`) so you don't have to log in next time. Anyone who has this file is effectively logged in to your account until it expires. Delete it once you have exported your data.

---

## 8. Running it (for readers who know Python)

> Technical section. Requires Python 3.10+ and a free [Alpaca](https://alpaca.markets/) account for the market data API key.

**1. Install dependencies** (a virtual environment is recommended)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**2. Add the Robinhood statement**

Export your trade history CSV from "Reports and statements" in Robinhood and put it in the project root. It must be the only `.csv` file in the root.

**3. Export exact fill times (read-only)**

```powershell
python export_rh_option_orders.py
```

The script asks for your Robinhood username, password and two-factor code in the terminal. `robin_stocks` caches the login token in your user folder, outside the project.

**4. Set the Alpaca API key**

In PowerShell:

```powershell
$env:ALPACA_API_KEY = "your key"
$env:ALPACA_API_SECRET = "your secret"
```

In Anaconda Prompt (used in the beginner steps) the syntax is different, with no spaces or quotes around the equals sign:

```bat
set ALPACA_API_KEY=your-key
set ALPACA_API_SECRET=your-secret
```

These settings last only for the current window.

**5. Download market data**

```powershell
# SPY/QQQ/IWM: every trading day in the range
python fetch_minute_bars.py --range 2026-03-02 2026-11-23

# Other tickers: only the days you traded them
python fetch_minute_bars.py --symbols INTC TSLA NVDA

# Every option contract you traded
python fetch_option_bars.py --symbols SPY QQQ IWM INTC TSLA NVDA
```

Files already downloaded are skipped. The free Alpaca plan is rate-limited (200 requests per minute); the scripts wait and retry automatically.

**6. Run the analysis**

```powershell
python run_analysis.py      # full analysis, ~40 seconds, writes to output/
python period_analysis.py   # comparison across trading periods
```

**7. Open the dashboard**

```powershell
streamlit run streamlit_app.py
```

Your browser opens `http://localhost:8501`. The dashboard runs only on your computer and does not upload your data anywhere.

- **Day / night themes**: light cream by day, deep green by night. It follows your system setting by default; switch manually under **⋮ → Settings → Theme** at the top right. The colours are defined in `.streamlit/config.toml`.
- **Calendar**: top right. Click a day for that day, a week (the W column on the left) for that week, or the month name for the whole month; "All" resets to every date. ◀ ▶ browse months without changing the filter.
- **Journal**: select a row in the trade list (or a trade in the replay) and click "Note on this trade", or use "Write a note…" in the sidebar for the day's note. Notes are stored in `notes/notes.json`, which is not uploaded to GitHub.
- **Export for LLM analysis**: at the bottom of the sidebar. It opens a dialog that uses the current filters. Dollar amounts and notes are both off by default.
- **Chinese / English**: pick the language at the top of the sidebar; the exported pack uses the same language. You can also open `http://localhost:8501/?lang=en` directly.

**8. Run the tests (developers)**

```powershell
pip install -r requirements-dev.txt
pytest
```

The tests use only made-up sample data, so no real trading history is needed.

**Files**

| File | Purpose |
|---|---|
| `export_rh_option_orders.py` | Export option orders and exact fill times from the Robinhood API |
| `fetch_minute_bars.py` | Download underlying 1-minute bars from Alpaca |
| `fetch_option_bars.py` | Download option contract 1-minute bars from Alpaca |
| `run_analysis.py` | Main analysis entry point: cleaning, matching, statistics, backtests, report and charts |
| `period_analysis.py` | Comparison across trading periods |
| `tradelab/` | Analysis code: data handling (`data.py`), market data and Greeks (`market.py`), statistics (`analytics.py`), charts (`charts.py`), parameters (`config.py`) |
| `build_fills.py`, `analyze_trades.py` | Earlier standalone round-trip analysis for SPY/QQQ/IWM only |
| `streamlit_app.py` | Dashboard entry point |
| `dashboard/` | Dashboard logic: data loading (`data.py`), filters (`filters.py`), statistics and confidence intervals (`stats.py`), replay chart (`charts.py`), analysis-pack export (`export.py`, `export_dialog.py`), journal (`notes.py`, `notes_dialog.py`), calendar (`calendar_view.py`), Chinese/English text (`i18n.py`) |
| `tests/` | Unit tests |

Personal trading data (the statement, `data/`, `output/`, `exports/`, `notes/`) is not included in the repository.

> Note: the full analysis report produced by `run_analysis.py` is currently written in Chinese.

---

## License

Released under the [MIT License](LICENSE): you may use, modify and distribute it freely, as long as the original copyright notice is kept.

The license covers the code in this repository only. Data from Robinhood and Alpaca is subject to their terms of service, and third-party libraries such as `robin_stocks` have their own licenses.

## Disclaimer

This is a personal review and learning project and is not investment advice. The findings apply only to my own trades over this period.
