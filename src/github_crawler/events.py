from enum import Enum, auto
from typing import Callable, Dict, List, Any

class EventType(Enum):
    # Synthesis events
    SYNTHESIS_STARTED = auto()
    SYNTHESIS_FINISHED = auto()
    
    # Search events
    SEARCH_STARTED = auto()
    SEARCH_SUCCESS = auto()
    SEARCH_ERROR = auto()
    
    # Processing events
    PROCESSING_STARTED = auto()
    PROCESSING_FINISHED = auto()
    REPO_START = auto()
    REPO_SUCCESS = auto()
    REPO_ERROR = auto()
    
    # General
    ERROR = auto()
    LOG = auto()

class EventBus:
    def __init__(self):
        self._listeners: Dict[EventType, List[Callable]] = {etype: [] for etype in EventType}

    def subscribe(self, event_type: EventType, listener: Callable):
        self._listeners[event_type].append(listener)

    def emit(self, event_type: EventType, data: Any = None):
        for listener in self._listeners[event_type]:
            listener(data)

# Global event bus
event_bus = EventBus()
