import time

import pyotp


def new_secret():
    return pyotp.random_base32()


def code(secret, at=None, step=30, digits=6):
    totp = pyotp.TOTP(secret, interval=step, digits=digits)
    when = time.time() if at is None else at
    return totp.at(int(when))


def verify(secret, value, window=1, at=None):
    value = str(value).strip()
    if len(value) != 6 or not value.isdigit():
        return False
    totp = pyotp.TOTP(secret)
    when = time.time() if at is None else at
    return bool(totp.verify(value, for_time=when, valid_window=window))


def matching_step(secret, value, at=None):
    """Return the accepted step so callers can atomically reject replay."""
    when = time.time() if at is None else at
    step = int(when) // 30
    for candidate in (step, step - 1, step + 1):
        if verify(secret, value, window=0, at=candidate * 30):
            return candidate
    return None
