import datetime

dt = datetime.datetime
import time
import sys, os, io
from collections import namedtuple
import traceback
import threading
import multiprocessing
import warnings
import yaml
import platform
import logging
from logging.handlers import RotatingFileHandler, QueueHandler

OldLoggingFormatter = logging.Formatter

if sys.version_info[1] < 8:
    from .log35 import FonsLogger
elif sys.version_info[1] < 11:
    from .log38 import FonsLogger
else:
    from .log311 import FonsLogger


class EmptyLogger:
    def debug(self, msg, *args, **kwargs):
        pass

    def info(self, msg, *args, **kwargs):
        pass

    def warn(self, msg, *args, **kwargs):
        pass

    def warning(self, msg, *args, **kwargs):
        pass

    def error(self, msg, *args, **kwargs):
        pass

    def exception(self, msg, *args, exc_info=True, **kwargs):
        pass

    def critical(self, msg, *args, **kwargs):
        pass

    def log(self, level, msg, *args, **kwargs):
        pass


SETTINGS_PATH = os.path.abspath(
    os.path.join(os.path.join(__file__, ".."), "settings.yaml")
)


def _read_settings():
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f)
    else:
        return {}


def _save_settings(d, mode="a"):
    if mode not in ("a", "w"):
        raise ValueError(mode)
    d_prev = {}
    if mode == "a":
        d_prev = _read_settings()
    d_prev.update(d)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        yaml.dump(d_prev, f)


def _read_root_dir():
    root_dir = ""
    d = _read_settings()
    if d.get("logging_default_root_dir") is not None:
        root_dir = d["logging_default_root_dir"]
        if platform.system() != "Windows":
            root_dir = os.path.expanduser(root_dir)
    if not isinstance(root_dir, str):
        raise TypeError(
            "Logging root dir in settings file must be of type <str>, got: {}".format(
                type(root_dir)
            )
        )
    return root_dir


def set_default_root_dir(path, make_permanent=False):
    """
    Set the default directory where file handlers will output their files
    (=='dir' param in functions 'standard_logging' and 'setup_logging').
    :param make_permanent:
        if True, writes to settings file (will keep defaulting to that during
        the future python instances)
    """
    global DEFAULT_ROOT_DIR
    if not isinstance(path, str):
        raise TypeError(type(path))
    DEFAULT_ROOT_DIR = path
    if make_permanent:
        _save_settings({"logging_default_root_dir": path}, "a")


# '' will later resolve to current working directory
DEFAULT_ROOT_DIR = _read_root_dir()

logging._srcfile2 = os.path.normcase(FonsLogger.findCaller.__code__.co_filename)

# For excluding this module from Logger's record (like logging module does)
# and fixing infinite recursion caused by LogListener trying to handle
# QueueHandler's record (this won't affect user defined QueueHandlers)
logging.Logger.findCaller = FonsLogger.findCaller
logging.Logger.handle = FonsLogger.handle
logging.Logger.callHandlers = FonsLogger.callHandlers

# This was necessary for something. For making compatible with new Logger methods?
_rhandlers, _rfilters = logging.root.handlers, logging.root.filters
logging.root = logging.RootLogger(logging.root.level)
logging.root.handlers = _rhandlers
logging.root.filters = _rfilters

NR_CONSOLE_LINES = 300
STREAMING_LOGGERS = ["L2", "T2"]

_is_logger_overwritten = False
_default_fmt = (
    "%(asctime)s:%(levelname)s:%(name)s:%(module)s:%(funcName)s(%(lineno)d):%(message)s"
)
_queue = multiprocessing.Queue(-1)
_lock = multiprocessing.Lock()
_globals = {
    "queue": _queue,
    "TEST_MODE": False,
    "level": "INFO",
    "fmt": None,
    "use_FonsFormatter": True,
}

_modules = [__name__]
_tklogiprocesses = {}
_sys_stdout_assigned = False
_mp_logging_enabled = False
_listener = None

