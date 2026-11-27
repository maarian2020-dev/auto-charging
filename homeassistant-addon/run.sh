#!/usr/bin/with-contenv bashio
# Arranque del add-on Auto Charging.
# Persistente: /data (historial y logs). Editable por el usuario: /config (rules.toml).

export HISTORY_DB=/data/autocharging.db
export ALC_LOG_FILE=/data/autocharging.log
export RULES_FILE=/config/rules.toml

if [ ! -f "$RULES_FILE" ]; then
  bashio::log.info "Creando reglas de ejemplo en $RULES_FILE (editalas desde el add-on File editor / Samba)"
  cat > "$RULES_FILE" << 'RULES'
# Reglas de carga: se aplica la primera que coincida con el dia y la hora.
# Cada regla puede ser: mode = "range" (low/high) o mode = "ready_by".

# Noche: a las 07:30 debe estar al 100 %. Espera en 90-95 % y programa el ultimo tramo.
[[rule]]
name = "noche"
mode = "ready_by"
start = "22:00"
end = "07:30"
ready_by = "07:30"
hold_low = 90
hold_high = 95
target = 100

# Dia: histeresis clasica para cuidar la bateria.
[[rule]]
name = "dia"
mode = "range"
start = "07:30"
end = "22:00"
low = 20
high = 80
RULES
fi

bashio::log.info "Informe de lo aprendido hasta ahora:"
autocharging --options-json /data/options.json --report || true

bashio::log.info "Iniciando Auto Charging"
exec autocharging --options-json /data/options.json
