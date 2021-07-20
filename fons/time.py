import datetime 
dt = datetime.datetime
td = datetime.timedelta
import time

import numpy as np
import pandas as pd
offsets = pd.tseries.offsets
frequencies = pd.tseries.frequencies

from collections import namedtuple
import math
import logging

_EPOCH = dt(*time.gmtime(0)[:6])

_BusinessHour_Fixed_Version = None
_BUSINESSHOUR_FIXED = dt(1996,1,2,10) - offsets.BusinessHour(1) == dt(1996,1,2,9)

DT_FIELDS = ('year','month','day','hour','minute','second','microsecond')
TD_FIELDS = ('days','days','days','hours','minutes','seconds','milliseconds','microseconds')

_FREQS =[(td(365),'YS'),
         (td(30),'MS'),
         (td(1),'D'),
         (td(hours=1),'H'),
         (td(minutes=1),'T'),
         (td(seconds=1),'S'),
         (td(milliseconds=1),'ms'),
         (td(microseconds=1),'us'),
         #(offsets.Nano().delta,'N'),
         ]
_TD_DAY = td(1)
_A_DATETIME = dt(1996,1,1)
_A_PD_TIMESTAMP = pd.Timestamp(1996,1,1)


def dt_tuple(dto):
    dtt = namedtuple('dtt',DT_FIELDS)
    return dtt(*[getattr(dto,x) for x in dtt._fields])

    
def dt_indexing(dto, index, value=None):
    names = DT_FIELDS

    try:
        n = names[index]
        
        if value is not None:
            values = []
            for i,nm in enumerate(names):
                if i == index:
                    values.append(value)
                else:
                    values.append(getattr(dto,nm))
            new_dto = dt(*values)

            return new_dto

        else:
            return getattr(dto,n)
    
    except IndexError:
        raise IndexError('Index ' + str(index) + ' is out of range '+\
                         'for a datetime object.')


def dt_get(dto, index, up_to=False):
    if not up_to:
        return dt_indexing(dto,index)
    
    return dt(*dt_tuple(dto)[:index+1])


def dt_assign(dto, index, value):
    return dt_indexing(dto,index,value)


def dt_round_to_digit(dto, index_or_freq):
    """Rounds datetime to nearest digit. For convenience 6=ms and 7=us"""
    
    if not isinstance(index_or_freq,int):
        freq_td = freq_to_td(index_or_freq)
        index = next((i for i,t in enumerate(_FREQS) if freq_td >= t[0]),7)
    else:
        index = index_or_freq if index_or_freq >= 0 else 8 +max(-8,index_or_freq)

    if index > 6:
        return dto
    
    new_dto_values = [datetime.MINYEAR,1,1,0,0,0,0]
    
    for i in range(index+1):
        new_dto_values[i] = dt_get(dto,i)
    
    #round the microseconds to milliseconds
    new_dto_values[6] = int(new_dto_values[6]/1000)*1000
    
    return dt(*new_dto_values)


def dt_isround(dto, from_index):
    dtt = dt_tuple(dto)
    
    if isinstance(from_index,str):
        from_index = DT_FIELDS.index(from_index.lower())
    
    for i,v in enumerate(dtt):
        if i <= from_index: continue
        elif i < 3:
            if v != 1: return False
        elif v != 0: return False
        
    return True


def ts_round(timestamp, freq, base=0, shift=0, *, as_pydt=False, **kw):
    """Round timestamp (seconds)"""
    dto = dt_round(pydt(timestamp), freq, base=base, shift=shift, **kw)
    if as_pydt:
        return dto
    return _timestamp(dto)


def ms_round(timestamp, freq, base=0, shift=0, *, as_pydt=False, **kw):
    """Round milliseconds (from epoch)"""
    dto = dt_round(pydt_from_ms(timestamp), freq, base=base, shift=shift, **kw)
    if as_pydt:
        return dto
    return timestamp_ms(dto)


