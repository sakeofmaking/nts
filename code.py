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
import rotaryio

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
button_enc = digitalio.DigitalInOut(board.GP21)
button_enc.switch_to_input(pull=digitalio.Pull.UP)
button_enc_state = None
encoder = rotaryio.IncrementalEncoder(board.GP19, board.GP18)
last_position = None  # encoder last position
led = digitalio.DigitalInOut(board.GP10)
led.direction = digitalio.Direction.OUTPUT
pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())
upper_temp_thresh = upper_temp_thresh_new = 30  # C
lower_temp_thresh = lower_temp_thresh_new = 10  # C
upper_lower = True  # upper
delay_count = 0
delay_overflow = 600  # 10 min

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
        scan_count += 1  # increment scan count

        # Pull temp and hum and create labels
        temperature, relative_humidity = sht.measurements
        upper_temp_display = f'Upper Alert: {upper_temp_thresh_new:0.1f} C'
        temp_display = f'Temp: {temperature:0.1f} C'
        lower_temp_display = f'Lower Alert: {lower_temp_thresh_new:0.1f} C'
        # hum_display = f'Hum: {relative_humidity:0.1f} %'

        # Update Display
        upper_temp_label = label.Label(font, text=upper_temp_display)
        temp_label = label.Label(font, text=temp_display)
        lower_temp_label = label.Label(font, text=lower_temp_display)
        # hum_label = label.Label(font, text=hum_display)

        # Set location on display
        (_, _, width, _) = upper_temp_label.bounding_box
        upper_temp_label.x = 0
        upper_temp_label.y = 5
        (_, _, width, _) = temp_label.bounding_box
        temp_label.x = 0
        temp_label.y = 15
        (_, _, width, _) = lower_temp_label.bounding_box
        lower_temp_label.x = 0
        lower_temp_label.y = 25
        # (_, _, width, _) = hum_label.bounding_box
        # hum_label.x = 0
        # hum_label.y = 35

        # Update the display
        watch_group = displayio.Group()
        watch_group.append(upper_temp_label)
        watch_group.append(temp_label)
        watch_group.append(lower_temp_label)
        # watch_group.append(hum_label)
        display.root_group = watch_group

        # Send data
        if scan_count % 100 == 0:  # every second
            if (temperature < lower_temp_thresh_new) or (temperature > upper_temp_thresh_new):  # threshold passed
                if delay_count == 0:
                    send_data = {'Temperature (C)': str(f'{temperature}'),}
                    r = requests.post(os.getenv('WEBHOOK_ENDPOINT_URL'), data=json.dumps(send_data), headers={'Content-Type': 'application/json'})
                    print('Message sent')
                delay_count += 1
                if delay_count >= delay_overflow:  # reset delay_count
                    delay_count = 0

        # Update encoder position
        position = encoder.position
        if last_position is None or position != last_position:
            # Update temp threshold
            if upper_lower:
                upper_temp_thresh_new = upper_temp_thresh + position
            else:
                lower_temp_thresh_new = lower_temp_thresh + position
        last_position = position

        # Toggle Upper Lower Threshold Selection
        if not button_enc.value and button_enc_state is None:
            button_enc_state = "pressed"
        if button_enc.value and button_enc_state == "pressed":
            print('Button pressed')
            upper_lower = not(upper_lower)
            button_enc_state = None

        if scan_count >= scan_overflow:  # reset scan_count
            scan_count = 0

        time.sleep(0.01)
    except Exception as e:
        print("Error:\n", str(e))
        print("Resetting microcontroller in 60 seconds")
        time.sleep(60)
        microcontroller.reset()



