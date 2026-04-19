"""get_time tool — Returns system clock datetime."""

from datetime import datetime


def tool_get_time(**kwargs) -> dict:
    """Return the current date and time from the Pi system clock."""
    now = datetime.now()
    return {
        "datetime": now.isoformat(),
        "date": now.strftime("%A, %B %d, %Y"),
        "time": now.strftime("%I:%M %p"),
    }
