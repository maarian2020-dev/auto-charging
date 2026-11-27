# Integración con Home Assistant (Android, iPhone, Windows y Green)

Con Home Assistant (HA) no necesitas scripts en el móvil ni la `LOCAL_KEY` de Tuya: la app **Companion** de HA da la batería del móvil (Android o iPhone) y HA controla el enchufe.

## 1. Elige dónde corre Auto Charging

| Opción | Cuándo usarla |
|---|---|
| **A. Add-on en Home Assistant Green** (o cualquier HA OS) | La más cómoda: arranca sola y no necesitas otro equipo. Controla un dispositivo por add-on. |
| **B. Script Python en un PC con Windows** | Si tu HA está en una máquina virtual de Windows, o quieres controlar varios dispositivos (una instancia por dispositivo), o el portátil se controla a sí mismo. |

## 2. Preparar Home Assistant

### El enchufe
Añade el enchufe a HA y comprueba que existen:
- una entidad `switch.…` (para encender y apagar), y
- idealmente un sensor de potencia `sensor.…` en W (los enchufes con medición de energía lo exponen). Sin él funciona la regla por porcentaje, pero se pierden la detección de fin de carga y el aprendizaje de cargadores.

Integraciones habituales para enchufes Tuya / Smart Life: la integración oficial **Tuya** (por la nube) o integraciones locales de la comunidad (por ejemplo, LocalTuya).

### El móvil con la app Companion
Instala la app oficial de Home Assistant, inicia sesión en tu servidor y activa los sensores de batería:

- **Android:** *Ajustes → Companion app → Administrar sensores → Sensores de batería*. Activa el nivel y el estado de carga. En *Frecuencia de actualización de sensores* elige la opción que actualiza con más frecuencia mientras carga (si aparece "Rápido mientras se carga", úsala): así el porcentaje llega cada minuto durante la carga.
- **iPhone:** *Ajustes → Companion App → Sensores* (comprueba que "Sensores enviados" no esté en "Ninguno"). iOS actualiza los sensores solo en situaciones limitadas (cambios de ubicación, app abierta, y en segundo plano con la frecuencia que decide iOS), así que el porcentaje puede llegar con retraso. Auto Charging lo tolera: si el dato es antiguo (`HA_MAX_AGE_MINUTES`), pasa a estimar por el consumo del enchufe. Abrir la app o hacer "Actualizar sensores" refresca el dato.

### Ver los nombres de las entidades
En HA: *Herramientas para desarrolladores → Estados* y busca `battery`. Ejemplos habituales:

| Dispositivo | Nivel | Estado de carga |
|---|---|---|
| Android | `sensor.<nombre>_battery_level` | `sensor.<nombre>_battery_state` (valores como `charging`, `discharging`, `full`) |
| iPhone | `sensor.<nombre>_battery_level` | `sensor.<nombre>_battery_state` (valores `Charging`, `Not Charging`, `Full`) |

Los nombres exactos dependen del nombre de tu dispositivo: copia el que veas en Estados.

### Token de acceso (solo para la opción B)
*Tu perfil (abajo a la izquierda) → Seguridad → Tokens de acceso de larga duración → Crear token.* Cópialo en el momento: no se vuelve a mostrar. Es como una contraseña: no lo subas a GitHub.

## 3. Opción A: add-on en Home Assistant Green

1. *Ajustes → Complementos → Tienda de complementos* (en versiones recientes se llama también "Apps").
2. Menú **⋮** (arriba a la derecha) → **Repositorios** → añade `https://github.com/maarian2020-dev/auto-charging`.
3. Recarga la página, busca **Auto Charging** e instálalo.
4. Pestaña **Configuración**: rellena `ha_switch_entity`, `ha_power_entity`, `ha_battery_entity`, `ha_battery_state_entity` y, si quieres avisos, `ha_notify_service` (por ejemplo `notify.mobile_app_pixel_8`).
5. Arráncalo y abre la pestaña **Registro**. Prueba primero con el interruptor del enchufe a mano y revisa que `bateria=…%` coincide con la del móvil.
6. Las reglas están en `rules.toml`, en la carpeta de configuración del add-on (se crea en el primer arranque con un ejemplo; edítala con el complemento *File editor* o *Samba*) y reinicia el add-on.

