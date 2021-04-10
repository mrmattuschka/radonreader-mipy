from ubluetooth import BLE, UUID
from micropython import const
from struct import unpack
from machine import Timer, reset
from time import time, sleep_ms
import urequests
import ubinascii
import ujson
import network


__version__ = "0.2.0"

_IRQ_SCAN_RESULT                     = const(1 << 4)
_IRQ_SCAN_COMPLETE                   = const(1 << 5)
_IRQ_PERIPHERAL_CONNECT              = const(1 << 6)
_IRQ_PERIPHERAL_DISCONNECT           = const(1 << 7)
_IRQ_GATTC_SERVICE_RESULT            = const(1 << 8)
_IRQ_GATTC_CHARACTERISTIC_RESULT     = const(1 << 9)
_IRQ_GATTC_DESCRIPTOR_RESULT         = const(1 << 10)
_IRQ_GATTC_READ_RESULT               = const(1 << 11)
_IRQ_GATTC_WRITE_STATUS              = const(1 << 12)

uuid_svc    = UUID("00001523-1212-efde-1523-785feabcd123")
uuid_write  = UUID("00001524-1212-efde-1523-785feabcd123")
uuid_read   = UUID("00001525-1212-efde-1523-785feabcd123")

config_file = "config.json"

global read_handle, write_handle
global scan_data
scan_data = []
write_handle = None
read_handle = None

def reset_wrap(*_):
    reset()

def wifi_connect(ssid, pw):
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

def addr_decode(addr):
    return ":".join([ubinascii.hexlify(addr[i:i+1]).decode("utf8") for i in range(len(addr))])

def addr_encode(addr):
    # Convert address in AA:BB:CC:DD:EE:FF format to hex bytes
    return ubinascii.unhexlify(addr.replace(":", ""))

def adv_decode(adv_type, data):
    # This function dissects adv_data into AD elements
    # consisting of a byte for length, followed by a byte for data type (0x09 is local complete name)
    # followed by the data
    i = 0
    while i + 1 < len(data):
        if data[i + 1] == adv_type:
            return data[i + 2:i + data[i] + 1]
        i += 1 + data[i]
    return None

def adv_decode_name(data):
    n = adv_decode(0x09, data)
    if n:
        return n.decode('utf-8')
    return data

def bt_irq(event, data): # Register event handler
    global scan_data
    global read_handle, write_handle

    if event == _IRQ_SCAN_RESULT:
        # Scan functionality is not used by this script but is included for debugging
        addr_type, addr, connectable, rssi, adv_data = data
        if not addr in scan_data: # Only mention new devices
            print(
                "\n--- BT DEVICE ---",
                "\nBT address:", addr_decode(addr),
                "\nAddress type:", addr_type,
                "\nRSSI:", rssi,
                "\nDevice name:", adv_decode_name(adv_data))
            scan_data.append(addr)

    elif event == _IRQ_SCAN_COMPLETE:
        # Scan duration finished or manually stopped.
        scan_data = []
        print('GAP Scan complete.')

    elif event == _IRQ_PERIPHERAL_CONNECT:
        print("\n--- BT CONNECTED ---")
        conn_handle, addr_type, addr = data
        print("conn_handle:", conn_handle, "\naddr:", addr_decode(addr))
        
        # Set up timer to disconnect after 10s
        timer_dc = Timer(0)
        timer_dc.init(
            mode=Timer.ONE_SHOT,
            period=10000,
            callback=lambda t: bt.gap_disconnect(conn_handle)
        )
        
        bt.gattc_discover_services(conn_handle)

    elif event == _IRQ_PERIPHERAL_DISCONNECT:
        conn_handle, addr_type, addr = data
        
        if conn_handle == 65535:
            print("\nERROR: BT connection failed!")
        else:
            print("\n--- BT DISCONNECTED ---")

    elif event == _IRQ_GATTC_SERVICE_RESULT:
        conn_handle, start_handle, end_handle, uuid = data
        
        print(
            "\n--- SERVICE ---",
            "\nconn_handle:", conn_handle,
            "\nstart_handle:", start_handle,
            "\nend_handle:", end_handle,
            "\nuuid:", uuid
        )

        if uuid == uuid_svc:
            print("\nFound radon service, fetching characteristics...")
            sleep_ms(500)
            bt.gattc_discover_characteristics(conn_handle, start_handle, end_handle)

    elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
        conn_handle, def_handle, value_handle, properties, uuid = data
        
        print(
            "\n--- CHARACTERISIC ---",
            "\nconn_handle:", conn_handle,
            "\ndef_handle:", def_handle,
            "\nvalue_handle:", value_handle,
            "\nuuid:", uuid
        )

        if uuid == uuid_read:
            read_handle = value_handle
            print("\nFound radon read-out characteristic.")

        if uuid == uuid_write:
            write_handle = value_handle
            print("\nFound radon update trigger characteristic.")

        if (value_handle in [read_handle, write_handle]) and read_handle and write_handle:
            print(
                "\nWriting \\x50 to value handle",
                write_handle,
                "on conn",
                conn_handle
            )
            sleep_ms(500)
            bt.gattc_write(conn_handle, write_handle, b"P", 1)

    elif event == _IRQ_GATTC_WRITE_STATUS:
        # A gattc_write() has completed.
        conn_handle, value_handle, status = data
        print("Write status:", status)
        if status == 0:
            bt.gattc_read(conn_handle, read_handle)
            
            # Reset handles
            write_handle = None
            read_handle = None
        else:
            print("ERROR: Write request failed!")

    elif event == _IRQ_GATTC_READ_RESULT:
        # A gattc_read() has completed.
        conn_handle, value_handle, char_data = data
        print("\nRead value", value_handle, "\nData:", char_data)
        radon_value = unpack('<f', char_data[2:6])[0] * 37 # Unpack, convert to Bq
        print("Decoded radon value:", radon_value, "Bq")
        bt.gap_disconnect(conn_handle)
        
        print("Sending HTTP request:", config["homematic_addr"].format(radon=radon_value, ise_id=config["homematic_ise_id"]))
        resp = urequests.get(config["homematic_addr"].format(radon=radon_value, ise_id=config["homematic_ise_id"]))
        if resp:
            resp.close()
            print("Done.")
        else:
            print("ERROR: Could not reach HomeMatic!")


def connect_and_read_radon(*_):
    print("\n--- STARTING RADON READOUT ROUTINE ---")
    if wifi_connect(config["ssid"], config["pass"]):
        bt.gap_connect(
            config["radoneye_addr_type"],
            addr_encode(config["radoneye_addr"]),
            2000
        )


config = ujson.load(open(config_file, 'r'))

if config["reset_timer"] > 0:
    timer_reader = Timer(2)
    timer_reader.init(
        mode=Timer.PERIODIC,
        period=config["reset_timer"]*1000*3600,
        callback=reset
    )

bt = BLE()

bt.irq(bt_irq)
bt.active(True)

wifi_connect(config["ssid"], config["pass"])

timer_reader = Timer(1)
timer_reader.init(
    mode=Timer.PERIODIC,
    period=config["readout_interval"]*1000,
    callback=connect_and_read_radon
)

