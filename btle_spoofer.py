from ubluetooth import BLE, UUID, FLAG_READ, FLAG_WRITE, FLAG_NOTIFY
from micropython import const
from random import random
import struct
import ubinascii


__version__ = "0.2.0"

local_name = "RadonEye-Spoofer"
adv_data = bytes([len(local_name)+1])+b"\x09"+local_name.encode("utf-8")

_IRQ_CENTRAL_CONNECT                 = const(1 << 0)
_IRQ_CENTRAL_DISCONNECT              = const(1 << 1)
_IRQ_GATTS_WRITE                     = const(1 << 2)

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
    if event == _IRQ_CENTRAL_CONNECT:
        print("Central device connected:", addr_decode(data[2]))
    elif event == _IRQ_CENTRAL_DISCONNECT:
        print("Central device disconnected:", addr_decode(data[2]))
        print("Continuing to advertise.")
        # Need to start advertising again
        bt.gap_advertise(100, adv_data=adv_data, connectable=True)
    elif event == _IRQ_GATTS_WRITE:
        conn_handle, attr_handle = data # Don't know what conn_handle is, but attr_handle is the handle of the char written to

        print("GATTC write has occured: conn.", conn_handle, "on", attr_handle, ", new value:", bt.gatts_read(attr_handle))

        if (attr_handle == rdw) & (bt.gatts_read(rdw) == b"P"): #\x50
            bt.gatts_write(rdw, b"\x00")
            radon_reading = random()
            print("Triggered radon readout. Writing {} to RDR.".format(radon_reading))
            bt.gatts_write(rdr, b"\x00\x00" + struct.pack('<f', radon_reading))

bt = BLE()
bt.active(True)
bt.irq(bt_irq)
#bt.gap_scan(2000, 30000, 30000)

SVC_UUID = UUID("00001523-1212-efde-1523-785feabcd123") # Service UUID
RDW_UUID = UUID("00001524-1212-efde-1523-785feabcd123") # Notify/write characteristic UUID -> this is where the reader writes
RDR_UUID = UUID("00001525-1212-efde-1523-785feabcd123") # Radon readout characteristic UUID

# Assemble characteristics
RDW = (RDW_UUID, FLAG_WRITE,)
RDR = (RDR_UUID, FLAG_READ,)

# Assemble services
SVC = (SVC_UUID, (RDW, RDR),)

# Register services
((rdw, rdr),) = bt.gatts_register_services((SVC,))
# rdw, rdr are value handles to manipulate the characterisics

bt.gap_advertise(
    100,
    adv_data=adv_data,
    connectable=True
)