_s5_names = {
    "logger": "L1",
    "logger2": "L2",
    "tlogger": "T1",
    "tloggers": "T2",
    "tlogger0": "T0",
}
_Standard_5 = namedtuple(
    "StandardLogging_5", "logger logger2 tlogger tloggers tlogger0"
)
_Standard_5.__new__.__defaults__ = tuple(
    logging.getLogger(_s5_names[x]) for x in _Standard_5._fields
)

standard_5 = _Standard_5()

# The difference between logger and logger2 (and tlogger / tloggers) is that after calling setup_logging(),
# logger2 (and tloggers) will *also* stream to console, while logger (and tlogger, tlogger0) only stream to file
logger = standard_5.logger
logger2 = standard_5.logger2
tlogger = standard_5.tlogger
tloggers = standard_5.tloggers
tlogger0 = standard_5.tlogger0


for _logger in standard_5[:2]:
    _logger.setLevel(10)
# Set test loggers' level to 0
for _logger in standard_5[2:]:
    _logger.setLevel(0)


class TempStreamHandler(logging.StreamHandler):
    """
    Only stream if root has not handlers set (to avoid duplication)
    """

    def handle(self, record):
        if not logging.root.handlers and not _mp_logging_enabled:
            return logging.StreamHandler.handle(self, record)


# We want the logger and logger2 to stream only if user has not called basicConfig(),
# and revoke the streaming when user decides to call it later
if not logging.root.handlers and not _mp_logging_enabled:
    _h = TempStreamHandler()
    _h.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    logger.addHandler(_h)
    logger2.addHandler(_h)


# ----------------------------------------------


class FonsFormatter(logging.Formatter):
    converter = dt.utcfromtimestamp

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            t = ct.strftime("%Y-%m-%dT%H:%M:%S")
            s = "%s.%03d" % (t, record.msecs)

        return s


class FonsFormatter2(logging.Formatter):
    converter = time.gmtime
    default_time_format = "%Y-%m-%d %H:%M:%S"
    defualt_msec_format = "%s.%03d"


def initiate_FonsFormat():
    logging.Formatter = FonsFormatter


# -------------------------------------------


def getFonsLogger(
    name=None, lvl="DEBUG", streams=True, fmt=None, use_FonsFormatter=True
):
    if name is None:
        name = __name__
    logger = logging.getLogger(name)
    logger.setLevel(lvl)

    if fmt is None:
        fmt = "%(asctime)s:%(levelname)s:%(name)s:%(funcName)s: %(message)s"
    elif fmt == "simpleformat":
        fmt = "%(asctime)s %(message)s"

    remove_stream_handlers(logger)

    if streams:
        console = logging.StreamHandler()
        aFormatter = FonsFormatter if use_FonsFormatter else OldLoggingFormatter

        formatter = aFormatter(fmt=fmt)
        console.setFormatter(formatter)

        logger.addHandler(console)

    """if queue is not None:
        logger.addHandler(QueueHandler(queue))"""

    return logger


class Tee(object):
    def __init__(self, files=[], lvl=logging.INFO, logger=None):
        self.files = files

        if logger is None:
            self.logger = getFonsLogger(
                "stdout",
                streams=False,
                fmt=_globals["fmt"],
                use_FonsFormatter=_globals["use_FonsFormatter"],
            )
        else:
            self.logger = logger

        self.lvl = level_to_int(lvl)

    def write(self, obj):
        for f in self.files:
            f.write(obj)
        self.logger.log(self.lvl, obj)

    def flush(self):
        pass


