# @sniptest filename=timezone.py
from datetime import datetime

import pytz


def run():
    # Get current time in specific timezone
    tz = pytz.timezone("America/New_York")
    current_time = datetime.now(tz)

    # Your automation
    pass