El add-on usa el acceso interno de HA, así que no necesita token. Crea el sensor `sensor.autocharging_<target_device>` con el porcentaje y atributos (origen, regla, última acción), útil para tu panel.

## 4. Opción B: script en Windows

### Home Assistant en Windows
Home Assistant Core no se ejecuta de forma nativa en Windows. Las formas habituales son:

- **Máquina virtual con Home Assistant OS** (VirtualBox, Hyper-V o VMware; la web de HA ofrece imagen para cada una). Usa red en **modo puente (bridged)** para que la VM tenga IP en tu red y el móvil pueda llegar a ella. Con esta opción tienes add-ons, así que también sirve la opción A. Inconveniente: si el PC se apaga o reinicia (por actualizaciones de Windows, por ejemplo), HA se detiene y Auto Charging también.
- **Docker Desktop (contenedor de HA):** funciona, pero **sin add-ons** y con limitaciones de red; en ese caso usa siempre esta opción B.

Un equipo dedicado y siempre encendido (como HA Green) es más fiable que un PC de uso diario.

### Instalar y configurar el script
```powershell
git clone https://github.com/maarian2020-dev/auto-charging.git
cd auto-charging
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[all]"
copy credentials.env.example credentials.env
```
Edita `credentials.env` y descomenta el bloque de Home Assistant (`HA_URL`, `HA_TOKEN`, `HA_SWITCH_ENTITY`, `HA_POWER_ENTITY`, `HA_BATTERY_ENTITY`…). `HA_URL` es `http://homeassistant.local:8123` o la IP de HA (por ejemplo `http://192.168.1.50:8123`).

Prueba:
```powershell
autocharging --probe      # lee cada entidad y muestra su valor y la hora del ultimo dato
autocharging --dry-run    # decide y registra sin conmutar el enchufe
autocharging              # funcionamiento normal
```

**Portátil que se controla a sí mismo:** deja `HA_BATTERY_ENTITY` vacío y `TARGET_DEVICE=local`. Leerá la batería del propio portátil y usará HA solo para el enchufe.

### Arranque automático
*Programador de tareas → Crear tarea → desencadenador "Al iniciar sesión" → acción "Iniciar un programa"* con `C:\ruta\auto-charging\.venv\Scripts\autocharging.exe`, y como carpeta de inicio la del proyecto (para que encuentre `credentials.env`).

## 5. Resolución de problemas

| Síntoma | Causa probable |
|---|---|
| `token no valido` | Token mal copiado o revocado. Crea otro. |
| `no encontrado (revisa el entity_id)` | El nombre de la entidad no coincide; cópialo de *Herramientas para desarrolladores → Estados*. |
| `sin conexion con Home Assistant` | URL o puerto incorrectos, o el equipo con el script no ve a HA (en una VM de Windows, red no puente). |
| `Dato de bateria antiguo` | El móvil no ha informado en `HA_MAX_AGE_MINUTES`. En Android, revisa la frecuencia de sensores y las restricciones de batería de la app; en iPhone, abre la app. |
| El enchufe no reporta potencia | Falta `HA_POWER_ENTITY` o el modelo no mide consumo. |
| La hora de desconexión no se aprende | Configura `HA_BATTERY_STATE_ENTITY` (o `HA_PLUGGED_ENTITY`). |

## Seguridad

- El enchufe se controla por HA: si HA o la red fallan, Auto Charging no puede actuar. Mantén el corte de seguridad (`BATTERY_ABS_MAX`, `MAX_CHARGE_MINUTES`).
- No subas `credentials.env` ni el token al repositorio.
