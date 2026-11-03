#!/data/data/com.termux/files/usr/bin/bash
# Android (Termux + Termux:API + jq): envia el % de bateria cada minuto.
# Rellena las tres variables.
SERVER="http://IP_DEL_PC:8765/battery"
TOKEN="TU_TOKEN"
DEVICE="movil"

while true; do
  STATUS=$(termux-battery-status)
  P=$(echo "$STATUS" | jq .percentage)
  PLUGGED=$(echo "$STATUS" | jq '.plugged != "UNPLUGGED"')   # true/false
  curl -s -m 10 -X POST "$SERVER" -H "X-Token: $TOKEN" \
       -d "{\"device\":\"$DEVICE\",\"percent\":$P,\"plugged\":$PLUGGED}" > /dev/null
  sleep 60
done
