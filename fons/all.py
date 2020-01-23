"""
    This module is meant to be used as a convenient namespace.
"""

from fons import (__version__, __author__)

import fons.log as log
from fons.log import (setup_logging, standard_logging, get_standard_5, 
                      get_standard_logger, getFonsLogger, multi_module_logging,
                      quick_logging)

import fons.gui as gui
from fons.gui import (TkThread, NbGUI)

import fons.debug as _debug
from fons.debug import (debug, set_pm_hook, trylog, asyncTryLog, aTryLog, 
                        safeTry, safeAsyncTry, safeATry, wrap_trylog,
                        safewait)

import fons.aio as aio
import fons.event as event
import fons.host as host
import fons.processes as processes
import fons.reg as reg
import fons.sched as sched
import fons.threads as threads
from fons.aio import (call_via_loop, call_via_loop_afut, wrap_with_future, lrc)
from fons.event import (force_put, empty_queue, Station, QueueTransmitter, EventTransmitter,
                        Node, NodeHandler, RelayInfo, RelayPackage, NodeExit)
from fons.host import Server
from fons.processes import (LogiProcess, TkLogiProcess, pool_processes)
from fons.reg import create_name
from fons.sched import (Ticker, TickManager, AsyncTicker, AsyncTickManager,
                        BaseTicker, AsyncBaseTicker, ScheduleTicker, Routine)
from fons.threads import (EliThread, LoopingThread)

import fons.math as math
import fons.math.graph as graph
import fons.math.series as series
import fons.math.round as _round
from fons.math.round import (round_sd, ignore_half_round, round)
from fons.math.graph import (find_shortest_path, create_graph)

import fons.crypto as crypto
from fons.crypto import (nonce, nonce_ms, sign, password_encrypt, password_decrypt)

import fons.argv as argv
import fons.dict_ops as dict_ops
import fons.dtype as _dtype
import fons.dtype.dtype as dtype
import fons.dtype.merging as merging
import fons.dtype.store as store
import fons.iter as iter
import fons.verify as verify

from fons.argv import parse_argv
from fons.dtype.dtype import (DType, ShadowMerger)
from fons.iter import (flatten, flatten2, flatten_dict, fliter, is_flat, unique, consume,
                       sequence_insert)
from fons.dict_ops import (nt_to_od, od_to_nt, apply_until_get, deep_get, deep_update)
from fons.verify import (init_data, verify_data)

import fons.time as time
from fons.time import (dt_tuple, dt_indexing, dt_get, dt_assign, dt_round_to_digit,
                         dt_isround, dt_round, dt_round2, dt_round_freq, dt_synced,
                         _dt_round_bh, freq_to_td, freq_to_str, freq_to_offset,
                         dt_round_strf, dt_strp, _set_win_time, get_utctime,
                         _get_epoch, pydt, pydt_from_ms, timestamp, timestamp_ms,
                         ctime, ctime_ms, DT_FIELDS, TD_FIELDS, _FREQS, _EPOCH)

import fons.io as io
from fons.io import (DateTimeEncoder, DateTimeEncoderNumeric, 
                     get_params, read_params, save_params,
                     wait_filelock, SafeFileLock, update_settings, _META_NORM as META_NORM)
import fons.os as os
from fons.os import (search, search_in_file, delete_empty_dirs, make_dirpath, zip_contents)


import fons.net as net
import fons.net.url as url
import fons.net.urlstr as urlstr
from fons.net import (fetch, init_session, get_session, close_sessions)


from fons.func import (limitcalls, limitcalls_f, limitcalls_m,
                       async_limitcalls, async_limitcalls_f, async_limitcalls_m,
                       get_arg_count)

import fons.py as py
from fons.py import (mro, rreload)

import fons.pyops as pyops
from fons.pyops import exec_op

import fons.errors as e

logger,logger2,tlogger,tloggers,tlogger0 = log.get_standard_5(__name__)