<<<<<<< HEAD
=======
"""
pi_main.py
EENG350 Mini Project - full Raspberry Pi program

Purpose:
    Runs the whole Pi side of the mini project:
      1. Camera finds the marker and its quadrant (uses marker_quadrant.py)
      2. Shows the live camera image with the marker position
      3. Sends the new goal [left, right] to the Arduino over I2C
      4. Shows "Goal Position: L R" on the LCD
    Steps 3 and 4 run in a background thread so the slow LCD never makes
    the camera lag.

Hardware:
    - USB webcam on any USB port of the Pi
    - Adafruit 16x2 RGB LCD plate on the Pi's I2C pins (SDA, SCL)
    - Arduino on the same I2C bus (Pi SDA -> Arduino SDA, SCL -> SCL, GND -> GND)
      at address ARD_ADDR

Message sent to the Arduino (agree on this with the controls team):
    3 bytes: [0, left, right]   (0 is the register/offset byte)

How to run:
    python3 pi_main.py      (press q in the camera window to quit)
"""

>>>>>>> 81df5d9ca4da8a2b988ab43bdf9872eabf88f9cf
import queue
import threading

import cv2
import board
import adafruit_character_lcd.character_lcd_rgb_i2c as character_lcd
from smbus2 import SMBus

from marker_quadrant import get_quadrant, draw, GOALS, MIRROR

<<<<<<< HEAD
ARD_ADDR = 8
q = queue.Queue()


def i2c_worker():
    """thread sends each new goal to the Arduino then updates the LCD"""
=======
ARD_ADDR = 8          # Arduino's I2C address (must match Wire.begin(8) on the Arduino)
q = queue.Queue()     # main loop puts new goals here, the thread takes them out


def i2c_worker():
    """Background thread: sends each new goal to the Arduino, then updates the LCD."""
>>>>>>> 81df5d9ca4da8a2b988ab43bdf9872eabf88f9cf
    lcd = character_lcd.Character_LCD_RGB_I2C(board.I2C(), 16, 2)
    lcd.color = [0, 100, 0]
    arduino = SMBus(1)

    while True:
<<<<<<< HEAD
        goal = q.get()            #waits until a new goal
        while not q.empty():      #skip to the newest one
            goal = q.get()

        try:
            arduino.write_byte(ARD_ADDR, goal[0] * 2 + goal[1])
        except OSError:
            print("Arduino not responding")
=======
        goal = q.get()            # waits here until there is a new goal
        while not q.empty():      # if several piled up, skip to the newest one
            goal = q.get()

        try:
            arduino.write_i2c_block_data(ARD_ADDR, 0, goal)
        except OSError:
            print("Arduino not responding (not connected?)")
>>>>>>> 81df5d9ca4da8a2b988ab43bdf9872eabf88f9cf

        lcd.clear()
        lcd.message = f"Goal Position:\n{goal[0]} {goal[1]}"


def main():
<<<<<<< HEAD
    #daemon=True means the thread stops
=======
    # daemon=True means the thread stops when the main program quits
>>>>>>> 81df5d9ca4da8a2b988ab43bdf9872eabf88f9cf
    threading.Thread(target=i2c_worker, daemon=True).start()

    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

<<<<<<< HEAD
    goal = [0, 0]
    q.put(goal)
=======
    goal = [0, 0]     # both wheels start with 0 facing up
    q.put(goal)       # show the starting goal on the LCD
>>>>>>> 81df5d9ca4da8a2b988ab43bdf9872eabf88f9cf

    while True:
        ret, frame = camera.read()
        if not ret:
<<<<<<< HEAD
            print("Camera not found")
=======
            print("Camera not found. Is it plugged in?")
>>>>>>> 81df5d9ca4da8a2b988ab43bdf9872eabf88f9cf
            break
        if MIRROR:
            frame = cv2.flip(frame, 1)

        quadrant, center = get_quadrant(frame)

<<<<<<< HEAD
        #Only send when the goal changes
=======
        # Only send when the goal changes -> no lag, no spamming the I2C bus
>>>>>>> 81df5d9ca4da8a2b988ab43bdf9872eabf88f9cf
        if quadrant and GOALS[quadrant] != goal:
            goal = GOALS[quadrant]
            print("New goal:", goal)
            q.put(goal)

        draw(frame, quadrant, center, goal)
        cv2.imshow("Mini Project", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
