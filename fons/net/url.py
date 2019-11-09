from http.client import HTTPConnection
from urllib.parse import (urlparse, urlunparse)

from urllib.request import urlopen
import requests

from fons.net.urlstr import (find_urls, filter_urls)

import datetime
dt = datetime.datetime
td = datetime.timedelta

import math
#from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed

import logging

UTM_QUERY_PARAMS = ['utm_source','utm_medium','utm_campaign','utm_term','utm_content']
STRIP_PARAMS = ['cmpid%3D','cmpid%2D','cmpid','__source','mod','link','xid','ncid','sr_share','_cookie-check','dcmp','ftag'] + UTM_QUERY_PARAMS


def expand_url_http(url, limit=5, timeout=None, as_absolute=False, **kw):
    """The HTTPConnection variant of expand_url. 
    Does not work on certain urls, e.g. those starting with https://t.co/... """
    seen = kw.get('seen')
    if seen is None: seen = []
    
    if not len(seen) or seen[-1] != url:
        seen.append(url)
        logging.debug('Expanding: {}'.format(url))

    return_seen = kw.get('return_seen')
    if return_seen is None: return_seen = False
    
    start = kw.get('start',dt.utcnow())
    timeout_left = timeout
    if timeout is not None and as_absolute:
        timeout_left = max(0, round(timeout-(dt.utcnow() - start).total_seconds(), 2))
        
    exclude_domains = kw.get('exclude_domains')
    if exclude_domains is None: exclude_domains = []
    parsed = urlparse(url)
    
    if parsed.netloc in exclude_domains: pass
    elif limit is None or limit > 0:
        h = HTTPConnection(parsed.netloc, timeout=timeout_left)
        resource = parsed.path
        if parsed.query != "":
            resource += "?" + parsed.query
        h.request('HEAD', resource )
        response = h.getresponse()
    
        location = response.getheader('Location')
        #print(response.status,location)
        
        if not location: pass
        elif int(response.status/100) != 3: pass
        elif response.status == 302:
            #301 is sometimes final, 302 seems to be always final
            url = location
            try: assert seen[-1] != url
            except (IndexError,AssertionError):pass
            else: seen.append(url)
            
        elif location not in seen:
            new_limit = limit -1 if limit is not None else None
            return expand_url_http(location, new_limit, timeout, as_absolute, 
                              seen=seen, start=start, return_seen=return_seen, exclude_domains=exclude_domains)
    
    if return_seen:
        return seen
    
    return url


def expand_url(url, limit=5, timeout=None, as_absolute=False, **kw):
    session = kw.get('session')
    if session is None:
        session = requests.session()
    seen = kw.get('seen')
    if seen is None: seen = []
    
    if not len(seen) or seen[-1] != url:
        seen.append(url)
        logging.debug('Expanding: {}'.format(url))

    return_seen = kw.get('return_seen')
    if return_seen is None: return_seen = False
    
    start = kw.get('start',dt.utcnow())
    timeout_left = timeout
    if timeout is not None and as_absolute:
        timeout_left = max(0, round(timeout-(dt.utcnow() - start).total_seconds(), 2))
        
    exclude_domains = kw.get('exclude_domains')
    if exclude_domains is None: exclude_domains = []
    parsed = urlparse(url)
    
    if parsed.netloc in exclude_domains: pass
    elif limit is None or limit > 0:
        #response = requests.head(url,allow_redirects=False,timeout=timeout_left)
        response = session.head(url,allow_redirects=False,timeout=timeout_left)
        location = response.headers.get('location')
        #print(response.status_code,location)
        
        if not location: pass
        elif int(response.status_code/100) != 3: pass
        elif response.status_code == 302:
            #301 is sometimes final, 302 seems to be always final
            url = location
            try: assert seen[-1] != url
            except (IndexError,AssertionError):pass
            else: seen.append(url)
            
        elif location not in seen:
            new_limit = limit -1 if limit is not None else None
            return expand_url(location, new_limit, timeout, as_absolute, session=session,
                              seen=seen, start=start, return_seen=return_seen, exclude_domains=exclude_domains)
    
    if return_seen:
        return seen
    
    return url


