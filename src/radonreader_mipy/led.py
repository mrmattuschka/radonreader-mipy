from time import sleep_ms

import neopixel
from machine import Pin

__version__ = "1.0.0"

# Onboard WS2812 RGB LED of the Waveshare ESP32-C6 Zero lives on GPIO8.
LED_PIN = 8
LED_COUNT = 1

# Some named colors as (g, r, b) tuples to match the NeoPixel GRB wire order.
OFF = (0, 0, 0)
RED = (0, 255, 0)
GREEN = (255, 0, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
CYAN = (255, 0, 255)
MAGENTA = (0, 255, 255)
WHITE = (255, 255, 255)


class LED:
    def __init__(self, pin: int = LED_PIN, count: int = LED_COUNT, brightness: float = 1.0):
        self._np = neopixel.NeoPixel(Pin(pin, Pin.OUT), count)
        self._count = count
        self.brightness = brightness
        self.set(OFF)

    def set(self, color: tuple, brightness=None) -> None:
        """Set the LED to an (r, g, b) color, scaled by brightness."""
        if brightness is None:
            brightness = self.brightness
        color = tuple(int(c * brightness) for c in color)
        self._np[0] = color
        self._np.write()

    def on(self, color: tuple = WHITE) -> None:
        self.set(color)

    def off(self) -> None:
        self.set(OFF)

    def blink(self, color: tuple, period_ms: int = 500, times: int = 1) -> None:
        """Blink the LED *times* times with the given on/off period."""
        half = period_ms // 2
        for _ in range(times):
            self.set(color)
            sleep_ms(half)
            self.off()
            sleep_ms(half)

    def breathe(self, color: tuple, period_ms: int = 1000, times: int = 1, steps: int = 20) -> None:
        """Breath the LED *times* times, smoothly ramping brightness up and down.

        A full up-and-down ramp takes *period_ms*, split into *steps* per direction.
        """
        step_ms = period_ms // (2 * steps)
        for _ in range(times):
            for i in range(steps):
                ratio = i / (steps - 1)
                self.set(color, self.brightness * ratio)
                sleep_ms(step_ms)
            for i in range(steps - 1, -1, -1):
                ratio = i / (steps - 1)
                self.set(color, self.brightness * ratio)
                sleep_ms(step_ms)
        self.off()

    def __getitem__(self, index: int) -> tuple:
        """Return the raw color of the LED at *index* (before brightness scaling)."""
        return self._np[index]

    def __setitem__(self, index: int, value: tuple) -> None:
        self._np[index] = value
        self._np.write()
