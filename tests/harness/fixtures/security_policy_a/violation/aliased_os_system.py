# v1.3.0 S5 — `from os import system; system(...)` resolves via
# ImportTracker to the canonical `os.system`. Pre-v1.3.0 missed.
from os import system


def run(cmd):
    system(cmd)
