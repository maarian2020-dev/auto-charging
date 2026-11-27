# Auto Charging

Controla un enchufe de Home Assistant para limitar la carga de un móvil o portátil, con reglas por franja horaria, carga "lista a una hora" y aprendizaje del cargador.

## Opciones

| Opción | Qué poner |
|---|---|
| `ha_switch_entity` | La entidad del enchufe, p. ej. `switch.cargador_movil` (obligatoria). |
| `ha_power_entity` | Sensor de potencia del enchufe, p. ej. `sensor.cargador_movil_potencia` (recomendado: activa la detección de fin de carga y el aprendizaje). |
| `ha_battery_entity` | Batería del dispositivo con la app Companion, p. ej. `sensor.pixel_8_battery_level` o `sensor.iphone_battery_level`. |
| `ha_battery_state_entity` | Estado de carga del dispositivo, p. ej. `sensor.pixel_8_battery_state`. Sirve para aprender la hora de desconexión. |
| `ha_plugged_entity` | Opcional: sensor que indique si está enchufado (en Android, `sensor.<movil>_charger_type`). |
| `ha_notify_service` | Opcional: servicio de notificaciones, p. ej. `notify.mobile_app_pixel_8`. |
| `target_device` | Nombre corto del dispositivo (crea `sensor.autocharging_<nombre>`). |
| `battery_low`, `battery_high`, `battery_abs_max` | Umbrales cuando no hay ninguna regla que coincida. `battery_abs_max` es el corte de seguridad. |
| `ha_max_age_minutes` | Si la batería no informa en este tiempo, se pasa a la estimación por consumo. |

## Reglas

En el primer arranque se crea `rules.toml` en la carpeta de configuración del add-on (`/addon_configs/<id>_autocharging/` desde el complemento File editor o Samba). Edítalo y reinicia el add-on.

## Consejos

- Empieza con valores prudentes y revisa el registro del add-on durante unos días.
- Al iniciar el add-on, la pestaña **Registro** muestra el informe de lo aprendido (cargadores, tiempos y consejos de salud). Reinícialo para actualizarlo.
- Un add-on controla **un** dispositivo. Para varios, usa el script de Python en un PC (una instancia por dispositivo).
