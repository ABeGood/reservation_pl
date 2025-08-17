"""
Monitor controller for managing RealTimeAvailabilityMonitor lifecycle.
Provides thread-safe start/stop controls and status monitoring.
"""

import threading
import time
from typing import Optional, Dict, Any
from datetime import datetime
from logging_config import get_logger

from realtime_availability_monitor import RealTimeAvailabilityMonitor
from monitor_events_manager import get_event_emitter, emit_monitor_started, emit_monitor_stopped, emit_error


class MonitorController:
    """
    Thread-safe controller for RealTimeAvailabilityMonitor.
    Manages monitor lifecycle and provides status information.
    """
    
    def __init__(self):
        self.monitor: Optional[RealTimeAvailabilityMonitor] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.running = False
        self.lock = threading.Lock()
        self.event_emitter = get_event_emitter()
        self.logger = get_logger(__name__)
        
        # Monitor configuration
        self.config = {
            'room': 'A1',  # A1 or A2
            'check_interval': 0.5,  # seconds between checks
            'auto_registration': True,  # enable auto-registration
            'db_check_interval': 10  # seconds between database checks
        }
        
        # Statistics
        self.start_time: Optional[datetime] = None
        self.stop_time: Optional[datetime] = None
    
    def is_running(self) -> bool:
        """Check if monitor is currently running."""
        try:
            if self.lock.acquire(blocking=False):
                try:
                    return self.running and self.monitor_thread and self.monitor_thread.is_alive()
                finally:
                    self.lock.release()
            else:
                # If lock is busy, return current running state
                return self.running
        except Exception:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current monitor status and statistics."""
        try:
            # Use trylock to avoid blocking
            if self.lock.acquire(blocking=False):
                try:
                    status = {
                        'running': self.running and self.monitor_thread and self.monitor_thread.is_alive(),
                        'config': self.config.copy(),
                        'start_time': self.start_time.isoformat() if self.start_time else None,
                        'stop_time': self.stop_time.isoformat() if self.stop_time else None,
                        'uptime_seconds': None,
                        'monitor_stats': None
                    }
                    
                    if self.start_time and status['running']:
                        status['uptime_seconds'] = (datetime.now() - self.start_time).total_seconds()
                    
                    if self.monitor:
                        status['monitor_stats'] = self.monitor.get_current_stats()
                    
                    return status
                finally:
                    self.lock.release()
            else:
                # Return basic status if lock is busy
                return {
                    'running': self.running,
                    'config': self.config.copy(),
                    'start_time': self.start_time.isoformat() if self.start_time else None,
                    'stop_time': self.stop_time.isoformat() if self.stop_time else None,
                    'uptime_seconds': None,
                    'monitor_stats': {'status': 'busy'}
                }
        except Exception as e:
            self.logger.error(f"Error getting status: {e}")
            return {
                'running': False,
                'config': {},
                'error': str(e)
            }
    
    def start_monitor(self, room: str = 'A1', check_interval: float = 0.5, 
                     auto_registration: bool = True, db_check_interval: int = 10) -> bool:
        """
        Start the availability monitor.
        
        Args:
            room: Room to monitor (A1 or A2)
            check_interval: Seconds between availability checks
            auto_registration: Enable automatic registration attempts
            db_check_interval: Seconds between database checks
            
        Returns:
            bool: True if started successfully
        """
        with self.lock:
            if self.is_running():
                self.logger.warning("Monitor is already running")
                return False
            
            try:
                # Update configuration
                self.config.update({
                    'room': room,
                    'check_interval': check_interval,
                    'auto_registration': auto_registration,
                    'db_check_interval': db_check_interval
                })
                
                # Create monitor instance
                page_url = f"https://olsztyn.uw.gov.pl/wizytakartapolaka/pokoj_{room}.php"
                self.monitor = RealTimeAvailabilityMonitor(page_url=page_url)
                
                # Configure monitor
                self.monitor.endpoint = f"godziny_pokoj_{room}.php"
                self.monitor.db_check_interval = db_check_interval
                
                # Inject event emitter into monitor
                self.monitor.event_emitter = self.event_emitter
                
                # Start monitor in separate thread
                self.monitor_thread = threading.Thread(
                    target=self._run_monitor_loop,
                    name=f"MonitorThread-{room}",
                    daemon=True
                )
                
                self.running = True
                self.start_time = datetime.now()
                self.stop_time = None
                
                self.monitor_thread.start()
                
                # Emit start event
                emit_monitor_started(self.config)
                
                self.logger.info(f"Monitor started for room {room}")
                return True
                
            except Exception as e:
                self.running = False
                self.monitor = None
                self.monitor_thread = None
                error_msg = f"Failed to start monitor: {str(e)}"
                self.logger.error(error_msg)
                emit_error(error_msg, {'exception': str(e)}, priority=4)
                return False
    
    def stop_monitor(self) -> bool:
        """
        Stop the availability monitor.
        
        Returns:
            bool: True if stopped successfully
        """
        with self.lock:
            if not self.is_running():
                self.logger.warning("Monitor is not running")
                return False
            
            try:
                # Signal monitor to stop
                if self.monitor:
                    self.monitor.stop_event.set()
                
                self.running = False
                self.stop_time = datetime.now()
                
                # Wait for thread to finish (with timeout)
                if self.monitor_thread:
                    self.monitor_thread.join(timeout=5.0)
                    if self.monitor_thread.is_alive():
                        self.logger.warning("Monitor thread did not stop cleanly")
                
                # Get final stats before cleanup
                final_stats = self.monitor.get_current_stats() if self.monitor else {}
                
                # Emit stop event
                emit_monitor_stopped(final_stats)
                
                # Cleanup
                self.monitor = None
                self.monitor_thread = None
                
                self.logger.info("Monitor stopped")
                return True
                
            except Exception as e:
                error_msg = f"Error stopping monitor: {str(e)}"
                self.logger.error(error_msg)
                emit_error(error_msg, {'exception': str(e)}, priority=3)
                return False
    
    def restart_monitor(self, **kwargs) -> bool:
        """
        Restart the monitor with optional new configuration.
        
        Returns:
            bool: True if restarted successfully
        """
        self.logger.info("Restarting monitor...")
        
        # Get current config and update with any new values
        current_config = self.config.copy()
        current_config.update(kwargs)
        
        # Stop current monitor
        stop_success = self.stop_monitor()
        if not stop_success:
            self.logger.error("Failed to stop monitor for restart")
            return False
        
        # Wait a moment for cleanup
        time.sleep(1)
        
        # Start with new config
        return self.start_monitor(**current_config)
    
    def _run_monitor_loop(self):
        """Internal method to run the monitor loop."""
        try:
            if self.monitor:
                # Enhanced monitoring with event emission
                self.monitor.start_monitoring(
                    check_interval=self.config['check_interval'],
                    auto_registration=self.config['auto_registration']
                )
                self.logger.info("📤 start_monitoring() returned")
        except Exception as e:
            error_msg = f"Monitor loop crashed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            emit_error(error_msg, {'exception': str(e)}, priority=4)
        finally:
            with self.lock:
                self.running = False
                self.stop_time = datetime.now()
            self.logger.info("✅ _run_monitor_loop completed")
    
    def get_pending_registrants_count(self) -> int:
        """Get count of pending registrants from database."""
        try:
            if self.monitor and hasattr(self.monitor, 'pending_registrants'):
                return len(self.monitor.pending_registrants)
            else:
                # Fallback to database query
                from database import get_pending_registrations
                pending = get_pending_registrations()
                return len(pending)
        except Exception as e:
            self.logger.error(f"Failed to get pending registrants count: {e}")
            return 0
    
    def force_database_refresh(self) -> bool:
        """Force refresh of pending registrants from database."""
        try:
            if self.monitor and hasattr(self.monitor, 'refresh_pending_registrants'):
                self.monitor.refresh_pending_registrants()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to refresh database: {e}")
            return False


# Global monitor controller instance
_global_controller = None


def get_monitor_controller() -> MonitorController:
    """Get global monitor controller instance."""
    global _global_controller
    if _global_controller is None:
        _global_controller = MonitorController()
    return _global_controller


# Convenience functions
def start_monitor(room: str = 'A1', check_interval: float = 0.5, 
                 auto_registration: bool = True, db_check_interval: int = 10) -> bool:
    """Start monitor using global controller."""
    return get_monitor_controller().start_monitor(room, check_interval, auto_registration, db_check_interval)


def stop_monitor() -> bool:
    """Stop monitor using global controller."""
    return get_monitor_controller().stop_monitor()


def restart_monitor(**kwargs) -> bool:
    """Restart monitor using global controller."""
    return get_monitor_controller().restart_monitor(**kwargs)


def get_monitor_status() -> Dict[str, Any]:
    """Get monitor status using global controller."""
    return get_monitor_controller().get_status()


def is_monitor_running() -> bool:
    """Check if monitor is running using global controller."""
    return get_monitor_controller().is_running()


if __name__ == "__main__":
    # Test the monitor controller
    from logging_config import setup_logging
    setup_logging()
    logger = get_logger(__name__)
    
    controller = MonitorController()
    
    logger.info("Testing monitor controller...")
    
    # Test start
    logger.info("Starting monitor...")
    success = controller.start_monitor(room='A1', check_interval=2.0)
    logger.info(f"Start result: {success}")
    
    # Check status
    time.sleep(1)
    status = controller.get_status()
    logger.info(f"Status: {status}")
    
    # Test stop
    time.sleep(5)
    logger.info("Stopping monitor...")
    success = controller.stop_monitor()
    logger.info(f"Stop result: {success}")
    
    # Final status
    status = controller.get_status()
    logger.info(f"Final status: {status}")