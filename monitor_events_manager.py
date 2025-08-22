"""
Event system for communication between RealTimeAvailabilityMonitor and TelegramBot.
Provides thread-safe message passing and event serialization.
"""

import json
import queue
import threading
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict


class EventType(Enum):
    """Types of events that can be emitted by the monitor."""
    ERROR = "error"
    SLOT_FOUND = "slot_found"
    REGISTRATION_SUCCESS = "registration_success"
    REGISTRATION_FAILED = "registration_failed"
    STATUS_UPDATE = "status_update"
    MONITOR_STARTED = "monitor_started"
    MONITOR_STOPPED = "monitor_stopped"
    DATABASE_UPDATE = "database_update"


@dataclass
class MonitorEvent:
    """Event emitted by the monitor."""
    event_type: EventType
    timestamp: datetime
    data: Dict[str, Any]
    message: str
    priority: int = 1  # 1=low, 2=medium, 3=high, 4=critical
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data,
            'message': self.message,
            'priority': self.priority
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MonitorEvent':
        """Create event from dictionary."""
        return cls(
            event_type=EventType(data['event_type']),
            timestamp=datetime.fromisoformat(data['timestamp']),
            data=data['data'],
            message=data['message'],
            priority=data['priority']
        )


class EventQueue:
    """Thread-safe event queue for monitor-bot communication."""
    
    def __init__(self, maxsize: int = 1000):
        self._queue = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self._subscribers = []
        self._stats = {
            'events_sent': 0,
            'events_received': 0,
            'queue_size': 0,
            'last_event_time': None
        }
    
    def emit(self, event: MonitorEvent) -> bool:
        """
        Emit an event to the queue.
        
        Args:
            event: MonitorEvent to emit
            
        Returns:
            bool: True if event was queued successfully
        """
        with self._lock:
            try:
                self._queue.put_nowait(event)
                self._stats['events_sent'] += 1
                self._stats['queue_size'] = self._queue.qsize()
                self._stats['last_event_time'] = datetime.now()
                return True
            except queue.Full:
                # Drop oldest event and add new one for critical events
                if event.priority >= 3:
                    try:
                        self._queue.get_nowait()  # Remove oldest
                        self._queue.put_nowait(event)
                        return True
                    except queue.Empty:
                        pass
                return False
    
    def get_event(self, timeout: Optional[float] = None) -> Optional[MonitorEvent]:
        """
        Get next event from queue.
        
        Args:
            timeout: Maximum time to wait for event
            
        Returns:
            MonitorEvent or None if timeout
        """
        try:
            event = self._queue.get(timeout=timeout)
            with self._lock:
                self._stats['events_received'] += 1
                self._stats['queue_size'] = self._queue.qsize()
            return event
        except queue.Empty:
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        with self._lock:
            return self._stats.copy()
    
    def clear(self):
        """Clear all events from queue."""
        with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._stats['queue_size'] = 0


class EventEmitter:
    """Helper class for emitting events from the monitor."""
    
    def __init__(self, event_queue: EventQueue):
        self.event_queue = event_queue
    
    def emit_error(self, message: str, error_data: Dict[str, Any] = None, priority: int = 3):
        """Emit error event."""
        event = MonitorEvent(
            event_type=EventType.ERROR,
            timestamp=datetime.now(),
            data=error_data or {},
            message=message,
            priority=priority
        )
        return self.event_queue.emit(event)
    
    def emit_slot_found(self, slots: List[Dict[str, Any]], message: str = None):
        """Emit slot found event."""
        event = MonitorEvent(
            event_type=EventType.SLOT_FOUND,
            timestamp=datetime.now(),
            data={'slots': slots, 'count': len(slots)},
            message=message or f"🎯 Found {len(slots)} available slots!",
            priority=2
        )
        return self.event_queue.emit(event)
    
    def emit_registration_success(self, registrant_data: Dict[str, Any], slot_data: Dict[str, Any]):
        """Emit successful registration event."""
        event = MonitorEvent(
            event_type=EventType.REGISTRATION_SUCCESS,
            timestamp=datetime.now(),
            data={
                'registrant': registrant_data,
                'slot': slot_data
            },
            message=f"✅ Registration successful for {registrant_data.get('name', 'Unknown')} {registrant_data.get('surname', '')}",
            priority=3
        )
        return self.event_queue.emit(event)
    
    def emit_registration_failed(self, registrant_data: Dict[str, Any], slot_data: Dict[str, Any], error: str):
        """Emit failed registration event."""
        event = MonitorEvent(
            event_type=EventType.REGISTRATION_FAILED,
            timestamp=datetime.now(),
            data={
                'registrant': registrant_data,
                'slot': slot_data,
                'error': error
            },
            message=f"❌ Registration failed for {registrant_data.get('name', 'Unknown')} {registrant_data.get('surname', '')}: {error}",
            priority=2
        )
        return self.event_queue.emit(event)
    
    def emit_status_update(self, stats: Dict[str, Any], message: str = None):
        """Emit status update event."""
        event = MonitorEvent(
            event_type=EventType.STATUS_UPDATE,
            timestamp=datetime.now(),
            data={'stats': stats},
            message=message or "📊 Monitor status update",
            priority=1
        )
        return self.event_queue.emit(event)
    
    def emit_monitor_started(self, config: Dict[str, Any] = None):
        """Emit monitor started event."""
        event = MonitorEvent(
            event_type=EventType.MONITOR_STARTED,
            timestamp=datetime.now(),
            data={'config': config or {}},
            message="🚀 Monitor started",
            priority=2
        )
        return self.event_queue.emit(event)
    
    def emit_monitor_stopped(self, stats: Dict[str, Any] = None):
        """Emit monitor stopped event."""
        event = MonitorEvent(
            event_type=EventType.MONITOR_STOPPED,
            timestamp=datetime.now(),
            data={'final_stats': stats or {}},
            message="⏹️ Monitor stopped",
            priority=2
        )
        return self.event_queue.emit(event)
    
    def emit_database_update(self, update_type: str, data: Dict[str, Any] = None):
        """Emit database update event."""
        event = MonitorEvent(
            event_type=EventType.DATABASE_UPDATE,
            timestamp=datetime.now(),
            data={'update_type': update_type, 'data': data or {}},
            message=f"🗄️ Database update: {update_type}",
            priority=1
        )
        return self.event_queue.emit(event)
    
    def emit_datepicker_change(self, old_config: Dict[str, Any], new_config: Dict[str, Any], changes: List[str]):
        """Emit datepicker configuration change event."""
        event = MonitorEvent(
            event_type=EventType.DATABASE_UPDATE,  # Reusing existing event type for config changes
            timestamp=datetime.now(),
            data={
                'update_type': 'datepicker_config',
                'old_config': old_config,
                'new_config': new_config,
                'changes': changes
            },
            message=f"📅 Datepicker config changed: {', '.join(changes)}",
            priority=2
        )
        return self.event_queue.emit(event)