def dt_round(dto, freq, base=0, shift=0, **kw):
    """Round datetime object to nearest offset (freq) point.
       :param dto: datetime
       :param freq: timedelta, (pandas) offset, (pandas) freqstr,
                    int/float->timedelta(seconds=dto)
        Examples:
            dt_round(dt(1996,2,2,15,39), 'M') -> dt(1996,2,1)
            dt_round(dt(1996,2,2,15,39), 'H') -> dt(1996,2,1,15)"""
    roffset = dt_round_freq(freq)
    rounded = dt_synced(dto,roffset,base,shift)
      
    normalize = kw.get('normalize')
    
    if normalize is None:
        freq_td = freq_to_td(freq,coerce=True)
        normalize = freq_td >= td(1) or freq_td <= td(-1)
        
    if normalize:
        rounded = dt_round_to_digit(rounded,td(1))
              
    return rounded


def dt_round2(dto, freq, base=0, shift=0, **kw):
    #series.resample
    # >> does NOT automatically normalize if
    #     <offset> = n*<days>  | n>1 [e.g td(hours=48) / '2D']
    #     <offset> < td(1)     |     [e.g td(hours=13)]
    # >> freq 'BH' can often raise ValueError for no apparent reason,
    #       and sometimes starts with 17:00 of previous businessday (T10-> -1BT17)
    #series.asfreq
    # >> never normalizes, unless normalize=True
    # >> `base` is always the first element [e.g [T01:07,..] -asfreq('5T')> [T01:07,rounded...]]
    # >> non-exact offsets rounded UP to first occurrence, any below that excluded 
    #    [e.g Series('',[dt(1996,2,29,2,3),dt(1996,3,1,1,2)]).asfreq('MS') -> Series([])
    #         Series('',[dt(1996,2,29,2,3),dt(1996,3,1,5,6)]).asfreq('MS') -> Series('',[dt(1996,3,1,2,3)])
    #         Series('',[dt(1996,1,1,8,2),dt(1996,1,1,9,5)]).asfreq('BH') -> Series('',[dt(1996,1,1,9)])
    #         Series('',[dt(1996,1,1,9,5)]).asfreq('BH') -> Series('',[dt(1996,1,1,9,5)])
    #     (note the inconsistency between MH and BH base)
    #-->use resample for everything except 'BH'
    
    roffset = dt_round_freq(freq)
    
    nxt = dto + roffset
    if roffset.n == 0 or nxt == dto:
        raise ValueError('freq == 0: {}'.format(freq))
    #print(roffset)
    
    try: assert roffset.name == 'BH'
    except (NotImplementedError,AssertionError): pass
    else: return _dt_round_bh(dto,roffset.n/abs(roffset.n),shift,**kw)
    
    
    polarity = 1 if nxt > dto else -1
    
    
    if polarity == 1:
        #ofs.MonthBegin() would round the dto to the next month here, can't use it
        """dr = pd.date_range(dto,periods=1,freq=freq)"""
        s = pd.Series(False,index=[dto]) #dr)
        #Note: roffset param `normalize` has absolutely no effect, in both cases of asfreq and groupby
        #NB! resample/groupby can only handle positive frequencies
        #Note: base will only have effect if freq < td(1)
        s2 = s.resample(roffset,base=base).asfreq()
        #s2 = s.groupby(pd.TimeGrouper(roffset)).all()
        rounded = s2.index[0]
        
    else:
        rounded = dt_synced(dto,roffset,base)

        
    #decided not to implement (resample would differ from dt_round):
    """#make sure that e.g. dt(2001,1,31,13),'M' is rounded up, not to the same day
    if not isinstance(roffset,(offsets.MonthEnd,offsets.YearEnd)): pass
    elif dto > rounded:
        rounded += roffset"""
    
    if shift:
        rounded += shift*roffset
        
    normalize = kw.get('normalize')
    
    if normalize is None:
        freq_td = freq_to_td(freq,coerce=True)
        normalize = freq_td >= td(1) or freq_td <= td(-1)
        
    #rounded = s.asfreq(freq,normalize=normalize).index[0]
    if normalize:
        rounded = dt_round_to_digit(rounded,td(1))
              
    return rounded


