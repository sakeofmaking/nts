"""
Temp Sensor

Description:
* On power up, LED confirms connected to network
* On power up, OLED displays temperature actual
* Rotary encoder is used to set thresholds
* Rotary encoder button toggles between upper and lower threshold selection
* Button depressed enables temp monitoring
* Temp is periodically (10 min) reported to Home Assistant
"""


import os
import ipaddress
import wifi
import socketpool
import ssl
import time
import board
import digitalio
import microcontroller
import adafruit_requests
import json
import adafruit_sht4x

# Imports for display
import displayio
from displayio import I2CDisplay as I2CDisplayBus
import terminalio
from adafruit_display_text import label
import adafruit_displayio_sh1107


# Initialize Variables
wifi_flag = False
scan_count = 0
scan_overflow = 8640000
delay_count = 0
delay_overflow = 60  # seconds
button = digitalio.DigitalInOut(board.GP9)
button.switch_to_input(pull=digitalio.Pull.UP)
# button_enc = digitalio.DigitalInOut(board.GP9)
# button_enc.switch_to_input(pull=digitalio.Pull.UP)
led = digitalio.DigitalInOut(board.GP10)
led.direction = digitalio.Direction.OUTPUT
pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())
send_data = {
    'Temperature': str("Temperature goes here"),
}

# SH1107 is vertically oriented 64x128
WIDTH = 128
HEIGHT = 64
BORDER = 2


# Connect to Wifi
def connect_to_wifi():
    print('Connecting to WiFi')
    try:
        wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))
        print('Connected to WiFi')
        led.value = True
        return True
    except Exception as e:
        led.value = False
        print(f'Failed to connect to Wifi: {e}')
        print('Waiting 5 seconds before trying again...')
        time.sleep(10)
        return False


# Pings Google
def ping_google_test():
    ipv4 = ipaddress.ip_address('8.8.4.4')
    print("Ping google.com: %f ms" % (wifi.radio.ping(ipv4)*1000))


# Setup
while not wifi_flag:  # connect to wifi
    wifi_flag = connect_to_wifi()

# Configure SHT4x
i2c = board.STEMMA_I2C()
sht = adafruit_sht4x.SHT4x(i2c)
print("Found SHT4x with serial number", hex(sht.serial_number))
sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
print("Current mode is: ", adafruit_sht4x.Mode.string[sht.mode])

# Configure Display
font = terminalio.FONT
displayio.release_displays()
i2c = board.STEMMA_I2C()
display_bus = I2CDisplayBus(i2c, device_address=0x3C)
display = adafruit_displayio_sh1107.SH1107(display_bus, width=WIDTH, height=HEIGHT, rotation=0)


# While Loop
while True:
    try:
        # Pull temp and hum and create labels
        temperature, relative_humidity = sht.measurements
        temp_display = f'Temp: {temperature:0.1f} C'
        hum_display = f'Hum: {relative_humidity:0.1f} %'
        temp_label = label.Label(font, text=temp_display)
        hum_label = label.Label(font, text=hum_display)

        # Set location on display
        (_, _, width, _) = temp_label.bounding_box
        temp_label.x = 0
        temp_label.y = 5
        (_, _, width, _) = hum_label.bounding_box
        hum_label.x = 0
        hum_label.y = 15

        watch_group = displayio.Group()
        watch_group.append(temp_label)
        watch_group.append(hum_label)
        display.root_group = watch_group

        time.sleep(1)
    except Exception as e:
        print("Error:\n", str(e))
        print("Resetting microcontroller in 60 seconds")
        time.sleep(60)
        microcontroller.reset()



