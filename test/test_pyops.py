from fons.pyops import update_obj

D1 = {'a':{'aa':0,'ab':{'aba':10,'abb':11},'ac':0.2},
     'b':[1],
     'c':2}  

D2 = {'a':{'ab':{'abb':None}},
      'b':'newb'}

D = {'a':{'aa':0,'ab':{'aba':10,'abb':None},'ac':0.2},
     'b':'newb',
     'c': 2 }


Ls1 = ['A','B','C']
Ls2 = ['_keep_','BA']
Ls = ['A','BA']

D4 = {'a':{'aa':(1,2,Ls1,4,5)}}
D5 = {'a':{'aa':['_keep_',22,Ls2,'_keep_']},'b':'bnew'}
alist1 = [2,D4]
alist2 = ['_keep_', D5, 'new1','new2']
alist = [2, {'a':{'aa':[1,22,Ls,4]},'b':'bnew'}, 'new1','new2']
          
_gi1 = {'news':{'twitter':{'filter':['CrownPlatform']}},'reddit':{},'forward_to':'Crypto'}
_gi2 = {'twitter':{'filter':['_keep_','BlockThisGuy']}}
_gi = {'news':{'twitter':{'filter':['CrownPlatform','BlockThisGuy']}},'reddit':{},'forward_to':'Crypto'}

        
def test_update_obj():
    D3 = update_obj(D1,D2)
    assert D1 == D
    
    """pp.pprint(Ls1)
    pp.pprint(alist1)"""
    alist3 = update_obj(alist1,alist2)

    """pp.pprint(Ls1)
    pp.pprint(alist1)"""
    assert alist1 == alist
    assert alist3 == alist

    assert Ls1 == Ls

    #pp.pprint(_gi1)
    update_obj(_gi1,{'news':_gi2})
    #pp.pprint(_gi1)
    assert _gi1 == _gi
