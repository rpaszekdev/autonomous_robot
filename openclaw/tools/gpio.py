"""GPIO tool — Controls pins for LEDs, servos, relays, and wheel motors.

Uses gpiozero for safe pin management. Supports:
  - Direct pin on/off with optional auto-reset
  - Wheel motor control (forward/backward/turn via H-bridge)
"""

import logging
import threading

logger = logging.getLogger(__name__)

# ── Motor pin configuration (L298N H-bridge) ────────────────
# Adjust these to match your wiring
MOTOR_LEFT_FWD = 17    # BCM pin for left motor forward
MOTOR_LEFT_BWD = 27    # BCM pin for left motor backward
MOTOR_RIGHT_FWD = 22   # BCM pin for right motor forward
MOTOR_RIGHT_BWD = 23   # BCM pin for right motor backward
MOTOR_LEFT_EN = 12     # PWM enable for left motor
MOTOR_RIGHT_EN = 13    # PWM enable for right motor

_motors_initialised = False
_left_motor = None
_right_motor = None


def _init_motors():
    """Lazy-init motor controller using gpiozero."""
    global _motors_initialised, _left_motor, _right_motor
    if _motors_initialised:
        return

    try:
        from gpiozero import Robot
        _left_motor = (MOTOR_LEFT_FWD, MOTOR_LEFT_BWD)
        _right_motor = (MOTOR_RIGHT_FWD, MOTOR_RIGHT_BWD)
        _motors_initialised = True
        logger.info("Motors initialised: L(%d,%d) R(%d,%d)",
                     MOTOR_LEFT_FWD, MOTOR_LEFT_BWD,
                     MOTOR_RIGHT_FWD, MOTOR_RIGHT_BWD)
    except Exception as e:
        logger.error("Motor init failed: %s", e)


def tool_gpio_signal(pin: int, state: bool, duration_ms: int = None, **kwargs) -> dict:
    """Set a GPIO pin HIGH or LOW, optionally auto-resetting after duration_ms."""
    try:
        from gpiozero import LED
        device = LED(pin)
        if state:
            device.on()
        else:
            device.off()

        if duration_ms and state:
            def _reset():
                device.off()
                device.close()
            timer = threading.Timer(duration_ms / 1000.0, _reset)
            timer.daemon = True
            timer.start()

        logger.info("GPIO pin %d → %s%s", pin, "HIGH" if state else "LOW",
                     f" (reset in {duration_ms}ms)" if duration_ms else "")
        return {"status": "ok", "pin": pin, "state": state}

    except Exception as e:
        logger.error("GPIO error: %s", e)
        return {"error": str(e)}


def tool_move(direction: str, speed: float = 0.5, duration_ms: int = 1000, **kwargs) -> dict:
    """Move the robot using wheel motors.

    Args:
        direction: 'forward', 'backward', 'left', 'right', 'stop'
        speed: 0.0 to 1.0
        duration_ms: how long to move
    """
    _init_motors()

    try:
        from gpiozero import Robot
        robot = Robot(left=_left_motor, right=_right_motor)

        speed = max(0.0, min(1.0, speed))

        if direction == "forward":
            robot.forward(speed=speed)
        elif direction == "backward":
            robot.backward(speed=speed)
        elif direction == "left":
            robot.left(speed=speed)
        elif direction == "right":
            robot.right(speed=speed)
        elif direction == "stop":
            robot.stop()
            return {"status": "ok", "direction": "stop"}
        else:
            return {"error": f"Unknown direction: {direction}"}

        # Auto-stop after duration
        def _stop():
            robot.stop()
            logger.info("Movement stopped after %dms", duration_ms)

        timer = threading.Timer(duration_ms / 1000.0, _stop)
        timer.daemon = True
        timer.start()

        logger.info("Moving %s at %.1f speed for %dms", direction, speed, duration_ms)
        return {"status": "ok", "direction": direction, "speed": speed, "duration_ms": duration_ms}

    except Exception as e:
        logger.error("Move error: %s", e)
        return {"error": str(e)}
