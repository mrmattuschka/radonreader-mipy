__version__ = "0.1.0"

import struct
from time import sleep_ms, time

import ubinascii
from bluetooth import BLE, UUID
from micropython import const

# IRQ_CENTRAL_CONNECT = const(1)
# IRQ_CENTRAL_DISCONNECT = const(2)
# IRQ_GATTS_WRITE = const(3)
# IRQ_GATTS_READ_REQUEST = const(4)
IRQ_SCAN_RESULT = const(5)
IRQ_SCAN_DONE = const(6)
IRQ_PERIPHERAL_CONNECT = const(7)
IRQ_PERIPHERAL_DISCONNECT = const(8)
IRQ_GATTC_SERVICE_RESULT = const(9)
IRQ_GATTC_SERVICE_DONE = const(10)
IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
IRQ_GATTC_CHARACTERISTIC_DONE = const(12)
IRQ_GATTC_DESCRIPTOR_RESULT = const(13)
IRQ_GATTC_DESCRIPTOR_DONE = const(14)
IRQ_GATTC_READ_RESULT = const(15)
IRQ_GATTC_READ_DONE = const(16)
IRQ_GATTC_WRITE_DONE = const(17)
IRQ_GATTC_NOTIFY = const(18)
# IRQ_GATTC_INDICATE = const(19)
# IRQ_GATTS_INDICATE_DONE = const(20)

def addr_decode(addr):
    """
    Convert a hexadecimal BLE mac address from bytes to string format (AA:BB:CC:DD:EE:FF).
    """
    return ":".join([ubinascii.hexlify(addr[i:i+1]).decode("utf8") for i in range(len(addr))])

def addr_encode(addr):
    """
    Convert a hexadecimal BLE mac address from a string in AA:BB:CC:DD:EE:FF format to bytes.
    """
    return ubinascii.unhexlify(addr.replace(":", ""))

def decode_adv_data(adv_data):
    """
    Decode advertisement data of devices discovered using a GAP scan.
    Check https://docs.silabs.com/bluetooth/latest/general/adv-and-scanning/bluetooth-adv-data-basics for the advertising data format.

    Parameters
    ----------
    adv_data: bytes
        The raw adv_data to be digested.

    Returns
    ----------
    decoded: dict
        A dict of adv_type: adv_value pairs.
    """

    decoded = {}
    while adv_data:
        adv_length = struct.unpack("b", adv_data[0:1])[0]
        adv_type = ubinascii.hexlify(adv_data[1:2]).decode()
        payload = adv_data[2:adv_length+1]
        adv_data = adv_data[adv_length+1:]

        decoded[adv_type] = payload

    return decoded


class TimeoutError(Exception):
    pass


class _Busy():
    """
    This class is used to block code execution after launching GAP/GATTC procedures until it receives a clear from an external event.
    """

    def __init__(self):
        self.busy = False

    def is_busy(self):
        return self.busy

    def set_busy(self):
        """
        Set the internal busy flag to True.
        While busy == True, _Busy.wait will block further execution.
        """
        self.busy = True,

    def set_clear(self):
        """
        Set the internal busy flag to False.
        While busy == False, _Busy.wait will not (or no longer) block further execution.
        """
        self.busy = False

    def wait(self, timeout=30, permissive=False, sleep=10):
        """
        Block until the _Busy instance is cleared using set_clear.

        Parameters
        ----------
        timeout : int, optional
            Maximum duration to wait in seconds before timeout. Default 30.
        permissive: bool, optional
            Whether to allow a timeout without raising a TimeoutError. Default False.
        sleep: int, optional
            Temporal interval to check busyness in in milliseconds. Default 10.

        Returns
        ----------
        Returns 0 on successful wait, 1 if a timeout occured.
        """
        start = time()

        while self.is_busy():
            if time() - start > timeout:
                self.set_clear()
                if not permissive:
                    raise TimeoutError
                return 1
            else:
                sleep_ms(sleep)
        else:
            return 0


