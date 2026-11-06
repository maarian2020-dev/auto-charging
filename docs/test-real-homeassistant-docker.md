# Fase de prueba real: portátil + enchufe «Laptop Charger» + Home Assistant en Docker

Esta guía comprueba, con tu hardware real, que Auto Charging puede leer la batería del portátil, leer el consumo del enchufe y **encender y apagar el enchufe a través de Home Assistant**.

- **Dispositivo:** portátil con Windows (la batería se lee del propio portátil).
- **Enchufe:** «Laptop Charger» (Tuya, mide consumo).
- **Home Assistant:** en Docker o máquina virtual, accesible desde el PC (por ejemplo `http://192.168.1.156`).
- **Duración:** unos 60-90 minutos con las fases T0 a T8. T9 y T10 son opcionales.

Cada fase tiene un **criterio de aprobación**. No pases a la siguiente si la anterior falla.

---

## T0. Seguridad y requisitos

Antes de empezar:

- El portátil debe estar **enchufado** y con **al menos 40 % de batería**.
- Home Assistant debe abrirse desde el navegador del portátil.
- No dejes el PC desatendido durante las fases T6 a T9.
- Nunca pegues el token de Home Assistant en un chat ni lo subas a GitHub.

**Cómo dejar el enchufe encendido en cualquier momento** (después de crear `credentials.test.env` en T3), si algo se interrumpe:

```powershell
python -c "from autocharging.config import Config; from autocharging.ha import HAClient, HAPlug; c=Config.from_env('credentials.test.env'); print(HAPlug(c, HAClient(c.ha_url, c.ha_token)).set_state(True))"
```

También puedes encenderlo a mano desde la app de Tuya o desde Home Assistant.

**Aprobado si:** cumples los requisitos y tienes a mano cómo dejar el enchufe encendido.

---

## T1. Instalar la versión de prueba

En PowerShell, dentro de `C:\Users\nic_m\auto-charging` y con el entorno activo (`(.venv)` al principio de la línea):

```powershell
git switch main
git pull
git apply --check $HOME\Downloads\fase-test-real.patch
git apply $HOME\Downloads\fase-test-real.patch
pytest -q
autocharging --help
```

**Aprobado si:** `pytest` termina en verde y la ayuda muestra `--discover`, `--selftest`, `--actuate` y `--test-cycle`.

---

## T2. Token y descubrimiento de entidades

1. En Home Assistant: tu nombre (abajo a la izquierda) → **Seguridad** → **Tokens de acceso de larga duración** → **Crear token**. Cópialo; no se vuelve a mostrar.
2. Lista lo que Home Assistant ve. El programa pedirá la URL y el token, y **no muestra el token** al escribirlo:

```powershell
autocharging --discover laptop
```

El texto `laptop` filtra por nombre. Sin filtro verás todos los enchufes y sensores.

Debes ver algo como:

```
Enchufes (HA_SWITCH_ENTITY):
  switch.laptop_charger  [estado: on]  - Laptop Charger
Sensores de potencia (HA_POWER_ENTITY):
  sensor.laptop_charger_potencia  [valor: 70 W]  - ...
```

Apunta el nombre exacto del enchufe y del sensor de potencia.

**Si «Laptop Charger» no aparece** en Home Assistant, hay que añadir el enchufe:

- *Ajustes → Dispositivos y servicios → Añadir integración → Tuya* y seguir el asistente (suele pedir iniciar sesión con la app Tuya o Smart Life). Los pasos exactos pueden variar con la versión de Home Assistant; consulta la documentación de la integración Tuya.
- Tras añadirla, repite `autocharging --discover laptop`.

**Si falla la conexión:** prueba con `http://192.168.1.156:8123` en lugar de sin puerto, y comprueba que el token es el correcto.

**Aprobado si:** aparecen el enchufe `switch.…` y, si el modelo lo expone, un sensor de potencia en vatios.

---

## T3. Archivo de configuración de prueba

Crea un archivo **separado** del `credentials.env` actual, para no tocar tu configuración funcional:

```powershell
cd $HOME\auto-charging
notepad credentials.test.env
```

Contenido (cambia los tres valores marcados):

```
PLUG_BACKEND=homeassistant
HA_URL=http://192.168.1.156
HA_TOKEN=PEGA_AQUI_EL_TOKEN
HA_SWITCH_ENTITY=switch.CAMBIA_ESTO
HA_POWER_ENTITY=sensor.CAMBIA_ESTO
TARGET_DEVICE=local

HISTORY_DB=prueba.db
RULES_FILE=
POLL_SECONDS=30
BATTERY_LOW=20
BATTERY_HIGH=80
BATTERY_ABS_MAX=90
MAX_CHARGE_MINUTES=360
```

