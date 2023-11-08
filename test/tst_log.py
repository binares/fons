import os, sys
import tkinter as tk
import tkinter.ttk as ttk
import time
import logging

import fons.log as log
from fons.processes import LogiProcess, TkLogiProcess

logger, logger2, tlogger, tloggers, tlogger0 = log.get_standard_5(__name__)


def target1_sub_sub():
    logger.info("from target1_sub_sub")
    while True:
        logger.info("target1_sub_sub - This should NOT show")
        logger2.info("target1_sub_sub - from logger2")
        tloggers.info("target1_sub_sub - This should ALSO NOT show")
        print("target1_sub_sub - Printed sentence")
        time.sleep(80)


def target1_sub():
    logger.info("from target1_sub")
    p = LogiProcess(target=target1_sub_sub, name="target1_sub_sub-Process")
    p.start()
    while True:
        logger.info("target1_sub - This should NOT show")
        logger2.info("target1_sub - from logger2")
        tloggers.info("target1_sub - This should ALSO NOT show")
        print("target1_sub - Printed sentence")
        time.sleep(40)


def target1():
    log.standard_logging(os.path.dirname(__file__), f_ending="target1")
    logger.info("from target1")
    p = LogiProcess(target=target1_sub, name="target1_sub-Process")
    p.start()
    while True:
        logger.info("target1 - This should NOT show")
        logger2.info("target1 - from logger2")
        tloggers.info("target1 - This should ALSO NOT show")
        print("target1 - Printed sentence")
        time.sleep(20)


def target2():
    log.standard_logging(os.path.dirname(__file__), f_ending="target2")
    logger.info("from target2")
    print("target2", logging.root.handlers)
    print("target2", logger.handlers)
    print("target2", logger2.handlers)
    print("target2", sys.stdout)
    while True:
        logger.info("target2 - This should NOT show")
        logger2.info("target2 - from logger2")
        tloggers.info("target2 - This should ALSO NOT show")
        print("target2 - Printed sentence")
        time.sleep(20)


def target3_sub():
    logger.info("from target3_sub")
    while True:
        logger.info("target3_sub - This should NOT show")
        logger2.info("target3_sub - from logger2")
        tloggers.info("target3_sub - This should ALSO NOT show")
        print("target3_sub - Printed sentence")
        time.sleep(40)


def target3():
    logger.info("from target3")
    p = LogiProcess(target=target3_sub, name="target3_sub-Process")
    p.start()
    while True:
        logger.info("target3 - This should NOT show")
        logger2.info("target3 - from logger2")
        tloggers.info("target3 - This should ALSO NOT show")
        print("target3 - Printed sentence")
        time.sleep(20)


def test_logging():
    root = tk.Tk()
    root.geometry("975x475")  # 415")
    # root.resizable(0, 0)

    nb = ttk.Notebook(root)  # , width=800, height=500)
    # nb.pack_propagate(0)
    # nb.grid(row=1, column=0, sticky='NESW') #columnspan=50, rowspan=49,
    nb.pack(fill="both", expand=True)

    """def resize(event):
        w,h = event.width-100, event.height-100
        nb.config(width=w, height=h)
    nb.bind('<Configure>', resize)"""
    log.init_tab(nb, "info*")
    # log.init_tab(nb,'*')
    log.init_main_tab(nb)

    p1 = TkLogiProcess(nb, target=target1, name="Window1")
    p2 = TkLogiProcess(nb, target=target2, name="Window2")
    p3 = LogiProcess(target=target3, name="target3-Process")

    log.standard_logging(os.path.dirname(__file__), f_ending="main")
    p1.start()
    p2.start()
    p3.start()
    time.sleep(1)

    logger2.info("FROM MAIN")
    logger.debug("FROM MAIN")
    root.mainloop()


if __name__ == "__main__":
    test_logging()