class SyncBLE():
    """
    Wrapper for ubluetooth.BLE that turns its asynchrous factory behavior into a synchrous one.
    """

    def __init__(self, timeout=30, notify_callback=None, debug=False, debug_logger=None):
        """
        Wrapper for ubluetooth.BLE that synchronizes its asynchrous behavior

        Parameters
        ----------
        timeout: int, optional
            Duration to wait for BLE operations before calling a timeout in seconds. Default 30.
        notify_callback: object, optional
            Function to call when receiving a notification from a connected device.
            Must accept the following positional arguments: conn_handle, value_handle, notify_data. Default None.
        debug: bool, optional
            Whether or not to print additional debugging information. Default False.
        debug_logger: function, optional.
            Logging function to call for logging. If no logging function is passed, debug output will be printed to console.
        """
        self.busy = _Busy()

        self.ble = BLE()
        self.ble.irq(self.bt_irq)
        self.ble.active(True)

        self._timeout = timeout
        self._scan_devices = {}
        self._last_conn = None
        self._debug = debug

        self.connections = {}
        self.notify_callback = notify_callback

        if debug_logger is None:
            self.log = print
        else:
            if callable(debug_logger):
                self.log = debug_logger
            else:
                raise ValueError("debug_logger is not a callable.")

    def scan(self, duration_ms=10000, *args):
        """
        Perform a GAP scan for devices.

        Parameters
        ----------
        duration_ms: int, optional
            How long to scan in milliseconds. Default 10000
        *args: args
            Positional arguments to be passed on to ubluetooth.BLE.gap_scan

        Returns
        ----------
        scan_devices: dict
            a dict containing the discovered devices.
        """
        self._scan_devices = {}

        self.busy.set_busy()
        self.ble.gap_scan(duration_ms, *args)
        self.busy.wait()
        return self._scan_devices

    def connect(self, addr_type, addr):
        """
        Connect to a BLE peripheral device.

        Parameters
        ----------
        addr_type: int
            The MAC address type.
        addr: str
            The MAC address to connect to as a string in AA:BB:CC:DD:EE:FF format.

        Returns
        ----------
        connected_device: Peripheral
            An instance of sync_ubt.Peripheral representing the established connection.
        """
        self.busy.set_busy()
        self.ble.gap_connect(addr_type, addr_encode(addr))
        self.busy.wait()
        return self._last_conn

    def bt_irq(self, event, data):
        """
        Internal interrupt request handler.
        """
        if self._debug:
            self.log("Event:", event)

        if event == IRQ_SCAN_RESULT:
            addr_type, addr, connectable, rssi, adv_data = data
            addr = bytes(addr)
            adv_data = bytes(adv_data)
            if not addr in self._scan_devices: # Only save new devices
                self._scan_devices[addr] = {
                    "addr_decoded": addr_decode(addr),
                    "addr_type": addr_type,
                    "connectable": connectable,
                    "rssi": rssi,
                    "adv_data": adv_data
                }

        elif event == IRQ_SCAN_DONE:
            self.busy.set_clear()

        elif event == IRQ_PERIPHERAL_CONNECT:
            conn_handle, addr_type, addr = data
            # TODO: behaviour when device with different addr connects at same conn handle?
            if conn_handle not in self.connections:
                _conn = Peripheral(self, conn_handle, addr_type, addr)
                self.connections[conn_handle] = _conn
                self._last_conn = _conn
                self.busy.set_clear()
            else:
                self.connections[conn_handle].__init__(self, conn_handle, addr_type, addr)
                self._last_conn = self.connections[conn_handle]
                self.busy.set_clear()

        elif event == IRQ_PERIPHERAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            if conn_handle == 65535:
                self.log("ERROR: BT connection failed!") # TODO hand this to the calling function
                self._last_conn = None
            else:
                self.connections[conn_handle].connected = False
                self.log("BT device {0} disconnected.".format(conn_handle))
                # del self.connections[conn_handle]
            self.busy.set_clear()

        elif event == IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start_handle, end_handle, uuid = data
            svc = Service(
                self.connections[conn_handle],
                conn_handle,
                start_handle,
                end_handle,
                uuid
            )
            self.connections[conn_handle].services.append(svc)

        elif event == IRQ_GATTC_SERVICE_DONE:
            self.busy.set_clear()

        elif event == IRQ_GATTC_CHARACTERISTIC_RESULT:
            # Called for each characteristic found by gattc_discover_services().
            conn_handle, def_handle, value_handle, properties, uuid = data
            crc = Characteristic(
                self.connections[conn_handle],
                conn_handle,
                def_handle,
                value_handle,
                properties,
                uuid
            )
            self.connections[conn_handle]._cache.append(crc)

        elif event == IRQ_GATTC_CHARACTERISTIC_DONE:
            self.busy.set_clear()

        elif event == IRQ_GATTC_DESCRIPTOR_RESULT:
            # Called for each descriptor found by gattc_discover_descriptors().
            conn_handle, dsc_handle, uuid = data
            dsc = Descriptor(
                self.connections[conn_handle],
                conn_handle,
                dsc_handle,
                uuid
            )
            self.connections[conn_handle]._cache.append(dsc)

        elif event == IRQ_GATTC_DESCRIPTOR_DONE:
            self.busy.set_clear()

        elif event == IRQ_GATTC_WRITE_DONE:
            conn_handle, value_handle, status = data
            self.connections[conn_handle]._cache.append(status)
            self.busy.set_clear()

        elif event == IRQ_GATTC_READ_RESULT:
            conn_handle, value_handle, char_data = data
            self.connections[conn_handle]._cache.append(bytes(char_data))
            self.busy.set_clear()

        elif event == IRQ_GATTC_READ_DONE:
            conn_handle, value_handle, status = data
            self.connections[conn_handle]._cache.append(status)
            self.busy.set_clear()

        elif event == IRQ_GATTC_NOTIFY:
            conn_handle, value_handle, notify_data = data
            if self.notify_callback:
                self.notify_callback.__call__(conn_handle, value_handle, notify_data)



