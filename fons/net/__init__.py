from . import (url, urlstr)

import asyncio
import aiohttp
import functools
import requests

_sessions = {}


def init_session(loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()
    _sessions[loop] = session = aiohttp.ClientSession(loop=loop)
    return session


def get_session(loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()
    try: return _sessions[loop]
    except KeyError:
        return init_session(loop)
    
    
def close_sessions():
    for loop,session in _sessions.copy().items():
        if loop.is_running():
            partial = functools.partial(asyncio.ensure_future,session.close(),loop=loop)
            loop.call_soon_threadsafe(partial)
        else:
            loop.run_until_complete(asyncio.wait([session.close()]))
        del _sessions[loop]


async def fetch(url, session=None, *, loop=None, **kw):
    if session is None:
        session = get_session(loop)   
    #async with session:
    async with session.get(url,**kw) as response:
        return (await response.read()).decode('utf-8')


async def post(url, session=None, *, loop=None, **kw):
    if session is None:
        session = get_session(loop)
    
    async with session.post(url,**kw) as response:
        return (await response.read()).decode('utf-8')


def get_tor_session():
    session = requests.session()
    # Tor uses the 9050 port as the default socks port
    session.proxies = {'http':  'socks5://127.0.0.1:9050',
                       'https': 'socks5://127.0.0.1:9050'}
    return session