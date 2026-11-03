# Auto Charging

Limita la carga de **portátiles y teléfonos** con un enchufe inteligente Tuya: enciende el enchufe cuando la batería baja de un umbral y lo apaga al llegar al máximo, para alargar la vida de la batería.

A diferencia de un simple temporizador, decide con el **estado real** de la batería y, si no hay, con una **estimación a partir del consumo** que mide el enchufe.

## Cómo decide

Por orden de prioridad:

0. **Home Assistant**: la batería del móvil con la app Companion (ver más abajo).
1. **Batería remota**: el teléfono u otro equipo envía su porcentaje por HTTP.
2. **Batería local**: el portátil donde corre el programa (`psutil`).
3. **Estimación por consumo**: integra los vatios del enchufe y detecta el fin de carga cuando la potencia cae (fase de mantenimiento del cargador). Se recalibra al 100 % en cada fin de carga.

Seguridades: corte absoluto (`BATTERY_ABS_MAX`), tiempo máximo de carga y verificación del estado del enchufe tras cada orden.

## Requisitos

- Python 3.9+
- Enchufe compatible con [tinytuya](https://github.com/jasonacox/tinytuya) (Tuya / Smart Life). Para la estimación por consumo, un modelo **con medición de energía**.
- Un equipo siempre encendido en la misma red (PC, Raspberry Pi…) que ejecute el programa.

## Instalación

```bash
git clone https://github.com/<tu-usuario>/auto-charging.git
cd auto-charging
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[all]"     # all = tinytuya (enchufe Tuya local) + psutil (bateria del portatil)
cp credentials.env.example credentials.env
```

## Configuración

1. Reserva una IP fija para el enchufe en tu router (la **IP local**, no la pública que muestra la app).
2. Obtén `DEVICE_ID` y `LOCAL_KEY` con `python -m tinytuya wizard` (guía en la documentación de tinytuya).
3. Rellena `credentials.env`. Todas las opciones están comentadas en `credentials.env.example`.

> `credentials.env` está en `.gitignore`. **No lo subas nunca** a GitHub: contiene la clave de tu dispositivo.

## Uso

```bash
autocharging --probe     # muestra lo que reporta el enchufe (DPS, potencia)
autocharging --dry-run   # decide y registra, sin conmutar el enchufe
autocharging             # funcionamiento normal
```

Empieza siempre con `--probe` (para confirmar `POWER_DP` y `POWER_SCALE`) y luego `--dry-run` durante un rato.

### Cargar un teléfono

Activa el receptor en `credentials.env`:

```
TARGET_DEVICE=movil
REMOTE_PORT=8765
REMOTE_TOKEN="una-clave-larga"
```

y envía el porcentaje desde el teléfono. En Android con Termux, usa [`deploy/termux_battery_sender.sh`](deploy/termux_battery_sender.sh). En iOS, un atajo de Atajos que haga la misma petición:

```
POST http://IP_DEL_PC:8765/battery
X-Token: una-clave-larga
{"device": "movil", "percent": 54, "plugged": true}
```

Si pasan `REMOTE_MAX_AGE` segundos sin datos, el programa pasa a la estimación por consumo.

### Varios enchufes

Una instancia por enchufe, cada una con su `credentials.env` (`--env-file ruta`).

### Arranque automático

- **Linux**: [`deploy/autocharging.service`](deploy/autocharging.service) (systemd).
- **Windows**: Programador de tareas, "al iniciar sesión", ejecutando `autocharging`.

## Home Assistant (Android, iPhone, Windows y Green)

Alternativa recomendada si ya usas Home Assistant: la app **Companion** da la batería del móvil (Android e iPhone, sin scripts) y HA controla el enchufe. Hay dos formas de ejecutarlo:

- **Add-on para Home Assistant Green / HA OS**: añade este repositorio en *Complementos → Tienda → ⋮ → Repositorios* e instala **Auto Charging**.
- **Script en Windows** (o cualquier PC): `HA_URL`, `HA_TOKEN` y las entidades en `credentials.env`.

Guía paso a paso, con los nombres de las entidades y la resolución de problemas, en [docs/home-assistant.md](docs/home-assistant.md). Expone `sensor.autocharging_<dispositivo>` en HA y puede avisarte al móvil cuando ya puedes desenchufar.

## Reglas de carga personalizadas

El rango fijo 20-80 % solo sirve si cargas siempre en las mismas condiciones. Con `rules.toml` defines **franjas horarias** con su propio comportamiento:

```bash
cp rules.example.toml rules.toml
```

```toml
# Móvil de noche: a las 07:30 debe estar al 100 %
[[rule]]
name = "noche"
mode = "ready_by"
start = "22:00"
end = "07:30"
ready_by = "07:30"   # hora a la que lo desenchufas
hold_low = 90        # nivel de espera: se mantiene entre 90 y 95 %
hold_high = 95
target = 100

# De día: cuidado de la batería
[[rule]]
name = "dia"
mode = "range"
start = "07:30"
end = "22:00"
low = 20
high = 80
```

- Se aplica la **primera regla** que coincide con el día y la hora (`days = ["mon", "tue", ...]` es opcional). Si ninguna coincide, se usan `BATTERY_LOW` y `BATTERY_HIGH`.
- **`range`**: enciende por debajo de `low` y apaga por encima de `high`.
- **`ready_by`**: mantiene el dispositivo en el nivel de espera y calcula cuándo empezar el último tramo para llegar a `target` **justo a la hora indicada**, usando el tiempo de carga aprendido de tu cargador. Así pasa el mínimo tiempo posible al 100 %.
- Un nivel de espera más bajo (p. ej. 80-90 %) cuida más la batería; uno más alto te da margen si desenchufas antes de tiempo.
- El límite global `BATTERY_ABS_MAX` se aplica a las reglas `range`; en `ready_by` el tope es `target`.

## Aprendizaje y consejos

El programa guarda en SQLite (`autocharging.db`) el porcentaje, la potencia y el estado del enchufe en cada ciclo, y aprende:

- **Sesiones y cargadores**: agrupa las cargas por potencia máxima (±20 %). Distingue el cargador **habitual** de uno **puntual** (coche, otro cargador, trabajo…). No conoce tu ubicación: lo deduce por potencia y hora.
- **Curva de carga**: cuántos minutos necesita cada tramo del 0 al 100 % con cada cargador. La usa en `ready_by` para decidir cuándo empezar. Hasta que tiene datos usa valores genéricos.
- **Hora de desconexión habitual**: necesita que el dispositivo informe de `plugged` (el portátil lo hace solo; el móvil, con el script de Termux actualizado).

```bash
autocharging --report
```

muestra los cargadores detectados, los tiempos de carga estimados, la hora de desconexión sugerida para `ready_by` y consejos de salud de la batería (tiempo al 95-100 %, descargas por debajo del 10 %, ciclos al día). Son consejos **orientativos**: no mide la temperatura ni el estado real de la celda. Para que aprenda bien, déjalo funcionando varios días.

El historial se guarda en local y se borra pasados 180 días. Desactívalo con `HISTORY_DB=` (vacío).

## Limitaciones

- La estimación es aproximada: el uso del equipo durante la carga y la temperatura la desvían. Ajusta `CAPACITY_WH`.
- Sin medición de potencia solo funcionan las fuentes 1 y 2, y el aprendizaje por cargador queda muy limitado.
- Una señal Wi-Fi débil en el enchufe provoca fallos de comunicación; el programa reintenta pero no puede actuar sin conexión.
- iOS no permite leer la batería desde fuera: necesita el atajo.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest
```

## Créditos y licencia

Idea original: Auto-Laptop-Charging, de Aaditya Joshi (MIT). Este proyecto es una reescritura con soporte multi-dispositivo y estimación por consumo. Licencia MIT, ver [LICENSE](LICENSE).
