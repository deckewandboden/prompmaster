from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
class CryptoError(RuntimeError): pass
def _fernet():
    if not settings.APP_ENCRYPTION_KEY: raise CryptoError('APP_ENCRYPTION_KEY is not configured')
    return Fernet(settings.APP_ENCRYPTION_KEY.encode())
def encrypt(value:str)->str: return _fernet().encrypt(value.encode()).decode()
def decrypt(value:str)->str:
    try: return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc: raise CryptoError('Encrypted value cannot be decrypted') from exc
