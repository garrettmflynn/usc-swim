#!/usr/bin/env bash
# One-shot local run: check the page, then serve the built dashboard.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements.txt

python -m pytest tests/ -q
python scrape.py

if [ ! -d docs/assets ]; then
  echo "No built app yet — building it once."
  (cd app && npm install && npm run build)
fi

echo
echo "USC Swim: http://localhost:8000  (ctrl-C to stop)"
python -m http.server 8000 -d docs
