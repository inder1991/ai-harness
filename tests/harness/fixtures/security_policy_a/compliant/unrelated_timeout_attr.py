# v1.3.0 S7 — `request.timeout = None` is a different attribute
# (pre-v1.3.0 false-positive on this regex pattern).
class Request:
    def __init__(self):
        self.timeout = None
