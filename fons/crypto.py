import hmac
import hashlib
import base64 as _base64
import random
import string
import time

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
        sig = _base64.b64encode(sig)
        sig = sig.decode()
    return sig
