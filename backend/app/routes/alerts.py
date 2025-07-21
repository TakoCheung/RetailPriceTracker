from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas import PriceAlertCreate
from ..services.crud import create_alert
from ..database import AsyncSessionLocal

router = APIRouter()

async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/", status_code=201)
async def create_alert_endpoint(data: PriceAlertCreate, session: AsyncSession = Depends(get_session), user_id: int = 1):
    return await create_alert(session, user_id=user_id, product_id=data.product_id, threshold=data.threshold)
