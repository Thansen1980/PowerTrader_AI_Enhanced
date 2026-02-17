#!/bin/bash
# Quick start script for PowerTrader Enhanced

set -e

echo "🚀 PowerTrader Enhanced - Quick Start"
echo "======================================"
echo

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating from template..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo
    echo "📝 IMPORTANT: Edit .env file with your settings before continuing!"
    echo "   Especially:"
    echo "   - PT_ROBINHOOD_API_KEY"
    echo "   - PT_ROBINHOOD_PRIVATE_KEY"
    echo "   - PT_TRADING_MODE (paper/live)"
    echo
    read -p "Press Enter after editing .env to continue..."
fi

echo "📦 Creating directories..."
mkdir -p data models logs

echo "✅ Directories created"
echo

# Check if Docker is available
if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    echo "🐳 Docker detected. Do you want to:"
    echo "  1) Run with Docker (recommended)"
    echo "  2) Run locally with Python"
    read -p "Choice (1 or 2): " choice
    
    if [ "$choice" = "1" ]; then
        echo
        echo "🐳 Starting with Docker..."
        docker-compose up -d
        echo
        echo "✅ Services started!"
        echo
        echo "📊 Access points:"
        echo "  - API: http://localhost:8000"
        echo "  - Dashboard: http://localhost:3000"
        echo "  - Grafana: http://localhost:3001"
        echo
        echo "📝 View logs:"
        echo "  docker-compose logs -f"
        echo
        echo "🛑 Stop services:"
        echo "  docker-compose down"
        exit 0
    fi
fi

echo "🐍 Running locally with Python..."
echo

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.10 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "Found Python $PYTHON_VERSION"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

echo "📦 Activating virtual environment..."
source venv/bin/activate

echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Dependencies installed"
echo

echo "🎓 What would you like to do?"
echo "  1) Train models (first time setup)"
echo "  2) Generate signals only"
echo "  3) Start paper trading (signals + trader)"
echo "  4) Start API server"
echo "  5) Start everything"
read -p "Choice (1-5): " action

case $action in
    1)
        echo "🎓 Training models for all coins..."
        python trainer.py
        ;;
    2)
        echo "📊 Starting signal generator..."
        python signals.py
        ;;
    3)
        echo "📈 Starting paper trading..."
        python signals.py &
        SIGNALS_PID=$!
        sleep 2
        python trader.py &
        TRADER_PID=$!
        echo
        echo "✅ Paper trading started!"
        echo "   Signals PID: $SIGNALS_PID"
        echo "   Trader PID: $TRADER_PID"
        echo
        echo "Press Ctrl+C to stop..."
        trap "kill $SIGNALS_PID $TRADER_PID 2>/dev/null; exit" INT
        wait
        ;;
    4)
        echo "🌐 Starting API server..."
        python api.py
        ;;
    5)
        echo "🚀 Starting all services..."
        python api.py &
        API_PID=$!
        sleep 2
        python signals.py &
        SIGNALS_PID=$!
        sleep 2
        python trader.py &
        TRADER_PID=$!
        echo
        echo "✅ All services started!"
        echo "   API PID: $API_PID"
        echo "   Signals PID: $SIGNALS_PID"
        echo "   Trader PID: $TRADER_PID"
        echo
        echo "📊 Access API at: http://localhost:8000"
        echo
        echo "Press Ctrl+C to stop..."
        trap "kill $API_PID $SIGNALS_PID $TRADER_PID 2>/dev/null; exit" INT
        wait
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac
