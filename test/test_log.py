"""
ERRORS
With pytest only:
 - for some reason not any logger is logging anything (but do log with `python3 test/test_log.py`)
   (with basicConfig() or not)
   UNLESS we add StreamHandler() to them
"""

import logging

# Logger meant for this module
py_logger = logging.getLogger("py_logging")
print("parent:", py_logger.parent)  # <RootLogger root (WARNING)>
# py_logger.setLevel(10)


def log(logger=py_logger):
    print(logger.name)
    logger.debug("This is a debug msg")
    logger.info("This is info msg")
    logger.warning("This is a warning")
    print("-------------")


# logging.lastResort = None
log()
# >>> No handlers could be found for logger "py_logging"

# This doesn't affect the level of other loggers
if 1:
    print("Setting basicConfig(level=DEBUG)...")
    logging.basicConfig(level=logging.DEBUG)
# Without configuring:
#         ( https://docs.python.org/3.8/howto/logging.html#what-happens-if-no-configuration-is-provided )
#  - only >=WARNING is logged
#  - no format (acts like print(), without logger's metadata)
# After configuring:
#  - all loggers (that have not specified its own level) log DEBUG as well
log()
print("ADDING HANDLER")
# Duplicates the output only if basicConfig() is called, as propagate=True and root is everyone's parent
py_logger.addHandler(logging.StreamHandler())
log()
py_logger_after = logging.getLogger("py_logging_initiated_after_basicConfic")
log(py_logger_after)

print("...................")
print("IMPORTING fons.log")
from fons.log import logger, tlogger, quick_logging

# Verify that the old logger's root has been updated
assert logging.root == logging.Logger.root
assert py_logger.root == logging.Logger.root
assert py_logger.manager.root == logging.Logger.root
print(logging.root)

# Prints everything
log(logger)
# Only prints >=WARNING
log(tlogger)


print("=====================================")
print("quick_logging()")
quick_logging()
log()
log(logger)
# Now test logger outputs everything
log(tlogger)


def test_log():
    print("=====================================")
    print("test_log()")
    log()
    log(logger)
    log(tlogger)
    print("................\nSetting basicConfig(level=DEBUG)...")
    logging.basicConfig(level=logging.DEBUG)
    log()
    log(logger)
    log(tlogger)
