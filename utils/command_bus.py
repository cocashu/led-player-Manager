import queue

class CommandBus:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CommandBus, cls).__new__(cls)
            cls._instance.queue = queue.Queue()
        return cls._instance
        
    def send(self, command, data=None):
        self.queue.put({"command": command, "data": data})
        
    def get(self):
        if not self.queue.empty():
            return self.queue.get()
        return None
        
command_bus = CommandBus()
