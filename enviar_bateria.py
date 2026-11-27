import time
import psutil
import requests

HA_URL = "http://192.168.1.156/api/states/sensor.laptop_battery"
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI0NDg3NjhjYjkzM2I0NWIyYmYwYWM4NGNlM2IyODFhMyIsImlhdCI6MTc5NDQzMDQzOCwiZXhwIjoyMTA5NzkwNDM4fQ.tCc1yLegO9vh5K4I6SrwYV2vIp0SvOx9TWuPOFWEdo8"

headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

print("Iniciando envío de batería del portátil a Home Assistant...")

while True:
  try:
    battery = psutil.sensors_battery()
    if battery:
      percent = int(battery.percent)
      data = {
          "state": percent,
          "attributes": {
              "unit_of_measurement": "%",
              "device_class": "battery",
              "friendly_name": "Laptop Battery",
          },
      }
      response = requests.post(HA_URL, headers=headers, json=data)
      print(f"Batería enviada: {percent}% (Status: {response.status_code})")
    else:
      print("No se pudo leer la información de la batería.")
  except Exception as e:
    print(f"Error al enviar batería: {e}")

  time.sleep(60)