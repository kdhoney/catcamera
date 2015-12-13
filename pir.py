import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
PIR_PIN = 17
GPIO.setup(PIR_PIN, GPIO.IN)

def MOTION(PIR_PIN):
	print "MotionDetected"


print "PIR Start (CTRL+C to exit)"
time.sleep(2)
print "ready"

try:
	GPIO.add_event_detect(PIR_PIN, GPIO.RISING, callback=MOTION)
	while True:
		time.sleep(0.05)
except KeyboardInterrupt:
	print "Quit"
	GPIO.cleanup()
