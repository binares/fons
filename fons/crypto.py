import hmac
import hashlib
import secrets
from base64 import urlsafe_b64encode as b64e, urlsafe_b64decode as b64d, b64encode
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import random
import string
import time

backend = default_backend()
iterations = 100_000

ALPHA = string.ascii_lowercase
DIGITS =  string.digits
ALNUM = ALPHA + DIGITS
HEX = DIGITS + 'abcdef'
SETS = {'alpha': ALPHA,
        'num': DIGITS,
        'alnum': ALNUM,
        'hex': HEX}

_len = len

def nonce(len=35, set='alnum', uppers=True, lowers=True, custom_set=None):
    set = SETS[set] if custom_set is None else custom_set
    if not lowers: set = set.upper()
    elif uppers: set += ''.join(x.upper() for x in set if x.isalpha())
    len_set = _len(set)
    if not len_set:
        raise IndexError('Got empty set.')
    nonce = ''.join(set[random.randint(0,len_set-1)] for _ in range(len))
    return nonce


def nonce_ms():
    return int(time.time() * 1000)


def sign(key, msg=None, digestmod='sha256', hexdigest=True, base64=False):
    sig = hmac.new(
        key.encode('utf-8'),
        msg=msg.encode('utf-8') if msg is not None else msg,
        digestmod=getattr(hashlib,digestmod) if isinstance(digestmod,str) else digestmod
    )
    sig = sig.hexdigest() if hexdigest else sig.digest()
    if base64:
        sig = b64encode(sig)
        sig = sig.decode()
    return sig


def _derive_key(password, salt, iterations=iterations):
    """
    Derive a secret key from a given password and salt
    :type password: bytes
    :type salt: bytes
    :type iterations: int
    :returns: bytes
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt,
        iterations=iterations, backend=backend)
    return b64e(kdf.derive(password))


def password_encrypt(message, password, iterations=iterations, encoding='utf-8'):
    """
    Encrypt message with a password. Uses PBKDF2 to derive the key
    from password and random salt, then encrypts the message bytes with the key.
    Quite secure (with high enough iterations (>=100) and strong password),
    but if used with a small circuit and very little RAM, may expose to brute forcing.
    Weaknesses: https://en.wikipedia.org/wiki/PBKDF2#Alternatives_to_PBKDF2
    Source: https://stackoverflow.com/a/55147077/10492167
    
    To later decrypt the message use password_decrypt(token, password), where
    `token` is the output of this function.
    
    :type message: bytes or str
    :type password: str
    :type iterations: int
    :returns: bytes
    """
    if isinstance(message, str):
        message = message.encode(encoding)
    salt = secrets.token_bytes(16)
    key = _derive_key(password.encode(), salt, iterations)
    return b64e(
        b'%b%b%b' % (
            salt,
            iterations.to_bytes(4, 'big'),
            b64d(Fernet(key).encrypt(message)),
        )
    )


def password_decrypt(token, password):
    """
    Decrypts the token back to the bytes form of message.
    (`token` is the result of `password_encrypt(message, password)`)
    :type token: bytes
    :param token: the result of password_encrypt()
    :type password: str
    :returns: bytes
    """
    decoded = b64d(token)
    salt, iter, token = decoded[:16], decoded[16:20], b64e(decoded[20:])
    iterations = int.from_bytes(iter, 'big')
    key = _derive_key(password.encode(), salt, iterations)
    return Fernet(key).decrypt(token)
