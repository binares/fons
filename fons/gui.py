import tkinter as tk
import tkinter.ttk as ttk

import fons.log as _log
from fons.threads import EliThread


class NbGUI:
    def __init__(self, config={}):
        self.root = tk.Tk()
        self.root.geometry('975x475')
        #self.root.resizable(0, 0)
        
        if config.get('title') is not None:
            self.root.title(config['title'])
        
        self.button_frame = bf = tk.Frame(self.root)
        bf.pack(side=tk.LEFT)
        
        self.nb = ttk.Notebook(self.root)
        #self.nb.grid(row=1, column=0, columnspan=50, rowspan=49, sticky='NESW')
        #self.nb.pack_propagate(0) 
        self.nb.pack(side=tk.LEFT, fill='both', expand=True)
    
        tabs = config.get('tabs')
        if tabs is None: tabs = []
        for tab in tabs:
            if isinstance(tab,str): tab = {'text': tab}
            _log.init_tab(self.nb,tab['text'])
            
        buttons = config.get('buttons')
        if buttons is None: buttons = {}
        for button,specs in buttons.items():
            callback = self.wrap_button(specs['command']) if specs.get('command') else None
            text = specs.get('text')
            b = tk.Button(bf, text=text, command=callback)
            b.pack()
            
    def wrap_button(self, f):
        def on_button(*args,**kw):
            tab_selected = self.nb.tab(self.nb.select(), 'text')
            return f(tab_selected,*args,**kw)
        return on_button
            

class TkThread(EliThread):
    def __init__(self, config, *args, **kw):
        #print('args:{},kwargs:{}'.format(args,kw))
        super().__init__(*args,**kw)
        self.config = config
        """if isinstance(config,NbGUI):
            self.gui = config
        else:
            self.gui = NbGUI(config)"""
        self.start()
        
    def run(self):
        self.gui = NbGUI(self.config)
        self.gui.root.mainloop()
