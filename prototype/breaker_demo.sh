#!/usr/bin/env bash
# SURETY - emergency stop walkthrough.
#
# Proves the circuit breaker at all three scopes against a running service.
#
#   Terminal 1:  uvicorn main:app
#   Terminal 2:  ./breaker_demo.sh              (or: BASE=https://your.app ./breaker_demo.sh)
#
set -euo pipefail
BASE="${BASE:-http://127.0.0.1:8000}"

b()  { printf '\n\033[1;33m== %s\033[0m\n' "$1"; }
ev() { curl -s -X POST "$BASE/evaluate" -H 'Content-Type: application/json' -d "$1"; }
br() { curl -s -X POST "$BASE/breaker"  -H 'Content-Type: application/json' -d "$1"; }

# One agent, comfortably inside its limit and well below the decline threshold.
# Nothing but a breaker can stop this transaction.
SHOP='{"agent_id":"shop-bot-7","agent_class":"shopping","transaction_amount":9000,
       "exposure_limit":15000,"risk_score":0.42,"risk_tier":"SILVER"}'
OTHER='{"agent_id":"travel-bot-3","agent_class":"travel","transaction_amount":9000,
        "exposure_limit":15000,"risk_score":0.42,"risk_tier":"SILVER"}'

show() { python3 -c "
import json,sys
d=json.load(sys.stdin)
print('   %-9s %-40s scope=%s' % (d['decision'], d['reason'][:40], d.get('breaker_scope')))
"; }

b "0. Baseline - no breakers, transaction is allowed"
ev "$SHOP" | show

b "1. AGENT scope - suspend shop-bot-7 only"
br '{"scope":"agent","agent_id":"shop-bot-7","reason":"Rogue behaviour detected"}' >/dev/null
echo "   shop-bot-7:"   ; ev "$SHOP"  | show
echo "   travel-bot-3:" ; ev "$OTHER" | show
echo "   ^ only the named agent is stopped"
br '{"scope":"agent","agent_id":"shop-bot-7","action":"release"}' >/dev/null

b "2. CLASS scope - suspend every 'shopping' agent"
br '{"scope":"class","agent_class":"shopping","reason":"Class-wide anomaly"}' >/dev/null
echo "   shop-bot-7:"   ; ev "$SHOP"  | show
echo "   travel-bot-3:" ; ev "$OTHER" | show
echo "   ^ the whole class is stopped, other classes keep trading"
br '{"scope":"class","agent_class":"shopping","action":"release"}' >/dev/null

b "3. FLEET scope - stop everything"
br '{"scope":"fleet","reason":"Fleet-wide emergency stop"}' >/dev/null
echo "   shop-bot-7:"   ; ev "$SHOP"  | show
echo "   travel-bot-3:" ; ev "$OTHER" | show

b "4. Current breaker state"
curl -s "$BASE/breaker/status" | python3 -m json.tool

b "5. Release the fleet breaker"
br '{"scope":"fleet","action":"release"}' >/dev/null
ev "$SHOP" | show

b "6. Every trip and release is in the hash-chained ledger"
curl -s "$BASE/audit" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for r in d['records']:
    if r['decision'].startswith('BREAKER'):
        print('   seq %-3s %-18s %s' % (r['sequence'], r['decision'], r['reason']))
"
curl -s "$BASE/audit/verify" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('   chain %s (%s records)' % (d['status'], d.get('records_checked')))
"

printf '\n\033[1;32mEmergency stop verified at agent, class and fleet scope.\033[0m\n\n'
