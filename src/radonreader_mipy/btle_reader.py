from struct import unpack
from time import time

import network
import ujson
import urequests
from machine import WDT
from ubluetooth import UUID

from .sync_ubt import SyncBLE

__version__ = "2.0.0"

SVC_UUID    = UUID("00001523-1212-efde-1523-785feabcd123")
RDW_UUID = UUID("00001524-1212-efde-1523-785feabcd123") # Notify/write characteristic UUID -> this is where the reader writes
RDR_UUID = UUID("00001525-1212-efde-1523-785feabcd123") # Radon readout characteristic UUID

config_file = "config.json"

def wifi_connect(ssid: str, pw: str) -> bool:
    sta_if = network.WLAN(network.STA_IF)
    timeout = time() + 30 # 30 s timeout for connecting to wifi

    if not sta_if.isconnected():
        print('Connecting to network...')
        sta_if.active(True)
        sta_if.connect(ssid, pw)
        while (not sta_if.isconnected()) or (time() > timeout) :
            pass

    if sta_if.isconnected():
        print('Connected. Network config:', sta_if.ifconfig())
    else:
        print("ERROR: Connection failed/timeout while connecting.")

    return sta_if.isconnected()

def connect_and_read_radon():
    print("\n--- STARTING RADON READOUT ROUTINE ---")
    assert wifi_connect(config["ssid"], config["pass"])

    radoneye = sbt.connect(
        config["radoneye_addr_type"],
        config["radoneye_addr"]
    )
    assert radoneye

    # Get device name from generic access SVC
    devname = "Unknown device"
    generic_acc = radoneye.get_service(0x1800)
    if generic_acc:
        devname_chr = generic_acc[0].get_characteristic(0x2A00)
        if devname_chr:
            devname = devname_chr[0].read()
            if devname:
                devname = devname.decode()
                print("Found RadonEye device:", devname)

    # Find Komoot SVC & CHR, register notify
    radoneye_svc = radoneye.get_service(SVC_UUID)
    assert radoneye_svc:

    print("Found RadonEye SVC, locating CHR...")
    radoneye_write_chr = radoneye_svc[0].get_characteristic(RDW_UUID)
    assert radoneye_write_chr

    print("Found Komoot CHR, triggering update...")
    radoneye_write_chr[0].write(b"\x50")

    print("Locating Radon readout CHR...")
    radoneye_read_chr = radoneye_svc[0].get_characteristic(RDR_UUID)
    assert radoneye_read_chr

    radon_value = radoneye_read_chr[0].read()
    assert radon_value
    radon_value = unpack('<f', radon_value[2:6])[0] * 37 # Unpack, convert to Bq
    print("Decoded radon value:", radon_value, "Bq")

    url = config["homematic_addr"].format(radon=radon_value, ise_id=config["homematic_ise_id"])
    print("Sending HTTP request:", url)
    resp = urequests.get(url)
    assert resp
    resp.close()
    print("Done.")

config = ujson.load(open(config_file, 'r'))

if config["reset_timer"] > 0:
    timer_reader = WDT(timeout=config["reset_timer"] * 1000)

sbt = SyncBLE()