class Peripheral():
    """
    Class for BLE peripheral devices.
    """
    def __init__(self, parent, conn_handle, addr_type, addr):
        """
        Constructor for Peripheral device.
        Don't use this directly, use the connect function of a SyncBLE instance instead.
        """
        self.busy = parent.busy
        self.sble = parent
        self.ble = parent.ble
        self._timeout = parent._timeout
        self._cache = []

        self.connected = True
        self.conn_handle = conn_handle
        self.addr_type = addr_type
        self.addr = addr_decode(addr)

        self.services = []

    def __repr__(self):
        return "Peripheral({})".format(self.addr)

    def connect(self):
        """
        (Re-)connect the device.

        Returns
        ----------
        Returns 0 if connecting was successful (or device was already connected), 1 if connecting failed.
        """
        if not self.connected:
            if self.sble.connect(self.addr_type, self.addr) is None:
                return 1 # return 1 if connection fails
        return 0

    def disconnect(self):
        """
        Disconnect the device.
        """
        self.busy.set_busy()
        self.sble.ble.gap_disconnect(self.conn_handle)
        self.busy.wait()

    def discover_services(self):
        """
        Discover GATT services of the peripheral device.

        Returns
        ----------
        services: list
            A list of sync_ubt.Service objects representing the discovered servies.
        """
        self.services = []
        self.busy.set_busy()
        self.sble.ble.gattc_discover_services(self.conn_handle)
        self.busy.wait()

        return self.services

    def get_service(self, uuid, rediscover=False):
        """
        Retrieve GATT services using a UUID.
        Will call discover_service if no services have been discovered yet,

        Parameters
        ----------
        uuid: {ubluetooth.UUID, str}
            The UUID to fetch the services by (services of the same type can share a UUID).
        rediscover: bool, optional
            Force calling discover_services even if services have already been discovered.

        Returns
        ----------
        fetched_services: list
            A list of sync_ubt.Service objects matching the provided UUID.
        """
        if type(uuid) is not UUID:
            uuid = UUID(uuid)

        if (not self.services) or rediscover:
            self.discover_services()

        fetched_svcs = [svc for svc in self.services if svc.uuid == uuid]
        if len(fetched_svcs):
            return fetched_svcs
        else:
            raise KeyError("No services found for UUID {}".format(uuid))



