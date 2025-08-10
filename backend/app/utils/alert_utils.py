"""
Utility functions for testing alert processing functionality.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.alert_processor import alert_processor
from app.models import PriceRecord


async def trigger_alert_processing(db_session: AsyncSession, price_record: PriceRecord):
    """Utility function to trigger alert processing for a price record."""
    return await alert_processor.process_new_price_record(db_session, price_record)
