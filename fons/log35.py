import sys, os, io
import traceback
import logging
from logging.handlers import QueueHandler


class FonsLogger(logging.Logger):
    # NB! findCaller() forwards incompatible with Python 3.8
    def findCaller(self, stack_info=False):
        """
        Find the stack frame of the caller so that we can note the source
        file name, line number and function name.
        """
        f = logging.currentframe()
        # On some versions of IronPython, currentframe() returns None if
        # IronPython isn't run with -X:Frames.
        if f is not None:
            f = f.f_back
        rv = "(unknown file)", 0, "(unknown function)", None
        while hasattr(f, "f_code"):
            co = f.f_code
            filename = os.path.normcase(co.co_filename)
            # added _srcfile2 (this file), so that .llog/.__call__
            # method would not show as caller
            if filename in (logging._srcfile, getattr(logging, "_srcfile2")):  # EDITED
                f = f.f_back
                continue
            sinfo = None
            if stack_info:
                sio = io.StringIO()
                sio.write("Stack (most recent call last):\n")
                traceback.print_stack(f, file=sio)
                sinfo = sio.getvalue()
                if sinfo[-1] == "\n":
                    sinfo = sinfo[:-1]
                sio.close()
            rv = (co.co_filename, f.f_lineno, co.co_name, sinfo)
            break
        return rv

    def handle(self, record, *args, declude_with_queues=[], **kw):  # EDITED
        """
        Call the handlers for the specified record.

        This method is used for unpickled records received from a socket, as
        well as those created locally. Logger-level filtering is applied.
        """
        # `declude_with_queues` is necessary for avoiding infinite recursion
        # in handling QueueHandler records (QueueHandler is used to connect
        # with child processes)
        if (not self.disabled) and self.filter(record):
            self.callHandlers(record, declude_with_queues=declude_with_queues)  # EDITED

    def callHandlers(self, record, *args, declude_with_queues=[], **kw):  # EDITED
        """
        Pass a record to all relevant handlers.

        Loop through all handlers for this logger and its parents in the
        logger hierarchy. If no handler was found, output a one-off error
        message to sys.stderr. Stop searching up the hierarchy whenever a
        logger with the "propagate" attribute set to zero is found - that
        will be the last logger whose handlers are called.
        """
        q_check = (
            lambda h: isinstance(h, QueueHandler) and h.queue in declude_with_queues
        )  # EDITED
        c = self
        found = 0
        while c:
            for hdlr in c.handlers:
                found = found + 1
                if q_check(hdlr):
                    pass  # EDITED
                elif record.levelno >= hdlr.level:
                    hdlr.handle(record)
            if not c.propagate:
                c = None  # break out
            else:
                c = c.parent
        if found == 0:
            if logging.lastResort:
                if q_check(logging.lastResort):
                    pass  # EDITED
                elif record.levelno >= logging.lastResort.level:
                    logging.lastResort.handle(record)
            elif logging.raiseExceptions and not self.manager.emittedNoHandlerWarning:
                sys.stderr.write(
                    "No handlers could be found for logger" ' "%s"\n' % self.name
                )
                self.manager.emittedNoHandlerWarning = True