def dt_round_freq(freq, coerce=False, return_as='offset'):
    if return_as not in ('timedelta','td','offset','str'):
        raise ValueError(return_as)
    
    round = True
    
    try:
        ftd =  freq_to_td(freq, coerce=coerce)
        abs_ftd = abs(ftd)
        #round to digit:
        ftd0,label = next((x,y) for x,y in _FREQS if abs_ftd >= x)
        
        if abs_ftd < td(1):
            round = False

        div = int(ftd/ftd0)

        if return_as in ('timedelta','td'):
            freq = ftd0*div
        else: freq = str(div) + label
                
    except ValueError as e:
        if return_as in ('timedelta','td'):
            raise ValueError('Setting coerce=False cannot round this freq: {}'.format(freq))


    #---------------------
    #round the digit to 1:
    if round:
        if not isinstance(freq, offsets.DateOffset):
            freq = freq_to_offset(freq)
        if freq.n != 1:
            freq = _rebuild_offset(freq, n=1, keep_polarity=True)
        
    #_use_relativedelta *can* be True only for DateOffset class (not sublclasses, like 'MonthBegin')   
    if type(freq) is offsets.DateOffset and freq._use_relativedelta:
        kwds = {k: (1 if v > 0 else -1) for k,v in freq.kwds}
        freq = offsets.DateOffset(freq.n, **kwds) #freq.normalize
        
    if isinstance(freq, offsets.DateOffset) and freq.normalize:
        freq = _rebuild_offset(freq)

    #--------------------
        
    if return_as == 'offset':
        freq = freq_to_offset(freq)
    elif return_as == 'str':
        freq = freq_to_str(freq)
    else:
        freq = freq_to_td(freq)
        
    return freq


def dt_synced(dto, freq, base=None, shift=0):
    """Syncs dto to base, i.e. base + n*freq.
       Base may be `None`, int or datetime.
        `None`: -> base = dto
        int: works similar to pandas.Series.resample(freq,base=...).
             Note: time will be lost if is relative timedelta.
        dt: exact point of reference which time must pass through.
            Note: if relativedelta, this will be rounded to nearest point in negative direction,
                  preserving the exact time (except for businesshours, which will modify the hour part)."""    
    offset = freq_to_offset(freq) #.copy()
    
    dto2 = dto + offset
    rforward = dto2 > dto

    if dto2 == dto or offset.n == 0:
        raise ValueError('Frequency must be non-zero, got: {}'.format(freq))

    is_bh = isinstance(offset,offsets.BusinessHour)
    bh = offsets.BusinessHour(1)

    ndto = None
    if base is None: base = dto
    elif isinstance(base,int):
        ndto = dt_round_to_digit(dto,td(1))
        if not rforward and ndto != dto:
            ndto += td(1)
            #print(ndto)
    elif not isinstance(base,dt):
        raise TypeError(type(base))
    
    #To-do: determine the polarity with series.resample (would include custom-defined DateOffsets)
    name = offset.__class__.__name__
    is_end = name.endswith('End') or offset.__class__ is offsets.Week
    if is_end: fpolarity = True
    elif name.endswith('Begin'):fpolarity = False
    else: fpolarity = False
    
    if not rforward:
        fpolarity = not fpolarity
    
    
    try:
        delta = freq_to_td(offset, coerce=False)
        #if delta > td(0):
        round_op = math.floor
        #else: round_op = math.ceil
        
        if ndto is not None:
            abs_n,abs_base = abs(offset.n),abs(base)
            p = 1 if base >= 0 else -1
            base = ndto + p*(abs_base % abs_n)/abs_n * delta
            #print(ndto,base,freq,offset)
        
        n = round_op((dto - base)/delta)
        synced = base + (n+shift)*delta
        
        
    except ValueError:
        if ndto is not None:
            base = ndto

        #To not exclude e.g. dt(1996,1,31,2) from 2016 Jan ('MonthEnd')
        if is_end:
            dto = dt_round_to_digit(dto,td(1))
            
        if dto > base: tlforward = True
        elif dto == base: tlforward = rforward
        else: tlforward = False

        if tlforward: 
            addend,op = (offset, dto.__lt__)
        else: addend,op = (-1*offset, dto.__gt__)
        
        if not rforward:
            addend *= -1
            
        synced = base

        if is_bh and not _BUSINESSHOUR_FIXED:
            #The problems arise when base is not synced:
            # T18:00 + bh = ..T10:00
            synced -= addend
            #preserving the min,s,us of base (which due to error was currently lost if base was not in range of daily bh-s) 
            synced = dt(*dt_tuple(synced)[:4],*dt_tuple(base)[4:])
            
            if synced.hour == 17:
                synced = synced - bh + bh # 17 -> 16 -> 9
            
            while not op(synced):
                synced += addend
                if synced.hour == 17:
                    synced = synced - bh + bh
        else:
            while not op(synced):
                synced += addend
        
        prev = synced - addend

        if is_bh and not _BUSINESSHOUR_FIXED and prev.hour == 17:
            prev = prev - bh + bh
            
        #print(synced,prev,tlforward!=fpolarity,prev==dto,base,offset)
        if tlforward!=fpolarity or prev == dto:
            synced = prev
            
        if shift:
            synced += shift*offset
            
            if is_bh and not _BUSINESSHOUR_FIXED and synced.hour == 17:
                synced = synced - bh + bh
    
    return synced
    
    