class Service():
    """
    Class for BLE GATT services.
    """
    def __init__(self, parent, conn_handle, start_handle, end_handle, uuid):
        """
        Constructor for GATT Services.
        Don't use this directly, use the discover_services or get_service functions of a GATT Peripheral instance instead.
        """
        self.busy = parent.busy
        self.ble = parent.ble
        self._timeout = parent._timeout
        self._cache = parent._cache

        self.conn_handle = conn_handle
        self.start_handle = start_handle
        self.end_handle = end_handle
        # Make sure to reinstantiate the UUID in any case, the ones from the callback share the same instance!
        self.uuid = UUID(uuid)

        self.characteristics = []


    def __repr__(self):
       return "Service({})".format(self.uuid)


    def discover_characteristics(self):
        """
        Discover GATT characterisitcs of the service.

        Returns
        ----------
        characteristics: list
            A list of sync_ubt.Characeristics objects representing the discovered characteristics.
        """
        self._cache.clear()

        self.busy.set_busy()
        self.ble.gattc_discover_characteristics(self.conn_handle, self.start_handle, self.end_handle)
        self.busy.wait()

        self.characteristics = self._cache.copy()
        return self.characteristics


    def get_characteristic(self, uuid, rediscover=False):
        """
        Retrieve GATT characteristics of the service using a UUID.
        Will call discover_characteristics if no characteristics have been discovered yet,

        Parameters
        ----------
        uuid: {ubluetooth.UUID, str}
            The UUID to fetch the characteristics by (characteristics of the same type can share a UUID).
        rediscover: bool, optional
            Force calling discover_characteristics even if characteristics have already been discovered.

        Returns
        ----------
        fetched_characteristics: list
            A list of sync_ubt.Characteristics objects matching the provided UUID.
        """

        if type(uuid) is not UUID:
            uuid = UUID(uuid)

        if (not self.characteristics) or rediscover:
            self.discover_characteristics()

        fetched_crcs = [crc for crc in self.characteristics if crc.uuid == uuid]
        if len(fetched_crcs):
            return fetched_crcs
        else:
            raise KeyError("No characteristics found for UUID {}".format(uuid))



