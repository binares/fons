import re
from collections import namedtuple
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode

match_t = namedtuple('Match', 'pos end str')

asc = ''.join([chr(i) for i in range(128)])
alphanum = re.sub('[\W_]+','',asc)
symbols = re.sub('[{}]+'.format(alphanum),'',asc)

PROBABLY_INVALID_END = re.sub('[?+/&]+','',symbols)
#PROBABLY_INVALID_END = ['.,;:@!?()[]{}=']

#if url doesn't end with an alphanum, it is probably not necessary
#  (except some rare cases, e.g. it ending with a token containing symbols)

PATTERN = 'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+~]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
URL_SYMBOLS = alphanum + ':/' + '$-_.+!*\'()~#[]@,;=' + '?&='


def correct_old(new_match, correct={}, **kw):
    if not correct.get('indexes'):
        return
    
    old = correct['indexes']
    """for match in old:
        if new_match"""
    

def _get_url_indexes(txt):
    txt2 = txt.lower()
    i = 0
    indexes = []

    check = ('http://','https://','www.')
    lens = [len(c) for c in check]
    check_itms = list(zip(check,lens))
    min_address_part = 3 #site http://a.b
    
    while True:
        len_txt = len(txt)
        if i +4 > len_txt:
            break
        #print(i)
        #print(txt[i:])
        detected = False
        
        for c,ln in check_itms:
            #print("AA",txt2[i-ln:i])
            if i+ln > len_txt:
                continue
            elif txt2[i:i+ln] != c:
                continue
            
            nxt_i = i + ln
            #print(txt2[i-ln:i])
            
            if c in check[:2] and txt2[nxt_i:nxt_i+4] == 'www.':
                nxt_i += 4

            """if txt[i-1] != " ":
                txt = txt[:i] + " " + txt[i:]
                txt2 = txt2[:i] + " " + txt2[i:]
                nxt_i += 1
                i + = 1"""

            indexes.append(i)

            #nxt_i += min_address_part
            i = nxt_i
            detected = True
            break

        if not detected:
            i+=1

    return indexes


def _get_urls(txt):
    indexes = _get_url_indexes(txt)
    len_ind = len(indexes)
    #print(indexes)

    matches = []
    
    for k,i in enumerate(indexes):
        if k < len_ind-1:
            i2 = indexes[k+1]
        else:i2 = len(txt)

        txt_part = txt[i:i2]

        """space_loc = txt_part.find(" ")
        
        if space_loc != -1:
            part2 = txt_part[:space_loc]
        else:part2 = txt_part"""

        end = next((j for j,x in enumerate(txt_part) if x not in URL_SYMBOLS),len(txt_part))
        url = txt_part[:end]

        #eliminating accidental concatenings:
        url = url.strip(PROBABLY_INVALID_END)
        #www.goole.com/. Next sentence -> www.goole.com/
        #www.goole.com/page.Next sentence  -> www.goole.com/page.Next
        # (in cases similar to that it'd be too difficult to tell if the end is part of the link or not)

        match = match_t(i,i+len(url),url)
        
        matches.append(match)

    return matches


def find_urls(txt, return_match=True):
    match = _get_urls(txt)
    if not return_match:
        return [m.str for m in match]

    return match
        
    
def filter_urls(txt, replace=':url:', **kw):
    match = kw.get('match')
    if match is None:
        match = find_urls(txt)

    for x in reversed(match):
        txt = txt[:x[0]] + replace + txt[x[1]:]

    return txt



#------------------------------------------
#A DIFFERENT METHOD (excludes www. and non spaced links)
def _prepare_text(txt):
    txt2 = txt.lower()
    #indexes = []
    i = len(txt)

    check = ('http://','https://','www.')
    lens = [len(c) for c in check]
    check_itms = list(zip(check,lens))
    min_address_part = 3 #site http://a.b
    
    while True:
        if i - 4 < 0:
            break
        #print(i)
        #print(txt[i:])
        detected = False
        
        for c,ln in check_itms:
            #print("AA",txt2[i-ln:i])
            if i-ln < 0:
                continue
            elif txt2[i-ln:i] != c:
                continue
            
            nxt_i = i - ln
            #print(txt2[i-ln:i])
            
            if c == 'www.':
                for c2,ln2 in check_itms[:2]:
                    if nxt_i-ln2 <0: continue
                    elif txt2[nxt_i-ln2:nxt_i] == c2:
                        nxt_i -= ln2
                        break

            if nxt_i>0 and txt[nxt_i-1] != " ":
                txt = txt[:nxt_i] + " " + txt[nxt_i:]
                txt2 = txt2[:nxt_i] + " " + txt2[nxt_i:]
                nxt_i -= 1


            nxt_i -= min_address_part
            i = nxt_i
            detected = True
            break

        if not detected:
            i-=1

    return txt


def filter_links(txt,replace=':url:',filter_end=True):
    #txt = _prepare_text(txt)
    
    if not filter_end:
        return re.sub(PATTERN,replace,txt)

        
    matches = find_links(txt,filter_end=True,is_prepared=True)

    for x in reversed(matches):
        txt = txt[:x[0]] + replace + txt[x[1]:]

    return txt

    """
    len_txt = len(txt)
    for _id in ('http://', 'https://'):
        try:
            while True:
                i = txt.index(_id)
                end = next((i+j for j,x in enumerate(txt[i:]) if x == " "),len_txt)
                txt = txt[:i] + replace + txt[end:]
            
        except ValueError: pass

    return txt"""
    

def find_links(txt, filter_end=True, return_iter=True, **kw):
    #if not kw.get('is_prepared'):
        #txt = _prepare_text(txt)
        
    if not return_iter and not filter_end:
        return re.findall(PATTERN,txt)
    
    _iter = re.finditer(PATTERN,txt)
    matches = []

    for x in _iter:
        lnk = x.group()
        index = x.span()[0]
        end = x.span()[1]
        
        if filter_end:
            lnk = lnk.strip(PROBABLY_INVALID_END)
            end = index + len(lnk)

        matches.append(match_t(index,end,str))

  
    if not return_iter:
        return [x.str for x in matches]
    
    return matches
    

#---------------------------------------


def main():
    from urllib.request import urlopen
    txt = 'http://google.com, go to that site.https://www.goodshopping.info/buy?socks=2. '+\
          'Finallywww.bookreader.es/new/fiction?author=rowling+publisher=Frameworks~link_end,more_text'+\
          'http://bookreader.es/new/fiction?author=rowling+publisher=Frameworks~link_end,'+\
          'https://yahoo.com.https://www.yahoo.com/. And then we wen to.http://yahoo.comhttp://www.yahoo.comwww.yahoo.com'

    """urls = find_links(txt,filter_end=False,return_iter=False)
    urls2 = find_links(txt,filter_end=True,return_iter=False)
    urls2b = [u.strip(strip_urlend) for u in urls]"""

    urls = find_urls(txt)
    urls_replaced = filter_urls(txt)
    
    print(urls,"\n")
    #print(urls2,"\n")
    #print(urls2b,"\n")

    print(urls_replaced)

    """def decode_urls(urls):
        for u in urls:
            try:
                print(urlopen(u).geturl())
            except Exception as e:
                print(e.args[0], u)"""

    #decode_urls(urls2)
    #decode_urls(urls)
    
    
            
    
    

if __name__ == '__main__':
    main()
    