def _dt_round_bh(dto, polarity=1, shift=0, **kw):
    normalize = kw.get('normalize',False)
    bh = offsets.BusinessHour(polarity)
    
    dto = dt_round_to_digit(dto,td(hours=1))
    rounded = dto - bh
    
    if rounded.hour != 17:
        dto2 = rounded + bh
        if dto2 == dto:
            rounded = dto2
    else:rounded += bh
    

    if shift:
        rounded += shift * bh
        if rounded.hour == 17:
            #can only happen if polarity(shift) != polarity(bh)
            rounded += bh*polarity
            
    if normalize:
        rounded = dt_round_to_digit(rounded,td(1))
    
    return rounded


def freq_to_td(freq, coerce=False):
    #Important note:
    #pd handles differently freqs that are <td(1) and >=td(1)
    # in the former case the base is always the 00:00 of the current day (e.g. 7T -> 00:00 + n*7min)
    # in the latter case however the base is *the first GIVEN element*, unless specific str offset given ('M'/'MS'/Y'/'YS'...)
    if isinstance(freq,td): pass
    
    elif isinstance(freq,np.timedelta64):
        freq = pd.to_timedelta(freq)
        
    elif isinstance(freq,(int,float)):
        freq = td(seconds=freq)
        
    elif isinstance(freq,(str,offsets.DateOffset)):
        #1996,1,1 is Monday, perfect for calculating e.g. 1BH/BD (business hour/business week)
        # also, it is a leap year (jan + feb = 60 days == 2M)
        adt = _A_PD_TIMESTAMP
        #Note: freq.normalize value won't affect the date_range function
        dtrange = pd.date_range(adt,periods=2,freq=freq)
        
        try: freq = dtrange.freq.delta
        except AttributeError:
            if coerce: pass
            elif type(freq) is not offsets.DateOffset or freq._use_relativedelta:
                raise ValueError('Cannot be cast to td: {}'.format(freq))
            freq = dtrange[1] - dtrange[0]    
            if freq < td(0):
                dtrange = pd.date_range(adt,periods=2,freq=-1*dtrange.freq)
                freq = dtrange[0] - dtrange[1]
            
    else: 
        raise TypeError(freq)
    
    return freq


