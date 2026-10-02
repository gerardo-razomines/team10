"""
test_i2c_send.py
EENG350 Mini Project - debug tool

Purpose:
    Sends a goal to the Arduino by typing it in, no camera needed.
    Lets the controls team test the wheels without the vision code running,
    and lets us check the I2C link on its own.

Hardware:
    Arduino on the Pi's I2C bus (SDA -> SDA, SCL -> SCL, GND -> GND) at ARD_ADDR

How to run:
    python3 test_i2c_send.py
    Then type two numbers like:  0 1      (q to quit)
"""

from smbus2 import SMBus

ARD_ADDR = 8
arduino = SMBus(1)

while True:
    text = input("Goal (left right), q to quit: ")
    if text == "q":
        break
    try:
        left, right = [int(n) for n in text.split()]
        arduino.write_i2c_block_data(ARD_ADDR, 0, [left, right])
        print("Sent", [left, right])
    except ValueError:
        print("Type two numbers like: 0 1")
    except OSError:
        print("Arduino not responding (check wires and address)")
