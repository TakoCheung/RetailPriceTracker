from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas import UserPreferenceUpdate
from ..services.crud import get_user_preference, update_user_preference
from ..database import AsyncSessionLocal

router = APIRouter()

async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/")
async def read_preference(session: AsyncSession = Depends(get_session), user_id: int = 1):
    return await get_user_preference(session, user_id)

@router.patch("/")
async def update_preference(data: UserPreferenceUpdate, session: AsyncSession = Depends(get_session), user_id: int = 1):
    return await update_user_preference(session, user_id, **data.dict(exclude_unset=True))
