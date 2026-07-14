"""
Notification Aggregator for TerminalAccessManager.

Collects and aggregates notification events to avoid sending excessive emails.
Implements time-based batching and deduplication.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger

from app.services.notification_channels.base import NotificationEvent

# Aggregation window (seconds) - events within this window will be merged
AGGREGATION_WINDOW = 300  # 5 minutes

# Max events per aggregated email
MAX_EVENTS_PER_EMAIL = 50

# Minimum interval between emails to the same recipient
EMAIL_RATE_LIMIT_INTERVAL = 60  # 1 minute

# Global send task running flag
_send_task_running = False


class AggregatedEvent:
    """Represents an aggregated group of similar events."""
    
    def __init__(self, event_type: str, severity: str):
        self.event_type = event_type
        self.severity = severity
        self.events: List[NotificationEvent] = []
        self.first_timestamp: Optional[datetime] = None
        self.last_timestamp: Optional[datetime] = None
    
    def add_event(self, event: NotificationEvent):
        """Add an event to this aggregation group."""
        self.events.append(event)
        if self.first_timestamp is None or event.timestamp < self.first_timestamp:
            self.first_timestamp = event.timestamp
        if self.last_timestamp is None or event.timestamp > self.last_timestamp:
            self.last_timestamp = event.timestamp
    
    def get_count(self) -> int:
        """Get the number of events in this group."""
        return len(self.events)
    
    def get_summary(self) -> str:
        """Generate a summary of aggregated events."""
        if self.get_count() == 1:
            return f"1 event: {self.event_type}"
        return f"{self.get_count()} events: {self.event_type}"


class NotificationAggregator:
    """Aggregates notification events to reduce email flood."""
    
    _instance: Optional['NotificationAggregator'] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self._events: Dict[str, AggregatedEvent] = {}
        self._send_queue: asyncio.Queue[AggregatedEvent] = asyncio.Queue()
        self._last_send_time: Dict[str, datetime] = {}
        self._running = False
        self._flush_interval = AGGREGATION_WINDOW
    
    @classmethod
    async def get_instance(cls) -> 'NotificationAggregator':
        """Get singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = NotificationAggregator()
                cls._instance._start_flush_task()
            return cls._instance
    
    def _start_flush_task(self):
        """Start the periodic flush task."""
        if not self._running:
            self._running = True
            asyncio.create_task(self._periodic_flush())
    
    async def _periodic_flush(self):
        """Periodically flush aggregated events."""
        while self._running:
            await asyncio.sleep(self._flush_interval)
            await self.flush()
    
    async def add_event(self, event: NotificationEvent):
        """Add an event for aggregation."""
        key = f"{event.type}_{event.severity}"
        
        if key not in self._events:
            self._events[key] = AggregatedEvent(event.type, event.severity)
        
        self._events[key].add_event(event)
        logger.debug(f"Added event to aggregator: {event.type}, total={self._events[key].get_count()}")
    
    async def flush(self):
        """Flush all aggregated events to the send queue."""
        if not self._events:
            return
        
        current_time = datetime.now()
        
        for key, aggregated in list(self._events.items()):
            if aggregated.last_timestamp and (current_time - aggregated.last_timestamp).total_seconds() >= self._flush_interval:
                await self._send_queue.put(aggregated)
                del self._events[key]
                logger.info(f"Flushed aggregated events: {aggregated.get_summary()}")
    
    async def get_aggregated_events(self) -> List[AggregatedEvent]:
        """Get all aggregated events ready to send."""
        events = []
        while not self._send_queue.empty():
            try:
                events.append(self._send_queue.get_nowait())
                self._send_queue.task_done()
            except asyncio.QueueEmpty:
                break
        return events
    
    async def close(self):
        """Stop the aggregator."""
        self._running = False
        await self.flush()


# Global aggregator instance
_aggregator: Optional[NotificationAggregator] = None


async def get_notification_aggregator() -> NotificationAggregator:
    """Get the global notification aggregator."""
    global _aggregator
    if _aggregator is None:
        _aggregator = await NotificationAggregator.get_instance()
        _start_send_task()
    return _aggregator


def _start_send_task():
    """Start the notification send task."""
    global _send_task_running
    if not _send_task_running:
        _send_task_running = True
        asyncio.create_task(_notification_send_task())


async def _notification_send_task():
    """Periodically send aggregated notifications."""
    global _send_task_running
    while _send_task_running:
        await asyncio.sleep(30)
        try:
            aggregator = await get_notification_aggregator()
            await aggregator.flush()
            aggregated_events = await aggregator.get_aggregated_events()
            
            if aggregated_events:
                await _send_aggregated_notifications(aggregated_events)
        except Exception as e:
            logger.error(f"Error in notification send task: {str(e)}")


async def _send_aggregated_notifications(aggregated_events: List[AggregatedEvent]):
    """Send aggregated notifications via email."""
    from app.services.notification_channels.email_channel import EmailChannel
    
    for aggregated in aggregated_events:
        try:
            subject = f"[TAM] {aggregated.get_summary()}"
            body = _format_aggregated_body(aggregated)
            
            email_channel = EmailChannel(config={})
            result = await email_channel.send(
                subject=subject,
                message=body,
            )
            
            if result.success:
                logger.info(f"Sent aggregated notification: {aggregated.get_summary()}")
            else:
                logger.error(f"Failed to send aggregated notification: {result.message}")
        except Exception as e:
            logger.error(f"Error sending aggregated notification: {str(e)}")


def _format_aggregated_body(aggregated: AggregatedEvent) -> str:
    """Format the body for aggregated notifications."""
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 10px;">
                {aggregated.get_summary()}
            </h2>
            <p>以下是最近 {aggregated.get_count()} 个事件的汇总：</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr>
                    <th style="padding: 10px; border: 1px solid #ddd; background-color: #f9fafb;">时间</th>
                    <th style="padding: 10px; border: 1px solid #ddd; background-color: #f9fafb;">IP地址</th>
                    <th style="padding: 10px; border: 1px solid #ddd; background-color: #f9fafb;">详细信息</th>
                </tr>
    """
    
    for event in aggregated.events[:MAX_EVENTS_PER_EMAIL]:
        ip = event.data.get("ip_address", event.data.get("terminal_ip", ""))
        details = "<br>".join(f"<strong>{k}:</strong> {v}" for k, v in event.data.items())
        body += f"""
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;">{event.timestamp}</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{ip}</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{details}</td>
                </tr>
        """
    
    if aggregated.get_count() > MAX_EVENTS_PER_EMAIL:
        body += f"""
                <tr>
                    <td colspan="3" style="padding: 10px; border: 1px solid #ddd; text-align: center; color: #666;">
                        ... 还有 {aggregated.get_count() - MAX_EVENTS_PER_EMAIL} 个事件未显示
                    </td>
                </tr>
        """
    
    body += """
            </table>
            <div style="margin-top: 30px; padding: 15px; background-color: #f9fafb; border-radius: 4px;">
                <p style="color: #666; font-size: 12px; margin: 0;">
                    此邮件由 Terminal Access Manager 自动发送，请勿回复。
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return body