Notas:

- **No pongas `HA_BATTERY_ENTITY`**: así el programa lee la batería del propio portátil.
- Los archivos `*.env` están en el `.gitignore`: este no se sube a GitHub. Aun así, **bórralo al terminar** (T11).
- Si Home Assistant usa el puerto 8123, escribe `HA_URL=http://192.168.1.156:8123`.
- Si la integración del enchufe tarda en reflejar los cambios, añade `HA_SETTLE_SECONDS=5`.

**Aprobado si:** el archivo está guardado y sin errores de formato (una variable por línea, sin comillas obligatorias).

---

## T4. Lectura del enchufe

```powershell
autocharging --env-file credentials.test.env --probe
```

**Debe mostrar** el estado del enchufe de Home Assistant (`on`), el valor de potencia y la hora del último dato.

**Aprobado si:** el enchufe aparece `on`, la potencia es de varios vatios (con el portátil cargando suele rondar los 30-90 W) y no hay errores.

| Si ves | Causa probable |
|---|---|
| `token no valido` | Token mal copiado o con espacios |
| `no encontrado (revisa el entity_id)` | El nombre de la entidad no coincide con T2 |
| `sin conexion con Home Assistant` | URL o puerto incorrectos, o Home Assistant apagado |

---

## T5. Autodiagnóstico de solo lectura

```powershell
autocharging --env-file credentials.test.env --selftest
```

Comprueba, **sin tocar el enchufe**: Home Assistant y token, lectura del enchufe, potencia, batería del portátil, coherencia entre ambos y umbrales.

**Aprobado si:** termina con `RESULTADO: APTO` (o `APTO CON AVISOS` y entiendes los avisos). Un `NO APTO` indica qué falla.

Avisos habituales:

- *Enchufe ON pero casi sin consumo*: el cargador no está conectado al portátil o el portátil está al 100 %.
- *Incoherencia*: el enchufe consume pero Windows dice que no está enchufado.

---

## T6. Apagado y encendido real

```powershell
autocharging --env-file credentials.test.env --selftest --actuate
```

El programa pregunta antes de actuar. Responde `s`. Entonces:

1. Apaga el enchufe y comprueba que Home Assistant lo confirma.
2. Espera 8 segundos y comprueba que el consumo baja a casi 0 W y que Windows detecta que se cortó la carga.
3. Vuelve a encenderlo y lo confirma.

**Termina siempre con el enchufe encendido**, incluso si algo falla.

**Aprobado si:** `Apagado confirmado`, `Encendido confirmado`, y la respuesta tarda **menos de 8 segundos**. Si sale `Respuesta lenta`, sube `HA_SETTLE_SECONDS` o `POLL_SECONDS`.

Si ves `El encendido NO se confirmo`, enciende el enchufe a mano (ver T0) y no sigas hasta aclarar el motivo.

---

## T7. Simulacro (sin conmutar)

```powershell
autocharging --env-file credentials.test.env --dry-run
```

Déjalo **10 minutos** y detenlo con `Ctrl+C`. Deberías ver una línea cada 30 segundos:

```
bateria=63% (local) enchufe=ON potencia=68.0W regla=por-defecto
```

**Aprobado si:** el porcentaje coincide con el de Windows (±1 %), la potencia es coherente y no hay avisos de enchufe sin respuesta.

Con la batería en 63 % y el rango 20-80 %, no debe decidir ninguna acción.

---

## T8. Ciclo de corte real

Esta es la prueba principal. El programa fija los umbrales **pegados al nivel actual** (apagar 2 puntos por encima, encender 1 por debajo) y espera a ver el ciclo completo.

```powershell
autocharging --env-file credentials.test.env --test-cycle
```

Requisitos: batería entre **25 % y 90 %** y enchufe encendido. Usa el portátil con normalidad (navegar, vídeo) para que la batería baje antes.

Lo que debe pasar:

1. Al subir 2 puntos: `-> enchufe APAGADO con bateria NN %`.
2. El portátil se descarga con el uso.
3. Al bajar 1 punto del nivel inicial: `-> enchufe ENCENDIDO con bateria NN %`.
4. Termina con `RESULTADO: APTO: el programa corto y reanudo la carga.`

El límite es de 45 minutos. **Al terminar, haya salido bien o mal, deja el enchufe encendido.** Si cancelas con `Ctrl+C`, también lo hace.

**Aprobado si:** se ven los dos eventos, `APAGADO` y después `ENCENDIDO`.