def freq_to_str(freq):
    return freq_to_offset(freq).freqstr


def freq_to_offset(freq):
    if isinstance(freq, (int,float)):
        freq = td(seconds=freq)
    elif isinstance(freq, np.timedelta64):
        freq = pd.to_timedelta(freq)
    
    if freq == td(0):
        if not isinstance(freq, offsets.Second):
            freq = offsets.Second(0)
        return freq
    
    ftype = type(freq)
    adt = _A_PD_TIMESTAMP
    
    if ftype is offsets.DateOffset and not freq._use_relativedelta:
        #Convert the DateOffset to one of its subclasses
        #normalize = freq.normalize
        delta = (adt + freq) - adt
        freq = pd.date_range(adt,periods=1,freq=delta).freq
        #freq.normalize = normalize  #should it be left?
        
    elif issubclass(ftype,offsets.DateOffset): pass
    
    elif issubclass(ftype,(str,td)):
        freq = pd.date_range(adt,periods=1,freq=freq).freq
        
    else: raise TypeError(ftype)
    
    return freq


def _rebuild_offset(offset, n=None, keep_polarity=False):
    n0 = offset.n
    
    if n is None:
        n = n0
    elif isinstance(n, int):
        if keep_polarity and n0 < 0:
            n *= -1
    else:
        raise ValueError(n)
    
    #Before pandas 0.25.0 we could just do
    # offset = offset.copy()
    # offset.n = n
    # offset.normalize = False
    #but currently offsets are immutable
    
    if type(offset) is not offsets.DateOffset:
        if '<' not in offset.freqstr:
            freq_str = offset.freqstr.lstrip(' -')
            start_from = next((i for i,x in enumerate(freq_str) if not x.isdigit()),len(freq_str))
            freq_str = str(n) + freq_str[start_from:]
        else:
            #Does this happen?
            #freq_str = str(n)+offset._prefix #this may be inaccurate
            raise ValueError('Unknown offset freqstr: "{}"'.format(freq_str))
            
        freq = frequencies.to_offset(freq_str)
    
    else:
        #DateOffset class itself doesn't have a prefix, and its freqstr can't be easily interpreted
        freq = offsets.DateOffset(n, **offset.kwds)
        
    return freq
    
#####################################

def dt_round_strf(strf, freq):
    freq = freq_to_td(freq)
    strf_parts = strf.split('%')[1:]
    #strf = '%Y-%m-%dT%H-%M-%S-%f'
    
    dto = dt(2000,*[1]*6)
    dtt_r = dt_tuple(dt_round(dto,freq))
    
    if freq.days > 365:
        nr_keep = 1
    elif freq.days > 30:
        nr_keep = 2
    else:
        nr_keep = next((i for i,x in enumerate(dtt_r) if not x),len(dtt_r))
        
    #print(strf_parts,dto,dtt_r,nr_keep)
    
    strf_vars = {0: ('Y','y'),
                 1: ('m','-m'),
                 2: ('d','-d'),
                 3: ('H','-H','I','-I'),
                 4: ('M','-M'),
                 5: ('S','-S'),
                 6: ('f',)}
    
    strf_keep = []
    last_appended = (None,None)
    
    for n,x in enumerate(strf_parts):
        for i in range(nr_keep):
            if x[:1] in strf_vars[i] or x[:2] in strf_vars[i]:
                strf_keep.append(x)
                last_appended = (n,i)
                continue
            

    #print(strf_keep)
    
    #If e.g %Y-%m-%dT%H-%M-%S was shortened to %Y-%m-%dT%H-%M- 
    # --> we'd want to trim the last part to %Y-%m-%dT%H-%M (cut the "-")
    if last_appended[0] is not None:
        n,i = last_appended
        part = strf_parts[n]
        
        if n < len(strf_parts) -1:
            for v in strf_vars[i]:
                length = None
                if v == part[:1]:
                    length = 1
                elif v == part[:2]:
                    length = 2
                    
                if length and len(part) > length:
                    strf_keep[-1] = strf_keep[-1][:length]
                    
            
    return '%' + '%'.join(strf_keep) if len(strf_keep) else ''