def expand(urls, max_concurrent=50, timeout=20, **kw):
    """It's recommended to NOT set timeout to absolute, due to threads not processing in synchronized manner"""
    """len_urls = len(urls)
    pool_size = min(len_urls,max_concurrent)
    nr_packs = ceil(len_urls/pool_size)"""
    single = isinstance(urls,str)
    if single: urls = [urls] 
    
    return_seen = kw.get('return_seen')
    if return_seen is None: return_seen=False
    
    seen = kw.get('seen')
    try: kw.pop('seen')
    except KeyError: pass
    
    if seen is None and return_seen:
        seen = []

    def get_seen(i):
        try: 
            return seen[i]
        except (TypeError,IndexError):
            pass
        
        item = []
        if seen is not None:
            seen.append(item) 
        
        return item
        

    #for i in range(nr_packs):
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_url = {
            executor.submit(
                expand_url, url, seen=get_seen(j), timeout=timeout, **kw
            ): [j,url] for j,url in enumerate(urls)
        } #[i*pool_size:(i+1)*pool_size]])
        
        for future in as_completed(future_to_url):
            pk = future_to_url[future]

            try:
                data = future.result()
                pk.append(data)
            except Exception as exc:
                if return_seen:
                    seen = get_seen(pk[0])
                    seen.append(None)
                    pk.append(seen)
                else: pk.append(None)
                #print('%r generated an exception: %s' % (pk[1], exc))
            """else:
                print('%r page is %d bytes' % (pk[1], len(data)))"""
                              
    expanded = [x[2] for x in sorted(future_to_url.values(), key= lambda x:x[0])]
    
    return expanded if not single else expanded[0]


"""def expand2(urls,max_concurrent=200,**kw):
    import multiprocessing

    len_urls = len(urls)
    pool_size = min(len_urls,max_concurrent)
    
    def wrap(f):
        def f2(url):
            return f(url,**kw)
        return f2
    
    w_unshorten_url = wrap(expand_url)
    
    pool = multiprocessing.Pool(processes=pool_size)
    
    outputs = []
    nr_packs = ceil(len_urls/pool_size)
    
    for i in range(nr_packs):
        outputs += pool.map(w_unshorten_url, urls[i*pool_size:(i+1)*pool_size])
        
    return outputs
    #threads = [Thread(target=extend_url,args=[url,levels,timeout]) for url in urls]"""
    

session = None

#Slower version
def expand_url2(url, timeout=10, **kw):
    global session
    if not session:
        session = requests.session()
    
    r = session.head(url, allow_redirects=True, timeout=timeout)
    e_url = r.url
        
    """"r = urlopen(url,timeout=timeout)
    e_url = r.geturl()"""

    return e_url


def expand_in_text(text, max_len=None, strip_params=STRIP_PARAMS, **kw):
    match = find_urls(text)
    urls = [x.str for x in match]
    seen = []
    kw.update({'seen': seen, 
               'exclude_domains': ['youtu.be']})
        
    expand(urls, **kw)

    _strip = globals()['strip_params']
    def strip_url(url):
        stripped = _strip(url, strip_params)
        if max_len is not None and len(stripped) > max_len:
            return None
        return stripped

    stripped = ([strip_url(y) if y else y for y in x] for x in seen)
    expanded = list(stripped)
    expanded_last_nonna = [next((y for y in reversed(x) if y),None) for x in expanded]
            
    for m,url in reversed(list(zip(match,expanded_last_nonna))):
        text = '{}{}{}'.format(text[:m.pos],(url if url else m.str),text[m.end:])
    return text
        

def strip_params(url, params):
    up = urlparse(url)
    split = up.query.split('&')
    
    if params is not True:
        query_new = '&'.join(x for x in split if x[:x.find('=')].lower() not in params)
    else:query_new = ''
    
    up2 = up._replace(query=query_new)
    
    return urlunparse(up2)
    
    
def strip_utm(url):
    return strip_params(url, UTM_QUERY_PARAMS)


def strip_www(url):
    low = url.lower()
    if low.startswith('https://www.') or low.startswith('http://www.'):
        loc = low.find('www.')
        url =  url[:loc] + url[loc+len('www.'):]
    
    return url



#The old version of expand_url:
def extend_url(url, levels=None, timeout=10, **kw):
    lvl = kw.get('lvl',0)
    if levels is not None and lvl >= levels:
        return url
    elif len(url) > 32:
        return url
        
    r = urlopen(url,timeout=timeout)
    e_url = r.geturl()
    lvl += 1
    #print(lvl,e_url)

    if url != e_url:
        extend_url(e_url,levels,timeout,lvl=lvl)

    return e_url




if __name__ == '__main__':
    url = "https://t.co/L0t4lQ3hT7"
    e_url = extend_url(url, levels=5)
    #print(e_url)

    seen = []
    e_url = expand_url(url, limit=5, seen=seen)
    print('{}\n{}'.format(e_url, seen))
    print(strip_utm(e_url))
    
    seen = []
    print(expand(['https://bit.ly/2rwwupw','https://bit.ly/2I6HWDu',
                      'https://t.co/ydBPKn4wO0','http://t.co/hAplNMmSTg',
                      'http://f-st.co/THHI6hC',
                      ],seen=seen))
    print(seen)
    
