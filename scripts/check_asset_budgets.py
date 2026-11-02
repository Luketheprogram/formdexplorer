"""Check first-party release asset budgets without accessing user data."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
budgets = json.loads((root / 'docs/performance-budgets.json').read_text())['budgets']
totals = {
    'first_party_javascript_bytes': sum(p.stat().st_size for p in (root / 'static/js').glob('*.js')),
    'first_party_css_bytes': sum(p.stat().st_size for p in (root / 'static/css').glob('*.css')),
}
problems = [key for key, value in totals.items() if value > budgets[key]]
print(json.dumps({'measured_bytes': totals, 'problems': problems, 'scope': 'First-party source bytes; no claim about external SDKs, compressed transfer sizes or mobile field performance.'}, indent=2))
raise SystemExit(bool(problems))
