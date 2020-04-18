# RadonReader-MiPy
A Micropython-based tool for the ESP32 microcontroller to read out a RadonEye sensor using BTLE.
Radon level readouts are sent to a HomeMatic system via the web API.

### Setup
1. Copy `config_template.json` to `config.json`, adjust parameters.
2. Copy config file to ESP32, copy `btle_reader.py` to ESP32 as `main.py`
3. Reboot ESP32, check serial output to ensure everything is working.

### Config
| Parameter          | Default value                                                                  | Description                                                              |
|:-------------------|:-------------------------------------------------------------------------------|:-------------------------------------------------------------------------|
| **ssid**               | SSID                                                                           | WiFi SSID                                                                |
| **pass**               | PASS                                                                           | WiFi password                                                            |
| **radoneye_addr**      | AA:BB:CC:DD:EE:FF                                                              | Radoneye BT MAC address                                                  |
| **radoneye_addr_type** | 1                                                                              | Radoneye BTLE address type (1 for RadonEye, 0 for spoofer)               |
| **readout_interval**   | 20                                                                             | Radon readout interval in seconds                                        |
| **homematic_addr**     | http://0.0.0.0/addons/xmlapi/statechange.cgi?ise_id={ise_id}&new_value={radon} | HomeMatic web API address                                                |
| **homematic_ise_id**   | 12345                                                                          | HomeMatic Radon ISE ID                                                   |
| **reset_timer**        | 24                                                                             | Interval for automated ESP32 reboot in hours (set to 0 to disable) |

### RadonEye spoofer
The repo contains a utility named `blte_spoofer.py`, which can be used to imitate RadonEye behavior using another ESP32 for debugging.
To use it, simply copy it to another ESP32 as its `main.py`.  
**Important:** to connect to it, make sure to set the BTLE address type in the reader's config file to 0.

### TODO
- MQTT support