# v1.3.0 — `from time import sleep; sleep(1)` inside async def must fire.
from time import sleep


async def hang():
    sleep(1)