class Characteristic():
    """
    Class for BLE GATT characteristics.
    """
    def __init__(self, parent, conn_handle, def_handle, value_handle, properties, uuid):
        """
        Constructor for GATT Characteristics.
        Don't use this directly, use the discover_characteristics or get_characteristics functions of a GATTC Service instance instead.
        """
        self.busy = parent.busy
        self.ble = parent.ble
        self._timeout = parent._timeout
        self._cache = parent._cache

        self.conn_handle = conn_handle
        self.def_handle = def_handle
        self.value_handle = value_handle
        self.properties = properties
        # Make sure to reinstantiate the UUID in any case, the ones from the callback share the same instance!
        self.uuid = UUID(uuid)

        self.descriptors = []

    def __repr__(self):
       return "Characteristic({})".format(self.uuid)

    def discover_descriptors(self):
        """
        Discover GATT descriptors of the characteristics.

        Returns
        ----------
        characteristics: list
            A list of sync_ubt.Descriptor objects representing the discovered descriptors.
        """
        self._cache.clear()
        self.busy.set_busy()
        self.ble.gattc_discover_descriptors(self.conn_handle, self.def_handle, self.value_handle + 1)
        self.busy.wait()

        self.descriptors = self._cache.copy()
        return self.descriptors

    def get_descriptor(self, uuid, rediscover=False):
        """
        Retrieve GATT descriptors of the characteristic using a UUID.
        Will call discover_descriptors if no descriptors have been discovered yet,

        Parameters
        ----------
        uuid: {ubluetooth.UUID, str}
            The UUID to fetch the descriptors by (descriptors of the same type can share a UUID).
        rediscover: bool, optional
            Force calling discover_descriptors even if descriptors have already been discovered.

        Returns
        ----------
        fetched_descriptors: list
            A list of sync_ubt.Descriptor objects matching the provided UUID.
        """

        if type(uuid) is not UUID:
            uuid = UUID(uuid)

        if (not self.descriptors) or rediscover:
            self.discover_descriptors()

        fetched_dscs = [dsc for dsc in self.descriptors if dsc.uuid == uuid]
        if len(fetched_dscs):
            return fetched_dscs
        else:
            raise KeyError("No descriptors found for UUID {}".format(uuid))

    def write(self, data, mode=0):
        """
        Write to the characteristic's value.

        Parameters
        ----------
        data: bytes
            Data to write to the characteristic.
        mode: int, optional
            Writing mode. Has to be 0 or 1. If mode==1, write and request confirmation from the receiving characteristic.
            If mode==0, write without confirmation.

        Returns
        ----------
        status: int
            Write status. Only returned when using write mode 1.
        """

        self._cache.clear()

        if mode == 1:
            self.busy.set_busy()
            self.ble.gattc_write(self.conn_handle, self.value_handle, data, 1)
            self.busy.wait()
            return self._cache[0] # returns write status
        else:
            self.ble.gattc_write(self.conn_handle, self.value_handle, data, 0)

    def read(self, offset=0):
        """
        Read the characteristic's value.

        Returns
        ----------
        char_value: bytes
            The value of the characteristic. Returns None if read-out was unsuccessful.
        """

        self._cache.clear()
        self.busy.set_busy()
        self.ble.gattc_read(self.conn_handle, self.value_handle + offset)
        self.busy.wait()
        if self._cache[-1] == 0:
            return self._cache[-2]
        else:
            return None

    def register_notify(self):
        """
        Register to get notifications from the characteristic by setting the respective descriptor's flag.
        """
        cccd = self.get_descriptor(UUID(0x2902))[0]
        val = cccd.read()
        val = struct.pack("<h", struct.unpack("<h", val)[0] | 1)
        cccd.write(val)

    def unregister_notify(self):
        """
        Unregister notifications from the characteristic.
        """
        cccd = self.get_descriptor(UUID(0x2902))[0]
        val = cccd.read()
        val = struct.pack("<h", (struct.unpack("<h", val)[0] | 1) ^ 1)
        cccd.write(val)


class Descriptor():
    """
    Class for BLE GATT characteristic descriptors.
    """
    def __init__(self, parent, conn_handle, dsc_handle, uuid):
        """
        Constructor for GATT Descriptors.
        Don't use this directly, use the discover_descriptors or get_descriptor functions of a GATTC Characteristic instance instead.
        """
        self.busy = parent.busy
        self.ble = parent.ble
        self._timeout = parent._timeout
        self._cache = parent._cache

        self.conn_handle = conn_handle
        self.dsc_handle = dsc_handle
         # Make sure to reinstantiate the UUID in any case, the ones from the callback share the same instance!
        self.uuid = UUID(uuid)

    def __repr__(self):
       return "Descriptor({})".format(self.uuid)

    def write(self, data, mode=0):
        """
        Write to the descriptor's value.

        Parameters
        ----------
        data: bytes
            Data to write to the descriptor.
        mode: int, optional
            Writing mode. Has to be 0 or 1. If mode==1, write and request confirmation from the receiving descriptor.
            If mode==0, write without confirmation.

        Returns
        ----------
        status: int
            Write status. Only returned when using write mode 1.
        """
        self._cache.clear()

        if mode == 1:
            self.busy.set_busy()
            self.ble.gattc_write(self.conn_handle, self.dsc_handle, data, 1)
            self.busy.wait()
            return self._cache[0] # returns write status
        else:
            self.ble.gattc_write(self.conn_handle, self.dsc_handle, data, 0)

    def read(self):
        """
        Read the descriptor's value.

        Returns
        ----------
        char_value: bytes
            The value of the descriptor. Returns None if read-out was unsuccessful.
        """

        self._cache.clear()

        self.busy.set_busy()
        self.ble.gattc_read(self.conn_handle, self.dsc_handle)
        self.busy.wait()
        if self._cache[-1] == 0:
            return self._cache[-2]
        else:
            return None