class TKConsoleHandler(logging.Handler):
    # This class allows you to log to a Tkinter Text or ScrolledText widget
    # Adapted from Moshe Kaplan: https://gist.github.com/moshekaplan/c425f861de7bbf28ef06

    def __init__(self, text):
        import tkinter as tk

        logging.Handler.__init__(self)
        self.setFormatter(FonsFormatter(_default_fmt))
        self.text = text
        self._tk = tk

    def emit(self, record):
        msg = self.format(record)

        def append():
            self.text.configure(state="normal")
            self.text.insert(self._tk.END, msg + "\n")
            self.text.configure(state="disabled")
            # Autoscroll to the bottom
            self.text.yview(self._tk.END)

        # This is necessary because we can't modify the Text from other threads
        self.text.after(0, append)

        if self.num_lines() > NR_CONSOLE_LINES:
            self.clear_log()

    def num_lines(self):
        return int(self.text.index("end").split(".")[0]) - 1

    def clear_log(self):
        self.text.configure(state="normal")
        self.text.delete(1.0, 2.0)  # tk.END)
        self.text.configure(state="disabled")


def _create_logiGUI_class():
    import tkinter as tk

    class LogiGUI(tk.Frame):
        def __init__(self, parent, *args, loggers=[], **kwargs):
            tk.Frame.__init__(self, parent, *args, **kwargs)
            self.root = parent
            if loggers is None:
                loggers = []
            elif isinstance(loggers, str):
                loggers = [loggers]
            self.loggers = loggers
            self.build_gui()

        def build_gui(self):
            from tkinter.scrolledtext import ScrolledText

            # Build GUI
            # self.root.title(self.l_name)
            self.root.option_add("*tearOff", "FALSE")
            self.grid(column=0, row=0, sticky="nesw")
            self.grid_columnconfigure(0, weight=1, uniform="a")
            self.grid_columnconfigure(1, weight=1, uniform="a")
            self.grid_columnconfigure(2, weight=1, uniform="a")
            self.grid_columnconfigure(3, weight=1, uniform="a")

            # Add text widget to display logging info
            st = ScrolledText(self, state="disabled")
            st.configure(font="TkFixedFont")
            # .grid didn't expand vertically for some reason
            # st.grid(column=0, row=1, sticky='nesw', columnspan=4)
            st.pack(fill="both", expand=True)

            # Create textLogger
            self.text_handler = TKConsoleHandler(st)

            # Add the handler to logger
            for l in self.loggers:
                logger = l if isinstance(l, logging.Logger) else logging.getLogger(l)
                logger.addHandler(self.text_handler)

    return LogiGUI


