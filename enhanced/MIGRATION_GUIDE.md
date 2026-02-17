# Migration Guide: Original → Enhanced PowerTrader

## 🎯 Overview

This guide helps you transition from the original PowerTrader system to the enhanced version while preserving your existing data and configuration.

## ⚠️ Before You Begin

### Backup Everything
```bash
# Backup original system
cd /path/to/original/powertrader
tar -czf ~/powertrader_backup_$(date +%Y%m%d).tar.gz .

# Verify backup
tar -tzf ~/powertrader_backup_*.tar.gz | head -20
```

### System Requirements
- Python 3.10 or higher
- Docker & Docker Compose (recommended)
- 4GB RAM minimum
- 10GB disk space

## 📋 Migration Steps

### Step 1: Install Enhanced System

```bash
# Clone or extract enhanced system
cd ~
git clone https://github.com/yourname/powertrader-enhanced
cd powertrader-enhanced

# Or if you have the files
cd /path/to/powertrader_enhanced
```

### Step 2: Migrate Configuration

The original system used a combination of hardcoded values and `gui_settings.json`. The enhanced system uses environment variables and Pydantic models.

#### Original `gui_settings.json`
```json
{
  "coins": ["BTC", "ETH", "XRP"],
  "trade_start_level": 3,
  "start_allocation_pct": 0.5,
  "dca_multiplier": 2.0,
  "dca_levels": [-2.5, -5.0, -10.0]
}
```

#### Enhanced `.env`
```bash
# Copy example environment file
cp .env.example .env

# Edit with your settings
PT_TRADING_MODE=paper
PT_TRADING__COINS=BTC,ETH,XRP
PT_TRADING__TRADE_START_LEVEL=3
PT_TRADING__START_ALLOCATION_PCT=0.5
PT_TRADING__DCA_MULTIPLIER=2.0
PT_TRADING__DCA_LEVELS=-2.5,-5.0,-10.0
```

#### Automated Migration Script

```python
# scripts/migrate_config.py
import json
import os
from pathlib import Path

def migrate_config():
    """Migrate gui_settings.json to .env format."""
    
    # Read original settings
    old_settings_path = Path("../original/gui_settings.json")
    if not old_settings_path.exists():
        print("No gui_settings.json found")
        return
    
    with open(old_settings_path) as f:
        old = json.load(f)
    
    # Generate .env content
    env_content = [
        "# Migrated from gui_settings.json",
        f"PT_TRADING__COINS={','.join(old.get('coins', []))}",
        f"PT_TRADING__TRADE_START_LEVEL={old.get('trade_start_level', 3)}",
        f"PT_TRADING__START_ALLOCATION_PCT={old.get('start_allocation_pct', 0.5)}",
        f"PT_TRADING__DCA_MULTIPLIER={old.get('dca_multiplier', 2.0)}",
        f"PT_TRADING__DCA_LEVELS={','.join(map(str, old.get('dca_levels', [])))}",
    ]
    
    # Write .env
    with open(".env", "a") as f:
        f.write("\n".join(env_content))
    
    print("✅ Configuration migrated to .env")

if __name__ == "__main__":
    migrate_config()
```

Run it:
```bash
python scripts/migrate_config.py
```

### Step 3: Migrate Trained Models

The enhanced system uses a different model format (pickle-based with LRU caching), but can import from the original text files.

#### Migration Script

```python
# scripts/migrate_models.py
import pickle
from pathlib import Path
from datetime import datetime
from trainer import PatternMemory, Pattern

def parse_old_memory(text: str) -> list:
    """Parse original memory format."""
    entries = text.split('~')
    return [e for e in entries if e.strip()]

def migrate_models():
    """Migrate original memory files to new format."""
    
    old_dir = Path("../original")
    timeframes = ['1hour', '2hour', '4hour', '8hour', '12hour', '1day', '1week']
    
    for tf in timeframes:
        old_memory_file = old_dir / f"memories_{tf}.txt"
        old_weights_file = old_dir / f"memory_weights_{tf}.txt"
        
        if not old_memory_file.exists():
            continue
        
        print(f"Migrating {tf}...")
        
        # Read old format
        with open(old_memory_file) as f:
            old_memories = parse_old_memory(f.read())
        
        with open(old_weights_file) as f:
            old_weights = f.read().split()
        
        # Convert to new format
        memory = PatternMemory(max_size=10000)
        
        for i, (mem, weight) in enumerate(zip(old_memories, old_weights)):
            try:
                # Parse old memory format: "changes{}high_changes{}low_changes"
                parts = mem.split('{}')
                if len(parts) != 3:
                    continue
                
                close_changes = [float(x) for x in parts[0].split() if x]
                high_changes = [float(x) for x in parts[1].split() if x]
                low_changes = [float(x) for x in parts[2].split() if x]
                
                # Create pattern
                pattern = Pattern(
                    timeframe=tf,
                    pattern_hash=f"migrated_{i}",
                    close_changes=close_changes,
                    high_changes=high_changes,
                    low_changes=low_changes,
                    weight=float(weight),
                    high_weight=1.0,
                    low_weight=1.0,
                    created_at=datetime.now(),
                    last_seen=datetime.now(),
                    hit_count=1,
                    success_count=0
                )
                
                memory.add_pattern(pattern)
                
            except Exception as e:
                print(f"  Warning: Skipped entry {i}: {e}")
                continue
        
        # Save in new format
        new_path = Path("models") / f"BTC_model_{tf}.pkl"
        new_path.parent.mkdir(exist_ok=True)
        memory.save(new_path)
        
        print(f"  ✅ Migrated {len(memory.patterns)} patterns")

if __name__ == "__main__":
    migrate_models()
```

