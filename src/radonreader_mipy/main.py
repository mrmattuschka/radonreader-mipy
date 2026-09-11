from struct import unpack
from time import sleep_ms, time

import network
import ujson
import urequests
from machine import WDT, deepsleep
from sync_ubt import SyncBLE
from ubluetooth import UUID

__version__ = "2.0.0"

SVC_UUID = UUID("00001523-1212-efde-1523-785feabcd123")
# Write characteristic UUID -> where the reader triggers an update
RDW_UUID = UUID("00001524-1212-efde-1523-785feabcd123")
# Radon readout characteristic UUID
RDR_UUID = UUID("00001525-1212-efde-1523-785feabcd123")

config_file = "config.json"


def wifi_connect(ssid: str, pw: str) -> bool:
    sta_if = network.WLAN(network.STA_IF)

    if sta_if.isconnected():
        print("Connected. Network config:", sta_if.ifconfig())
        return True

    print("Connecting to network...")
    sta_if.active(True)
    sta_if.connect(ssid, pw)
    timeout = time() + 30  # 30 s timeout for connecting to wifi
    while not sta_if.isconnected() and time() < timeout:
        pass

    if sta_if.isconnected():
        print("Connected. Network config:", sta_if.ifconfig())
    else:
        print("ERROR: Connection failed/timeout while connecting.")

    return sta_if.isconnected()


def connect_and_read_radon():
    print("\n--- STARTING RADON READOUT ROUTINE ---")
    if not wifi_connect(config["ssid"], config["pass"]):
        raise RuntimeError("WiFi connection failed")

    radoneye = sbt.connect(config["radoneye_addr_type"], config["radoneye_addr"])
    if not radoneye:
        raise RuntimeError("BLE connection failed")

    # Get device name from generic access SVC
    generic_acc = radoneye.get_service(0x1800)
    devname = "Unknown device"
    if generic_acc:
        devname_chr = generic_acc[0].get_characteristic(0x2A00)
        if devname_chr:
            devname = devname_chr[0].read()
            if devname:
                devname = devname.decode()
                print("Found RadonEye device:", devname)

    # Find the RadonEye SVC & CHR
    radoneye_svc = radoneye.get_service(SVC_UUID)
    if not radoneye_svc:
        raise RuntimeError("RadonEye service not found")

    print("Found RadonEye SVC, locating CHR...")
    radoneye_write_chr = radoneye_svc[0].get_characteristic(RDW_UUID)
    if not radoneye_write_chr:
        raise RuntimeError("Write characteristic not found")

    print("Found write CHR, triggering update...")
    status = radoneye_write_chr[0].write(b"\x50")
    print("Write status:", status)
    sleep_ms(100)
    print("Locating Radon readout CHR...")
    radoneye_read_chr = radoneye_svc[0].get_characteristic(RDR_UUID)
    if not radoneye_read_chr:
        raise RuntimeError("Read characteristic not found")

    radon_value = radoneye_read_chr[0].read()
    if not radon_value:
        raise RuntimeError("Radon value read returned empty")
    radon_value = unpack("<f", radon_value[2:6])[0] * 37  # Unpack, convert to Bq
    print("Decoded radon value:", radon_value, "Bq")

    url = config["homematic_addr"].format(
        radon=radon_value,
        ise_id=config["homematic_ise_id"],
    )
    print("Sending HTTP request:", url)
    resp = urequests.get(url)
    resp.close()
    print("Done.")


with open(config_file, "r") as f:
    config = ujson.load(f)

if config["reset_timer"] > 0:
    WDT(timeout=config["reset_timer"] * 1000)

sbt = SyncBLE()
if config["status_led"]:
    from led import LED

    led = LED()
else:
    led = None

try:
    connect_and_read_radon()
    if led:
        led.breathe((64, 0, 0), times=1)
except Exception as e:
    print("Error:", e)
    if led:
        led.breathe((0, 64, 0), times=3)
