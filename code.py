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


# While Loop
while True:
    try:
        temperature, relative_humidity = sht.measurements
        print("Temperature: %0.1f C" % temperature)
        print("Humidity: %0.1f %%" % relative_humidity)
        print("")
        time.sleep(1)

        # time.sleep(0.01)
    except Exception as e:
        print("Error:\n", str(e))
        print("Resetting microcontroller in 60 seconds")
        time.sleep(60)
        microcontroller.reset()