class LogListener(threading.Thread):
    def __init__(self, queue):
        super().__init__(name="LogListener", daemon=True)
        self.queue = queue

    def run(self):
        logger.info(
            "Starting LogListener in '{}'".format(
                multiprocessing.current_process().name
            )
        )
        while True:
            try:
                record = self.queue.get()
                if (
                    record is None
                ):  # We send this as a sentinel to tell the listener to quit.
                    break
                self.handle(record)
            except Exception:
                print("Whoops! Problem:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)

    def handle(self, record):
        p_name = multiprocessing.current_process().name
        if not hasattr(record, "p_history"):
            record.p_history = [record.processName]

        # ordinary child process (non_tkLogiProcess) of main
        record_is_main = record.processName == "MainProcess"
        isin_tk0 = record.p_history[0] in _tklogiprocesses

        # if we are not in main process or this is non-tk process, we want to record its name
        if (
            p_name != "MainProcess" or record.p_history[0] not in _tklogiprocesses
        ) and record.p_history[0] != p_name:
            # if (p_name != 'MainProcess') and p_name not in record.p_history:
            record.p_history.insert(0, p_name)

        isin_tk = record.p_history[0] in _tklogiprocesses
        """if not isinstance(logging.root.handlers[0],QueueHandler):
            print('Received from: {}, Handling: "{}"'.format(record.processName,record.message))#logging.root.handlers[0].format(record)))"""

        display = (
            record.name in STREAMING_LOGGERS
            or record.name == "stdout"
            or p_name == record.processName
            and any(
                isinstance(x, logging.StreamHandler)
                for x in logging.getLogger(record.name).handlers
            )
        )

        if isin_tk and display:
            gui_handler = _tklogiprocesses[record.p_history[0]].text_handler
            gui_handler.emit(record)
        # we do not want to cause recursive loop
        # (if _tklogiprocesses is inited, the logging.root.handlers may contain self.queue
        #   [due to 'main' process also having gui notebook], but any other "not-TkLogiProcess" is *not* registered into
        #  the _tklogiprocesses, with the elif check removed causing infinite recursion;
        # --although any-non_tklogiprocess will have "MainProcess" as record.p_history[0], which should also ensure eliminate recursion,
        # -- thus the below is just as a precaution for unforeseen situations (when _gui is located in a child process?))

        if not record_is_main and not isin_tk0:
            _logger = logging.getLogger(record.name)
            # add [self.queue] to eliminate possibility of recursion
            _logger.handle(record, declude_with_queues=[self.queue])

        """if '*' in _tklogiprocesses and display:
            _tklogiprocesses['*'].text_handler.emit(record)"""
        for i, lname in enumerate(
            ("debug*", "info*", "warning*", "error*", "critical*")
        ):
            if record.levelno < (i + 1) * 10:
                break
            elif lname in _tklogiprocesses:
                _tklogiprocesses[lname].text_handler.emit(record)


def start_listener():
    global _listener
    with _lock:
        if _globals["queue"] is None:
            warnings.warn("u_log._queue is set to `None`. Cannot start LogListener.")
        if _listener is None:
            _listener = LogListener(_globals["queue"])
            _listener.start()


def init_tab(nb, processName):
    """:type nb: tkinter.ttk.Notebook"""
    LogiGUI = _create_logiGUI_class()
    fr = LogiGUI(nb)
    _tklogiprocesses[processName] = fr
    if _globals["queue"] is None:
        pass
    elif processName == "MainProcess" and not any(
        isinstance(x, QueueHandler) and x.queue is _globals["queue"]
        for x in logging.root.handlers
    ):
        logging.root.addHandler(QueueHandler(_globals["queue"]))
    text = processName if processName != "MainProcess" else "main"
    nb.add(fr, text=text)
    # in case it hasn't been started yet
    start_listener()


def init_main_tab(nb):
    """:type nb: tkinter.ttk.Notebook"""
    init_tab(nb, "MainProcess")


def remove_stream_handlers(logger):
    for h in logger.handlers[:]:
        # FileHandler is subclass of StreamHandler, but here we mean handlers streaming to console
        if isinstance(h, logging.StreamHandler) and not isinstance(
            h, logging.FileHandler
        ):
            logger.handlers.remove(h)


def level_to_int(lvl):
    return lvl if isinstance(lvl, int) else getattr(logging, lvl.upper())
    # raise TypeError('Level must be either of type <str> or <int>, got {}'.format(type(lvl)))


# --------------------------------------------


def multi_module_logging(modules, names, loggers):
    for mod in modules:
        if isinstance(mod, str):
            mod = sys.modules[mod]

        for name, logger in zip(names, loggers):
            if not isinstance(mod, dict):
                setattr(mod, name, logger)
            else:
                mod.update({name: logger})


def standard_logging(dir=None, f_ending=None, TEST_MODE=False, modules=None, **kw):
    """A standardized logging to file"""
    global _sys_stdout_assigned
    backup = sys.stdout
    if dir is None:
        dpath = kw.get("dpath")
        if dpath is None:
            dir = DEFAULT_ROOT_DIR
        else:
            dir = os.path.join(dpath, "logs", "other")
        if TEST_MODE:
            dir += "_TM"
        os.makedirs(dir, exist_ok=True)

    if TEST_MODE and isinstance(f_ending, str) and not f_ending.endswith("_TM"):
        f_ending += "_TM"

    params = {
        "dir": dir,
        "lvl": "DEBUG",
        "use_FonsFormatter": True,
        "pair_with_fwriters": [sys.stdout],
        "f_ending": f_ending,
        "lvl_handlers": ["WARNING", {"lvl": "INFO", "use_rotating": True}],
        "use_rotating": True,
        "maxBytes": 5 * 1024 * 1024,
        "backupCount": 5,
    }

    params.update({k: v for k, v in kw.items() if k in params})

    # --
    writer = setup_logging(**params)
    # --

    if _sys_stdout_assigned:
        pass
    elif any(x in params["pair_with_fwriters"] for x in ("sys.stdout", sys.stdout)):
        sys.stdout = writer
        _sys_stdout_assigned = True

    standard_5 = _init_standard_5(TEST_MODE)

    if modules is not None:
        for mod in modules:
            add_module(mod)

    multi_module_logging(_modules, standard_5._fields, standard_5)

    _globals.update(
        {
            #'queue': queue,
            "TEST_MODE": TEST_MODE,
            "level": params["lvl"],
            "use_FonsFormatter": params["use_FonsFormatter"],
            "fmt": kw.get("fmt"),
        }
    )

    return standard_5


def quick_logging(test=2, add_stream_handlers=False):
    if add_stream_handlers:
        remove_stream_handlers(logging.root)  # to avoid duplicate streaming
    else:
        for _logger in standard_5:
            remove_stream_handlers(_logger)
        logging.basicConfig(level=10)  # stream via root handler

    for i, _logger in enumerate(standard_5):
        level = 10 if i < (2 + test) else 0
        getFonsLogger(_logger.name, level, add_stream_handlers)


def standard_mp_logging(
    queue, level="INFO", fmt=None, use_FonsFormatter=True, TEST_MODE=False
):
    global _sys_stdout_assigned, _mp_logging_enabled
    _mp_logging_enabled = True

    if fmt is None:
        fmt = _default_fmt
    if use_FonsFormatter:
        logging.Formatter = FonsFormatter

    try:
        _modules[_modules.index("__main__")] = "__mp_main__"
    except ValueError:
        pass

    standard_5 = _init_standard_5(TEST_MODE, False)
    """print('standard_mp_logging')
    print(_modules)
    print([m in sys.modules for m in _modules])
    print(list(sys.modules)[:20])"""
    multi_module_logging(_modules, standard_5._fields, standard_5)

    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)

    logging.basicConfig(level=level, handlers=[QueueHandler(queue)], format=fmt)
    # print('_queue is queue: {}'.format(_queue is queue))
    _sys_stdout_assigned = True
    # let's remove sys.stdout altogether (since parent process will print the 'stdout' logger output anyway)
    sys.stdout = Tee([])  # sys.stdout
    """print(sys.modules['__mp_main__'].logger2,sys.modules['__mp_main__'].logger2.name)"""


