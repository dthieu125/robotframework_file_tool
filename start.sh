set -e

echo ""
echo "================================================"
echo "  Robot Framework Web Tool"
echo "================================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERR] python3 can not found"
    exit 1
fi

# Create venv
if [ ! -d "venv" ]; then
    echo "[INFO] Create virtual environment..."
    python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install deps
echo "[INFO] Install dependencies..."
pip install -q -r requirements.txt

# Create dirs
mkdir -p uploads results

# Local IP
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")

echo ""
echo "[OK] All are ready!"
echo ""
echo "================================================"
echo "  Tool:"
echo "    Local  : http://localhost:5000"
echo "    Network: http://${LOCAL_IP}:5000"
echo "================================================"
echo ""

# Open browser (macOS / Linux)
if command -v xdg-open &>/dev/null; then
    (sleep 2 && xdg-open http://localhost:5000) &
elif command -v open &>/dev/null; then
    (sleep 2 && open http://localhost:5000) &
fi

python3 app.py