#unlike dt.strptime(), it can also handle shortened time strings, like %Y-%m-%d, with given longer format
def dt_strp(dtstrf, base_strf="%Y-%m-%dT%H-%M-%S-%f"):
    #strf_parts = base_strf.split('%')[1:]
    parts = base_strf.split('%')
    lengths = [len(x) for x in parts]
    
    dto = None

    for n in range(1,(max(lengths)+1)):
        for i in range(len(parts)):
    
            try:
                border = len(parts)-(i+1)
                last_el = parts[border]

                if len(last_el) < n:
                    continue
                else: appendee = last_el[:n]
                
                strf_format = "%".join(parts[:border]) + '%' + appendee
                #print(strf_format)
                dto = dt.strptime(dtstrf,strf_format)
                break
            
            except Exception:
                #traceback.print_exc()
                pass
        
    if not dto:
        raise ValueError(dtstrf,base_strf)
    
    return dto


###############################

def _set_win_time(dto):
    time_tuple = dt_tuple(dto)
    import win32api
    # http://timgolden.me.uk/pywin32-docs/win32api__SetSystemTime_meth.html
    # pywin32.SetSystemTime(year, month , dayOfWeek , day , hour , minute , second , millseconds )
    dayOfWeek = dto.isocalendar()[2]
    time = (time_tuple[:2] + (dayOfWeek-1,) + time_tuple[2:6]) + (int(str(time_tuple[6])[:3]),)

    win32api.SetSystemTime(*time)

  
def get_utctime():
    import ntplib
    x = ntplib.NTPClient()
    
    utctime = None
    
    for i in range(3):
        try:
            utctime = dt.utcfromtimestamp(x.request('europe.pool.ntp.org').tx_time)
            break
        except Exception as e:
            logging.exception(e)
            time.sleep(0.1)
            if i == 3: raise e
            
    return utctime


def _get_epoch():
    return _EPOCH


def pydt(timestamp=None, unit='s'):
    if unit not in ('s','ms'):
        raise ValueError(unit)
    
    if timestamp is None:
        return dt.utcnow()
    
    if unit == 'ms':
        timestamp = timestamp/1000
    
    return _EPOCH + td(seconds=timestamp)


def pydt_from_ms(timestamp):
    return pydt(timestamp, 'ms')


def timestamp(dto=None, round_to=3):
    if dto is None:
        return ctime()
    
    seconds = (dto-_EPOCH).total_seconds()
    
    if round_to is not None:
        seconds = round(seconds,round_to)
        
    return seconds


def timestamp_ms(dto=None):
    if dto is None:
        return ctime_ms()
    
    return int(timestamp(dto)*1000)


def ctime():
    return time.time()


def ctime_ms():
    return round(time.time()*1000)
    

_timestamp = timestamp

#################################################

if __name__ == '__main__':
    import pywin
    print(pywin.__file__)
    print(ctime_ms())
    """dttime = dt(2012,3,24,15,43,11,229245)
    print(dt_indexing(dttime,3))
    delta = td(microseconds=0)
    delta = td(days=366)
    delta = td(seconds=15)
    print(delta)
    print(dt_round(dttime,delta))
    strf = '%Y-%m-%dT%H-%M-%S'
    strf = '%m-%d-%YT%H-%M-%S-%f'
    print(dt_round_strf(strf, delta))
    input()"""

    print(dt_strp("2012-02-01T"))
    print(dt_strp("2012-02-01T23-11-05-02"))
    
    """try: _BUSINESSHOUR_FIXED = compare_versions(pd.__version__, _BusinessHour_Fixed_Version, '__ge__')
    except Exception: pass"""
