from abc import ABC, abstractmethod


class BaseModule(ABC):
    """Every module in the system inherits from this.

    Modules communicate only through the MessageBus. They never import
    each other directly. The bus is the sole shared dependency.
    """

    module_name: str

    def __init__(self, bus: "MessageBus", config: dict):  # noqa: F821
        self.bus = bus
        self.config = config

    @abstractmethod
    async def setup(self) -> bool:
        """Initialize hardware, load models, validate config.

        Return True if ready, False if setup failed and module should
        be disabled.
        """
        ...

    @abstractmethod
    async def start(self) -> None:
        """Begin operation. Subscribe to bus topics, start loops."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown. Unsubscribe, close hardware, flush buffers."""
        ...

    @abstractmethod
    async def health(self) -> dict:
        """Return health status. Called periodically by bus.

        Returns:
            {"status": "ok"|"degraded"|"error", "details": {...}}
        """
        ...

    async def register(self) -> None:
        """Register with the bus. Called by main after successful setup()."""
        self.bus.register(self)
