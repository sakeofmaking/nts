"""
Temp Sensor

Description:
* On power up, LED confirms connected to network
* On power up, OLED displays temperature actual
* Rotary encoder is used to set thresholds
* Rotary encoder button toggles between upper and lower threshold selection
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
import struct
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
upper_lower = True  # upper
upper_temp_thresh = 90  # F
lower_temp_thresh = 30  # F
webhook_interval = 0
FIVE_MIN_INTERVAL = 300
alert_priority = True  # True triggers mobile notification
temp_offset = -6.4  # To account for device heat

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


# Read Data From NVM
def read_data_from_nvm():
    stored_data = microcontroller.nvm[0:8]
    upper_thresh, lower_thresh = struct.unpack('ff', stored_data)
    return upper_thresh, lower_thresh


# Write 
def write_data_to_nvm(upper_data, lower_data):
    write_data = struct.pack('ff', upper_data, lower_data)
    microcontroller.nvm[0:8] = write_data
    print(f'Wrote {upper_data} and {lower_data} to NVM')


# Setup
while not wifi_flag:  # connect to wifi
    wifi_flag = connect_to_wifi()
last_time = time.monotonic()  # get the start time
last_time2 = time.monotonic()  # get the start time
upper_temp_thresh_read, lower_temp_thresh_read = read_data_from_nvm()
upper_temp_thresh = upper_temp_thresh_read
lower_temp_thresh = lower_temp_thresh_read

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
        current_time = time.monotonic()  # get the current time

        # Pull temp and hum and create labels
        temperature, relative_humidity = sht.measurements
        temperature = ((9/5) * temperature) + 32 + temp_offset  # convert C to F
        temperature = round(temperature, 1)
        upper_temp_display = f'Upper Alert: {upper_temp_thresh:0.1f} F'
        temp_display = f'Temp: {temperature:0.1f} F'
        lower_temp_display = f'Lower Alert: {lower_temp_thresh:0.1f} F'
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
        if (temperature < lower_temp_thresh) or (temperature > upper_temp_thresh):  # threshold passed
            if current_time - last_time >= webhook_interval:  # check if interval has passed
                try:  # try pinging google
                    ping_google_test()
                except Exception as e:
                    print('Ping test failed')
                    wifi_flag = False
                    while not wifi_flag:
                        wifi_flag = connect_to_wifi()

                if wifi_flag:
                    send_data = {
                        'temperature_f': temperature,
                        'critical_alert': alert_priority,
                        }
                    r = requests.post(os.getenv('WEBHOOK_ENDPOINT_URL'), data=json.dumps(send_data), headers={'Content-Type': 'application/json'})
                    print('Message sent')
                last_time = current_time  # reset the timer
                webhook_interval = 600  # 10 min
                alert_priority = False
        else:
            webhook_interval = 0
            alert_priority = True

        # Update encoder position
        position = encoder.position
        if last_position is None:
            last_position = position
        if position != last_position:
            # Update temp threshold
            if upper_lower and (position > last_position):
                upper_temp_thresh += 1
            elif upper_lower and (position < last_position):
                upper_temp_thresh -= 1
            elif not upper_lower and (position > last_position):
                lower_temp_thresh += 1
            elif not upper_lower and (position < last_position):
                lower_temp_thresh -= 1
        last_position = position

        # Toggle Upper Lower Threshold Selection
        if not button_enc.value and button_enc_state is None:
            button_enc_state = "pressed"
        if button_enc.value and button_enc_state == "pressed":
            print('Button pressed')
            upper_lower = not(upper_lower)
            button_enc_state = None
        
        # Update Threshold Data In NVM
        if current_time - last_time2 >= FIVE_MIN_INTERVAL:  # check if interval has passed
            upper_temp_thresh_read, lower_temp_thresh_read = read_data_from_nvm()
            if (upper_temp_thresh != upper_temp_thresh_read) or (lower_temp_thresh != lower_temp_thresh_read):
                write_data_to_nvm(upper_temp_thresh, lower_temp_thresh)
            last_time2 = current_time  # reset the timer

        time.sleep(0.05)  # 50ms delay  
    except Exception as e:
        print("Error:\n", str(e))
        print("Resetting microcontroller in 60 seconds")
        time.sleep(60)
        microcontroller.reset()