| Si pasa | Causa probable |
|---|---|
| Llega a 45 min sin apagar | La batería no sube por el uso intenso; reintenta con el equipo en reposo |
| Apaga pero no enciende | La batería no baja lo bastante: usa el portátil con más carga de trabajo |
| `Enchufe sin respuesta` en el registro | Respuesta lenta de Home Assistant; sube `HA_SETTLE_SECONDS` |

---

## T9. (Opcional) Hora límite `ready_by`

Prueba el plan «listo a una hora» con una ventana corta. Con el portátil entre 25 % y 85 %, genera una regla de prueba que termina a los 30 minutos:

```powershell
$pct = [int](python -c "import psutil; print(int(psutil.sensors_battery().percent))")
$now = Get-Date
$txt = @"
[[rule]]
name = "prueba-ready-by"
mode = "ready_by"
start = "$($now.AddMinutes(-5).ToString('HH:mm'))"
end = "$($now.AddMinutes(60).ToString('HH:mm'))"
ready_by = "$($now.AddMinutes(30).ToString('HH:mm'))"
hold_low = $($pct - 2)
hold_high = $pct
target = $($pct + 4)
"@
[System.IO.File]::WriteAllText("$PWD\rules.test.toml", $txt, (New-Object System.Text.UTF8Encoding $false))
```

Cambia en `credentials.test.env` la línea `RULES_FILE=` por `RULES_FILE=rules.test.toml` y ejecuta:

```powershell
autocharging --env-file credentials.test.env
```

Debe verse la regla `prueba-ready-by` activa, el enchufe manteniéndose entre `hold_low` y `hold_high`, y, unos 15 minutos antes de la hora límite, una línea como:

```
Accion: ENCENDER -> plan 'prueba-ready-by': listo a las HH:MM, faltan ~N min de carga
```

y después `objetivo NN% alcanzado`.

**Aprobado si:** aparece el plan, la carga final empieza antes de la hora límite y se detiene al alcanzar el objetivo.

Al acabar, vuelve a `RULES_FILE=` (vacío) y borra `rules.test.toml`.

---

## T10. (Opcional) Resistencia: Home Assistant se reinicia

Con el programa corriendo (`autocharging --env-file credentials.test.env`), reinicia Home Assistant desde *Ajustes → Sistema → Reiniciar Home Assistant*.

**Debe pasar:**

1. Aparecen avisos `Enchufe sin respuesta (1 seguidos)…`.
2. El programa **no se detiene** ni cambia el estado del enchufe mientras no hay respuesta.
3. Al volver Home Assistant, retoma el control y las líneas de estado normales.

**Aprobado si:** no hay errores no controlados (trazas largas) y el programa se recupera solo.

---

## T11. Cierre y limpieza

1. Deja el enchufe **encendido** y comprueba que el portátil carga.
2. Borra los archivos de prueba, que contienen el token:

```powershell
Remove-Item credentials.test.env, rules.test.toml, prueba.db -ErrorAction SilentlyContinue
```

3. Si quieres usar Home Assistant en producción, copia esos mismos valores a tu `credentials.env` real y arranca el programa con una tarea programada (ver el README).
4. **Revoca el token de prueba** en Home Assistant (*Seguridad → Tokens de acceso de larga duración → Eliminar*) si no lo vas a seguir usando, y crea uno nuevo para producción.

---

## Informe de resultados

Copia este cuadro y rellénalo. Se pueden pegar **las salidas de texto** de los comandos, pero **nunca el token** ni capturas que lo muestren.

| Fase | Resultado | Notas |
|---|---|---|
| T1 Instalación | | |
| T2 Descubrimiento | | Nombre del enchufe y del sensor |
| T4 Lectura (`--probe`) | | |
| T5 Autodiagnóstico | | |
| T6 Apagado y encendido | | Latencia (s) |
| T7 Simulacro | | |
| T8 Ciclo real | | Batería al apagar / al encender |
| T9 `ready_by` (opcional) | | |
| T10 Reinicio de HA (opcional) | | |

Para recoger el registro de la última ejecución:

```powershell
Get-Content autocharging.log -Tail 60
```

---

## Qué se aprende de esta prueba

- **Latencia real** de Home Assistant: decide el intervalo de comprobación y `HA_SETTLE_SECONDS`.
- **Si la integración del enchufe es lenta**: las integraciones por la nube suelen reflejar los cambios con retraso; una integración local reduce el problema.
- **Consumo real del cargador**: con el aprendizaje de cargadores, el programa distingue más adelante el cargador de casa de otros.
- **Qué falta** para dar el salto a Home Assistant OS y al add-on (ver `docs/propuesta-configuracion-ha.md`).
