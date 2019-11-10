import pytest
from cryptography.fernet import InvalidToken
from fons.crypto import password_encrypt, password_decrypt

password = 'k2L0?me!r7Gs'
typo_password = password[:-1] + 'd'

DATA = [
    '',
    'a',
    'This text will be encrypted',
    'Hello world! #s{}:'.format('\u20ac\u00a3'), #euro pound
]

@pytest.mark.parametrize('text', DATA)
def test_encrypt_decrypt(text):
    btext = text.encode('utf-8')
    encoded = password_encrypt(btext, password)
    
    assert encoded != btext
    
    btext2 = password_decrypt(encoded, password)
    text2 = btext2.decode('utf-8')
    
    assert text == text2
    
    with pytest.raises(InvalidToken):
        password_decrypt(encoded, typo_password)
    