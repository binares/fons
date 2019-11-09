from fons.net.url import expand_url, expand, strip_params, find_urls, expand_in_text


def _test_expand_url():
    url = 'https://t.co/L0t4lQ3hT7'
    expected_seen = ['https://t.co/L0t4lQ3hT7', 'http://wef.ch/2yg5TRT', 'https://www.weforum.org/agenda/2017/09/dubai-has-successfully-tested-the-first-flying-taxi?utm_content=buffer98989&utm_medium=social&utm_source=twitter.com&utm_campaign=buffer']
    seen = []
    
    assert expand_url(url,seen=seen) == expected_seen[-1]
    assert seen == expected_seen
    
    
def _test_expand(nr=10):
    urls = ['https://bit.ly/2rwwupw','https://bit.ly/2I6HWDu',
            'https://t.co/ydBPKn4wO0','http://t.co/hAplNMmSTg',
            'http://f-st.co/THHI6hC',
            ]*nr
    
    expected = [x.lower() for x in
                ('https://www.youtube.com/watch?v=Lvf8koqX_yE&feature=youtu.be', 
                'https://www.youtube.com/watch?v=UrCs-GuAQDY&feature=youtu.be', 
                'https://www.coindesk.com/bitcoin-lightning-payments-slowly-becoming-less-reckless/', 
                'http://www.wtatennis.com/players/player/314320/title/simona-halep', 
                'https://www.fastcodesign.com/3016456/this-note-taking-system-turns-you-into-an-efficiency-expert?utm_source=facebook'
                )*nr ]
    
    expanded = [x.lower() if x is not None else x for x in expand(urls)]
    
    assert expanded == expected


def test_find_urls():
    urls = ['https://t.co/ydBPKn4wO0','https://bit.ly/2I6HWDu','www.google.com?search=sth&p2=null','http://www.yahoo.com']
    temp = "Hello to you, {0}, this here:{1}.\n{2}\r{3}. end"
    text = temp.format(*urls)
    expected = [[text.find(x),text.find(x)+len(x),x] for x in urls]
    found = find_urls(text)
    assert [list(x) for x in found] == expected
    
    
def _test_expand_urls_in_text():
    text = "Hello to you, https://t.co/ydBPKn4wO0 , this here:https://bit.ly/2I6HWDu. end"
    expanded = expand_in_text(text)
    expected = "Hello to you, https://www.coindesk.com/bitcoin-lightning-payments-slowly-becoming-less-reckless/, this here:https://www.youtube.com/watch?v=UrCs-GuAQDY&feature=youtu.be. end" 
    assert expanded == expected
    
    
def test_strip_params():
    url = 'https://www.weforum.org/agenda/2017/09/dubai-has-successfully-tested-the-first-flying-taxi?utm_content=buffer98989&utm_medium=social&utm_source=twitter.com&utm_campaign=buffer'
    expected = 'https://www.weforum.org/agenda/2017/09/dubai-has-successfully-tested-the-first-flying-taxi?utm_content=buffer98989&utm_campaign=buffer'
    
    assert strip_params(url,['utm_source','utm_medium']) == expected