# Global event queue instance
_global_event_queue = None
_global_event_emitter = None


def get_event_queue() -> EventQueue:
    """Get global event queue instance."""
    global _global_event_queue
    if _global_event_queue is None:
        _global_event_queue = EventQueue()
    return _global_event_queue


def get_event_emitter() -> EventEmitter:
    """Get global event emitter instance."""
    global _global_event_emitter
    if _global_event_emitter is None:
        _global_event_emitter = EventEmitter(get_event_queue())
    return _global_event_emitter


# Convenience functions
def emit_error(message: str, error_data: Dict[str, Any] = None, priority: int = 3) -> bool:
    """Emit error event using global emitter."""
    return get_event_emitter().emit_error(message, error_data, priority)


def emit_slot_found(slots: List[Dict[str, Any]], message: str = None) -> bool:
    """Emit slot found event using global emitter."""
    return get_event_emitter().emit_slot_found(slots, message)


def emit_registration_success(registrant_data: Dict[str, Any], slot_data: Dict[str, Any]) -> bool:
    """Emit registration success event using global emitter."""
    return get_event_emitter().emit_registration_success(registrant_data, slot_data)


def emit_registration_failed(registrant_data: Dict[str, Any], slot_data: Dict[str, Any], error: str) -> bool:
    """Emit registration failed event using global emitter."""
    return get_event_emitter().emit_registration_failed(registrant_data, slot_data, error)


def emit_status_update(stats: Dict[str, Any], message: str = None) -> bool:
    """Emit status update event using global emitter."""
    return get_event_emitter().emit_status_update(stats, message)


def emit_monitor_started(config: Dict[str, Any] = None) -> bool:
    """Emit monitor started event using global emitter."""
    return get_event_emitter().emit_monitor_started(config)


def emit_monitor_stopped(stats: Dict[str, Any] = None) -> bool:
    """Emit monitor stopped event using global emitter."""
    return get_event_emitter().emit_monitor_stopped(stats)


def emit_datepicker_change(old_config: Dict[str, Any], new_config: Dict[str, Any], changes: List[str]) -> bool:
    """Emit datepicker configuration change event using global emitter."""
    return get_event_emitter().emit_datepicker_change(old_config, new_config, changes)


if __name__ == "__main__":
    # Test the event system
    import time
    
    # Create event queue and emitter
    event_queue = EventQueue()
    emitter = EventEmitter(event_queue)
    
    # Emit some test events
    emitter.emit_monitor_started({'room': 'A1', 'check_interval': 0.5})
    emitter.emit_slot_found([{'date': '2025-08-20', 'time': '10:00'}])
    emitter.emit_error("Test error", {'code': 500})
    
    # Consume events
    from logging_config import get_logger
    logger = get_logger(__name__)
    
    logger.info("Testing event queue:")
    while True:
        event = event_queue.get_event(timeout=1.0)
        if event is None:
            break
        logger.info(f"Event: {event.event_type.value} - {event.message}")
        logger.info(f"Data: {event.data}")
        logger.info(f"Priority: {event.priority}")
        logger.info("---")
    
    logger.info(f"Queue stats: {event_queue.get_stats()}")