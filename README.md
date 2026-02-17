# PowerTrader — Complete Project
## Quick-start guide

---

## 📂 Folder layout

```
PowerTrader_Complete/
│
├── pt_hub.py          ← Enhanced GUI  (multi-exchange: Robinhood / Kraken / Binance)
├── pt_thinker.py      ← Neural signal runner  (original, unchanged)
├── pt_trader.py       ← Order executor         (original, unchanged)
├── pt_trainer.py      ← Pattern trainer        (original, unchanged)
├── requirements.txt   ← pip packages for the 4 scripts above
├── WHAT_CHANGED.md    ← Summary of every change made to pt_hub.py
│
└── enhanced/          ← New modular architecture (optional, future-ready)
    ├── config.py
    ├── models.py
    ├── trainer.py
    ├── signals.py
    ├── trader.py
    ├── api.py
    ├── exchange/
    │   ├── __init__.py
    │   └── paper.py
    ├── .env.example
    ├── requirements_enhanced.txt
    ├── docker-compose.yml
    ├── Dockerfile
    ├── start.sh
    ├── README.md
    ├── PROJECT_SUMMARY.md
    ├── COMPARISON.md
    ├── MIGRATION_GUIDE.md
    └── ANALYSIS_AND_IMPROVEMENTS.md
```

---

## 🖥️ Windows — run the original system (recommended starting point)

### 1. Install Python 3.10+
Download from https://www.python.org/downloads/

### 2. Install dependencies
Open a Command Prompt in this folder:
```
pip install requests psutil matplotlib colorama cryptography PyNaCl kucoin-python
```

### 3. Launch the GUI
```
python pt_hub.py
```

### 4. Set up your exchange credentials
- Go to **Settings** (menu) → choose your **Exchange** (Robinhood / Kraken / Binance)
- Click **Setup Wizard** and follow the steps
- Click **Save**

### 5. Train your models
- In the GUI → Training section → **Train All**
- Wait for training to complete (status shows "Trained ✅")

### 6. Start trading
- Click **Start All** in the GUI
- The neural runner and trader will launch automatically

---

## 🐧 Linux / Docker — run the enhanced modular system

See `enhanced/README.md` for full instructions.

```bash
cd enhanced
cp .env.example .env
# edit .env with your settings
./start.sh
```

---

## 📋 Exchange credential files

| Exchange   | API Key file    | Secret file        |
|------------|-----------------|--------------------|
| Robinhood  | `r_key.txt`     | `r_secret.txt`     |
| Kraken     | `kr_key.txt`    | `kr_secret.txt`    |
| Binance    | `bn_key.txt`    | `bn_secret.txt`    |

All files are created by the **Setup Wizard** inside the GUI.  
Place them in the same folder as `pt_hub.py`.

---

## ⚠️ Disclaimer
This software is for educational purposes. Cryptocurrency trading involves
significant financial risk. Always start with paper trading and never invest
more than you can afford to lose.
