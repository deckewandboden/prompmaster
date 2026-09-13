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