def get_standard_logger(name=None):
    if name is None:
        return standard_5[0]

    elif isinstance(name, int):
        return standard_5[name]

    return getattr(standard_5, name)


def get_standard_5(module=None):
    if module is not None:
        add_module(module)

    return standard_5


def add_module(module):
    if module not in _modules:
        _modules.append(module)


def _init_standard_5(TEST_MODE, stream_enabled=None):
    if stream_enabled is None:
        stream_enabled = not _mp_logging_enabled
    logger = getFonsLogger("L1", streams=False)
    logger2 = getFonsLogger("L2", streams=stream_enabled)

    tlogger = getFonsLogger("T1", streams=False)  # logger
    tloggers = getFonsLogger("T2", streams=stream_enabled)  # logger2
    tlogger0 = getFonsLogger("T0", 0, streams=False)

    if not TEST_MODE:
        [x.setLevel(0) for x in (tlogger, tloggers, tlogger0)]

    global standard_5
    standard_5 = _Standard_5(logger, logger2, tlogger, tloggers, tlogger0)

    return standard_5


# --------------------------------------------


def setup_logging(
    dir=None,
    lvl="INFO",
    pair_with_fwriters=[],
    fname=None,
    f_ending=None,
    lvl_handlers=[],
    use_rotating=True,
    maxBytes=5 * 1024 * 1024,
    filemode="a",
    backupCount=2,
    fmt=None,
    use_FonsFormatter=True,
):
    """Attaches file handlers to root logger"""
    if dir is None:
        dir = ""

    if not fname:
        fname = dt.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    if f_ending:
        fname += "_" + f_ending

    if dir is not False:
        dir = os.path.join(dir, fname)
        if not os.path.exists(dir):
            os.mkdir(dir)

    if not fname.endswith(".log"):
        fname += ".log"

    if use_FonsFormatter:
        logging.Formatter = FonsFormatter

    if not fmt:
        fmt = _default_fmt

    lvl_handlers = lvl_handlers[:]

    if not any(
        isinstance(L, dict)
        and level_to_int(L.get("lvl", L.get("level"))) == level_to_int(lvl)
        or not isinstance(L, dict)
        and level_to_int(L) == level_to_int(lvl)
        for L in lvl_handlers
    ):
        lvl_handlers.append(lvl)

    # Removes all previous handlers
    # (e.g. if logging.log() called before setup_logging,
    #  it automatically adds StreamHandler, and basicConfig(handlers=handlers) won't add the new handlers)
    keep_handlers = [x for x in logging.root.handlers if isinstance(x, QueueHandler)]
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    handlers = []

    for L in lvl_handlers:
        if dir is False:
            break
        if not isinstance(L, dict):
            L = {"lvl": L}

        h_lvl = L.get("lvl", L.get("level"))
        if isinstance(h_lvl, str):
            h_lvl = h_lvl.upper()

        # h_rotating = L.get('use_rotating',[True,False][level_to_int(h_lvl) > 30])
        h_filemode = L.get("filemode", filemode)
        h_backupCount = L.get("backupCount", backupCount)
        h_max_size = L.get("maxBytes", maxBytes)

        fpth = os.path.join(dir, fname[:-4] + "_{}.log".format(h_lvl))
        if use_rotating:
            h = RotatingFileHandler(
                fpth,
                mode=h_filemode,
                maxBytes=h_max_size,
                backupCount=h_backupCount,
                encoding="utf-8",
                delay=0,
            )
        else:
            h = logging.FileHandler(fpth, mode=h_filemode)
        h.setLevel(h_lvl)

        handlers.append(h)

    handlers += keep_handlers

    logging.basicConfig(  # filename=fpath,
        format=fmt,
        # filemode=filemode,
        handlers=handlers,
        level=level_to_int(lvl),
    )  # ,\
    # datefmt = '%Y-%m-%dT%H:%M:%S')

    if len(pair_with_fwriters):
        synched_writer = Tee(pair_with_fwriters, lvl, logging)
        return synched_writer


