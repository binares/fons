from . import (url, urlstr)

import asyncio
import aiohttp
import aiohttp_socks
import functools
import requests

_sessions = {}


def init_session(loop=None, *, proxy=None):
    if loop is None:
        loop = asyncio.get_event_loop()
    connector = None
    kw = {'loop': loop}
    if proxy:
        connector = aiohttp_socks.ProxyConnector.from_url(proxy, loop=loop)
        del kw['loop']
    _sessions[(loop, proxy)] = session = aiohttp.ClientSession(connector=connector, **kw)
    return session


def get_session(loop=None, *, proxy=None):
    if loop is None:
        loop = asyncio.get_event_loop()
    try:
        return _sessions[(loop, proxy)]
    except KeyError:
        return init_session(loop, proxy=proxy)
    
    
def close_sessions():
    for k, session in _sessions.copy().items():
        loop, proxy = k
        if loop.is_running():
            partial = functools.partial(asyncio.ensure_future, session.close(), loop=loop)
            loop.call_soon_threadsafe(partial)
        else:
            loop.run_until_complete(asyncio.wait([session.close()]))
        del _sessions[(loop, proxy)]


async def fetch(url, session=None, *, loop=None, **kw):
    proxy = _resolve_proxy(kw)
    if session is None:
        session = get_session(loop, proxy=proxy)
    
    async with session.get(url,**kw) as response:
        return (await response.read()).decode('utf-8')


async def post(url, session=None, *, loop=None, **kw):
    proxy = _resolve_proxy(kw)
    if session is None:
        session = get_session(loop, proxy=proxy)
    
    async with session.post(url,**kw) as response:
        return (await response.read()).decode('utf-8')


def _resolve_proxy(kw):
    proxy = kw.pop('proxy', None)
    proxies = kw.pop('proxies', None)
    if proxies and not proxy:
        proxy = list(proxies.values())[0]
    
    return proxy


def get_tor_session():
    session = requests.session()
    # Tor uses the 9050 port as the default socks port
    session.proxies = {'http':  'socks5://127.0.0.1:9050',
                       'https': 'socks5://127.0.0.1:9050'}
    return session