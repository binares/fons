import sys, os, io
import traceback
import logging
from logging.handlers import QueueHandler


# this was added in 3.11
def _is_internal_frame(frame):
    """Signal whether the frame is a CPython or logging module internal."""
    filename = os.path.normcase(frame.f_code.co_filename)
    return filename in (logging._srcfile, getattr(logging, "_srcfile2")) or (  # EDITED
        "importlib" in filename and "_bootstrap" in filename
    )


class FonsLogger(logging.Logger):
    # _srcfile was moved to _is_internal_frame() in 3.11, no need to edit findCaller()
    # def findCaller(self, stack_info=False, stacklevel=1)

    # Compatibility with >= 3.12 unknown
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

    # Compatibility with >= 3.12 unknown
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