if __name__ == "__main__":
    logger.debug("first output (from L1)")
    logdir = os.path.join("_test")
    backup = sys.stdout
    # Strange discovery:
    #  if logging.log used before initiating handlers, handlers will be void
    #  (everything is directed to logging module instead of handler)
    # Don't do:
    print("Handlers 0: {}".format(logging.root.handlers))  # []
    logging.warning("HERE (from root)")
    print(
        "Handlers now: {}".format(logging.root.handlers)
    )  # [<StreamHandler <stderr> (NOTSET)>]
    logger.debug("HERE (from L1)")
    logging2, sys.stdout = setup_logging(
        logdir,
        lvl="INFO",
        # lvl_handlers =  [{'lvl':'INFO','maxBytes':0.5*1024*1024},{'lvl':'WARNING','use_rotating':True},'CRITICAL'],
        use_rotating=True,
        use_FonsFormatter=True,
        pair_with_fwriters=[sys.stdout],
        f_ending="main",
        filemode="a",
        maxBytes=5242880,
        backupCount=5,
    )

    print("Handlers after setup: {}".format(logging2.root.handlers))

    logger = getFonsLogger("L1", streams=False)
    logger2 = getFonsLogger("L2", streams=True)
    logger.info("LOGGER!")
    logger2.info("LOGGER2!")

    print("Handlers final: {}".format(logging.root.handlers))
