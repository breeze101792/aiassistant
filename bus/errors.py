class BusError(Exception):
    """Base error for all bus-related failures."""
    pass


class NoSubscriberError(BusError):
    """No module is subscribed to the requested topic."""

    def __init__(self, topic: str):
        self.topic = topic
        super().__init__(f"No subscriber for topic: {topic}")


class TimeoutError(BusError):
    """RPC request timed out waiting for a response."""

    def __init__(self, topic: str, timeout: float):
        self.topic = topic
        self.timeout = timeout
        super().__init__(f"RPC request to '{topic}' timed out after {timeout}s")


class ModuleNotFoundError(BusError):
    """Referenced module is not registered."""

    def __init__(self, module_name: str):
        self.module_name = module_name
        super().__init__(f"Module not found: {module_name}")
