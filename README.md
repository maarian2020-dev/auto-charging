# Auto Charging

Limita la carga de **portátiles y teléfonos** con un enchufe inteligente Tuya: enciende el enchufe cuando la batería baja de un umbral y lo apaga al llegar al máximo, para alargar la vida de la batería.

A diferencia de un simple temporizador, decide con el **estado real** de la batería y, si no hay, con una **estimación a partir del consumo** que mide el enchufe.

## Cómo decide

Por orden de prioridad:

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
pip install -e .
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
{"device": "movil", "percent": 54}
```

Si pasan `REMOTE_MAX_AGE` segundos sin datos, el programa pasa a la estimación por consumo.

### Varios enchufes

Una instancia por enchufe, cada una con su `credentials.env` (`--env-file ruta`).

### Arranque automático

- **Linux**: [`deploy/autocharging.service`](deploy/autocharging.service) (systemd).
- **Windows**: Programador de tareas, "al iniciar sesión", ejecutando `autocharging`.

## Limitaciones

- La estimación es aproximada: el uso del equipo durante la carga y la temperatura la desvían. Ajusta `CAPACITY_WH`.
- Sin medición de potencia solo funcionan las fuentes 1 y 2.
- Una señal Wi-Fi débil en el enchufe provoca fallos de comunicación; el programa reintenta pero no puede actuar sin conexión.
- iOS no permite leer la batería desde fuera: necesita el atajo.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest
```

## Créditos y licencia

Idea original: Auto-Laptop-Charging, de Aaditya Joshi (MIT). Este proyecto es una reescritura con soporte multi-dispositivo y estimación por consumo. Licencia MIT, ver [LICENSE](LICENSE).
