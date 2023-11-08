import inspect

from fons.errors import ServerError
import fons.log as _log
from fons.reg import create_name
from fons.threads import EliThread
from fons.verify import verify_data

logger, logger2, tlogger, tloggers, tlogger0 = _log.get_standard_5(__name__)

_SERVER_NAMES = set()


class Server(EliThread):
    def __init__(
        self,
        conn,
        on_success=None,
        on_exit=None,
        exit_cmd=None,
        verify=None,
        *,
        wait=1,
        name=None,
        log_error=True,
        **kw
    ):
        super().__init__(**kw)
        self.conn = conn
        self.verify = verify
        self.wait = wait
        self._log_error = log_error

        self._on_success = on_success
        self._on_exit = on_exit
        self._exit_cmd = (lambda x: False) if exit_cmd is None else exit_cmd

        if name is None and hasattr(self.__class__, "_name"):
            name = self.__class__._name
        self._name = create_name(
            name, default=self.__class__.__name__, registry=_SERVER_NAMES
        )
        self._closed = False

    def run(self):
        try:
            while not self._closed:
                if self.conn.poll(self.wait):
                    r = self.conn.recv()
                    if self._exit_cmd(r):
                        logger.debug("{} - received exit command.".format(self.name))
                        self.close()
                        break
                    self.handle(r)
        finally:
            logger.debug("Closing {}".format(self.name))
            self.on_exit()

    def handle(self, inp):
        error_msg = self.verify_input(inp)
        if error_msg:
            self.send_error(error_msg)
        else:
            try:
                self.on_success(inp)
            except ServerError as e:
                self.send_error(e.msg)
            except Exception as e:
                logger.exception(e)
                self.send_error(str(e))

    def send(self, data, ok=True, msg=None):
        self.conn.send({"ok": ok, "msg": msg, "data": data})

    def send_error(self, msg):
        if self._log_error:
            logger.error(msg)
        self.send({}, ok=False, msg=msg)

    def on_success(self, inp):
        self._on_success(inp)

    def on_exit(self):
        if self._on_exit is not None:
            fas = inspect.getfullargspec(self._on_exit)
            ismethod = inspect.ismethod(
                self._on_exit
            )  # note: ismethod returns True for classmethods also
            args = (
                (self.conn,)
                if len(fas.args[(1 if ismethod else 0) :]) or fas.varargs
                else tuple()
            )
            self._on_exit(*args)
        else:
            self.conn.send(None)

    def verify_input(self, inp):
        if self.verify is not None:
            try:
                verify_data(inp, self.verify)
            except Exception as e:
                return "Incorrect input: {}".format(e)

    def close(self):
        self._closed = True

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    _name = None
