"""
Temp Sensor

Description:
* On power up, OLED displays temperature actual
* Rotary encoder is used to set thresholds
* Rotary encoder button toggles between upper and lower threshold selection
* Push button toggles between reporting modes
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
button_enc_prev = True
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
        return True
    except Exception as e:
        print(f'Failed to connect to Wifi: {e}')
        print('Waiting 5 seconds before trying again...')
        time.sleep(10)
        return False


# Pings Google
def ping_google_test():
    '''Send ping to Google's DNS server

    No return value, but throws exception if ping failed'''
    ipv4 = ipaddress.ip_address('8.8.4.4')
    print("Ping google.com: %f ms" % (wifi.radio.ping(ipv4)*1000))

### Consider replacing NVM with a JSON file so you can load a dictionary rather than a byte array
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


# Celcius to Farenheit
def ctof(temperature):
    temperature = ((9/5) * temperature) + 32 + temp_offset  # convert C to F
    return round(temperature, 1)

# Setup
while not wifi_flag:  # connect to wifi
    wifi_flag = connect_to_wifi()
last_time = time.monotonic()  # get the start time
last_time2 = time.monotonic()  # get the start time
upper_temp_thresh, lower_temp_thresh = read_data_from_nvm()

# Configure Temperature Sensor
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

# Place the labels
upper_temp_label = label.Label(font, text='80.0', x=0, y=5)
temp_label = label.Label(font, text='70.0', x=0, y=15)
lower_temp_label = label.Label(font, text='60.0', x=0, y=25)
# hum_label = label.Label(font, text='50.0%', x=0, y=35)
watch_group = displayio.Group()
watch_group.append(upper_temp_label)
watch_group.append(temp_label)
watch_group.append(lower_temp_label)
# watch_group.append(hum_label)

# While Loop
while True:
    try:
        current_time = time.monotonic()  # get the current time

        # Pull temp and hum and create labels
        temperature, relative_humidity = sht.measurements
        temperature = ctof(temperature)
        upper_temp_label.text = f'Upper Alert: {upper_temp_thresh:0.1f} F'
        temp_label.text = f'Temp: {temperature:0.1f} F'
        lower_temp_label.text = f'Lower Alert: {lower_temp_thresh:0.1f} F'
        # hum_label.text = f'Hum: {relative_humidity:0.1f} %'
        display.root_group = watch_group

        # Send data
        if (temperature < lower_temp_thresh) or (temperature > upper_temp_thresh) or not button.value:  # threshold passed or button
            led.value = True
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
                    print(f'Message sent, got {r}')
                    ### FIXME: Did it really post? What are the valid and invalid server responses?
                last_time = current_time  # reset the timer
                webhook_interval = 600  # 10 min
                alert_priority = False  ### Why is this changed? We only send updates with critical alert priority
        else:
            webhook_interval = 0
            alert_priority = True
            led.value = False

        # Update encoder position
        position = encoder.position
        if last_position is None:
            last_position = position
        elif position > last_position:
            if upper_lower:
                upper_temp_thresh += 1
            else:
                lower_temp_thresh += 1
        elif position < last_position:
            if upper_lower:
                upper_temp_thresh -= 1
            else:
                lower_temp_thresh -= 1
        last_position = position

        # Toggle Upper Or Lower Threshold Selection
        if button_enc.value and not button_enc_prev:
            print('Button pressed') ###Actually button released, but less bounce this way?
            upper_lower = not(upper_lower)
        button_enc_prev = button_enc.value
        
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



