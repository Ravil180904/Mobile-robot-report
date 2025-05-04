from gpiozero import OutputDevice
from time import sleep

relay = OutputDevice(18, active_high=True, initial_value=False)

def fire():
    for _ in range(4):  # 4 shots in 20 seconds total (every 5 seconds)
        relay.on()
        sleep(1)        # Shooting pulse duration
        relay.off()
        sleep(4)        # Wait until next shot

fire()



