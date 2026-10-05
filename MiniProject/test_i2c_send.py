from smbus2 import SMBus

ARD_ADDR = 8
arduino = SMBus(1)

while True:
    text = input("Goal left right, q to quit: ")
    if text == "q":
        break
    try:
        left, right = [int(n) for n in text.split()]
        arduino.write_byte(ARD_ADDR, left * 2 + right)
        print("Sent", [left, right], "as byte", left * 2 + right)
    except ValueError:
        print("Type two numbers like: 0 1")
    except OSError:
        print("Arduino not responding")
