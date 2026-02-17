# PowerTrader Hub — What Changed (v1 → v2)

## Drop-in replacement
`pt_hub.py` is the **only file that changed**.
`pt_thinker.py`, `pt_trainer.py`, and `pt_trader.py` are **untouched** — drop them
in the same folder as before.

---

## New Features

### 1. Exchange Selector
In **Settings → Exchange**, pick your exchange from a dropdown:
- **Robinhood** (default — existing behaviour, unchanged)
- **Kraken**
- **Binance**

The window title updates instantly: `PowerTrader - Hub  [Kraken]`

### 2. Per-Exchange Credential Wizards
Click **"Setup Wizard"** next to the Exchange row.  
A different wizard opens depending on which exchange you picked:

| Exchange   | Wizard                                     | Files created                       |
|------------|--------------------------------------------|-------------------------------------|
| Robinhood  | Generates Ed25519 keypair + API Key        | `r_key.txt`, `r_secret.txt`         |
| Kraken     | Paste API Key + API Secret from Kraken     | `kr_key.txt`, `kr_secret.txt`       |
| Binance    | Paste API Key + Secret Key from Binance    | `bn_key.txt`, `bn_secret.txt`       |

All wizards include:
- Step-by-step instructions with direct links to each exchange's API page
- **Test Credentials** button (safe read-only call, no trading)
- **Save** with automatic backup of existing files (`.bak_YYYYMMDD_HHMMSS`)
- **Clear** button to delete credentials

### 3. Exchange Written to Environment
When the GUI starts (or settings are saved), it sets:
```
POWERTRADER_EXCHANGE = "robinhood" | "kraken" | "binance"
```
`pt_trader.py` can read `os.environ["POWERTRADER_EXCHANGE"]` to know which
exchange to use — no need to edit the trader script manually.

---

## How to Setup Each Exchange

### Robinhood
1. Settings → Exchange → `robinhood` → Setup Wizard
2. Click **Generate Keys**
3. Copy the Public Key, paste it into:
   `Robinhood.com → Account → Settings → Crypto → API Trading → + Add Key`
4. Enable **READ + TRADE** permissions → Save → copy the API Key Robinhood shows
5. Paste API Key into the wizard → Test → Save

### Kraken
1. Settings → Exchange → `kraken` → Setup Wizard
2. Open the link to `kraken.com → Security → API → Create API Key`
3. Required permissions: **Query Funds**, **Create & Modify Orders**, **Cancel Orders**
4. Copy the **API Key** and **Private Key** Kraken shows you
5. Paste both into the wizard → Test → Save

### Binance
1. Settings → Exchange → `binance` → Setup Wizard
2. Open the link to `binance.com → Profile → API Management → Create API`
3. Required: **Enable Reading** + **Enable Spot & Margin Trading**
4. ⚠️ Copy the **Secret Key immediately** — Binance only shows it once!
5. Paste both fields into the wizard → Test → Save

---

## Unchanged
Everything else is **100% identical** to the original:
- Neural level tiles and bars
- Candlestick charts with price levels
- Account / P&L display
- DCA settings
- Training controls
- Log windows
- All keyboard shortcuts and layout behaviour
- All file paths and IPC (hub_data directory, runner_ready.json, etc.)

---

## Requirements
Same as original, no new packages needed for the GUI changes.

```
pip install requests psutil matplotlib colorama cryptography PyNaCl kucoin-python
```

---

## Files in This Package

| File | Status | Notes |
|---|---|---|
| `pt_hub.py` | ✅ ENHANCED | Multi-exchange support added |
| `pt_thinker.py` | ✅ Original | Neural runner — unchanged |
| `pt_trainer.py` | ✅ Original | Model trainer — unchanged |
| `pt_trader.py` | ✅ Original | Order executor — unchanged |
| `WHAT_CHANGED.md` | NEW | This file |