Run it:
```bash
python scripts/migrate_models.py
```

### Step 4: Migrate Credentials

#### Original Location
```
r_key.txt
r_secret.txt
```

#### Enhanced Location
```
.env file:
PT_ROBINHOOD_API_KEY=your_key_here
PT_ROBINHOOD_PRIVATE_KEY=your_base64_private_key_here
```

#### Migration Script

```bash
# scripts/migrate_credentials.sh
#!/bin/bash

if [ -f "../original/r_key.txt" ]; then
    API_KEY=$(cat ../original/r_key.txt)
    echo "PT_ROBINHOOD_API_KEY=$API_KEY" >> .env
    echo "✅ Migrated API key"
fi

if [ -f "../original/r_secret.txt" ]; then
    PRIVATE_KEY=$(cat ../original/r_secret.txt)
    echo "PT_ROBINHOOD_PRIVATE_KEY=$PRIVATE_KEY" >> .env
    echo "✅ Migrated private key"
fi
```

Run it:
```bash
chmod +x scripts/migrate_credentials.sh
./scripts/migrate_credentials.sh
```

### Step 5: Parallel Testing

Run both systems side-by-side in paper trading mode to compare results.

```bash
# Terminal 1: Original system (paper trading)
cd /path/to/original
# ... start original system ...

# Terminal 2: Enhanced system (paper trading)
cd /path/to/enhanced
docker-compose up -d

# Compare signals
# Original: Check terminal output
# Enhanced: curl http://localhost:8000/api/signals
```

### Step 6: Cutover

Once you're confident the enhanced system works correctly:

```bash
# Stop original system
cd /path/to/original
# Kill processes

# Start enhanced system in live mode
cd /path/to/enhanced
# Edit .env: PT_TRADING_MODE=live
docker-compose down
docker-compose up -d

# Monitor
docker-compose logs -f
```

## 🔄 Data Mapping

### File Locations

| Original | Enhanced | Notes |
|----------|----------|-------|
| `gui_settings.json` | `.env` | See config migration |
| `r_key.txt` | `.env` variable | Secure |
| `r_secret.txt` | `.env` variable | Secure |
| `memories_*.txt` | `models/*.pkl` | Binary format |
| `memory_weights_*.txt` | `models/*.pkl` | Included |
| `*_current_price.txt` | Redis cache | Real-time |
| `trader_status.json` | PostgreSQL | Persistent |
| `trade_history.jsonl` | PostgreSQL | Queryable |

### Signal Compatibility

Both systems write the same signal files for backward compatibility:

```
data/BTC/long_dca_signal.txt    # 0-7 strength
data/BTC/short_dca_signal.txt   # 0-7 strength
```

So you can mix and match components during migration.

## 🧪 Testing Checklist

Before going live, verify:

- [ ] Configuration migrated correctly
- [ ] All coins have trained models
- [ ] Models are fresh (< 14 days old)
- [ ] API credentials work
- [ ] Paper trading produces signals
- [ ] Signals match expected levels
- [ ] Dashboard shows data
- [ ] Logs are being written
- [ ] Health checks pass
- [ ] Metrics are collected

### Test Script

```bash
# scripts/test_migration.sh
#!/bin/bash

echo "🧪 Testing migrated system..."

# 1. Check configuration
echo "1. Checking configuration..."
python -c "from config import get_settings; s = get_settings(); print(f'Coins: {s.trading.coins}')"

# 2. Check models
echo "2. Checking trained models..."
ls -lh models/

# 3. Check API
echo "3. Testing API..."
curl -f http://localhost:8000/api/health || echo "❌ API not responding"

# 4. Check signals
echo "4. Checking signals..."
python signals.py once

# 5. Check database
echo "5. Checking database..."
python -c "from database import engine; engine.connect()" && echo "✅ Database OK"

echo "✅ Migration tests complete!"
```

## 🚨 Rollback Plan

If something goes wrong:

```bash
# 1. Stop enhanced system
cd /path/to/enhanced
docker-compose down

# 2. Restore original system
cd /path/to/original
tar -xzf ~/powertrader_backup_*.tar.gz

# 3. Restart original
# ... start original system ...

# 4. Investigate issue
cd /path/to/enhanced
docker-compose logs > issue_log.txt
# Review logs, fix issue, retry
```

## 📞 Support

If you encounter issues:

1. Check logs: `docker-compose logs`
2. Review TROUBLESHOOTING.md
3. Join Discord: [link]
4. Open issue: [GitHub]

## ✅ Post-Migration

Once successfully migrated:

1. Archive original system: `mv original original_archived`
2. Update documentation
3. Train team on new system
4. Setup monitoring alerts
5. Schedule regular backups

---

**Migration Time Estimate:** 1-2 hours

**Difficulty:** Medium (mostly automated)

**Risk Level:** Low (rollback available)

**Recommended:** Migrate during off-hours
