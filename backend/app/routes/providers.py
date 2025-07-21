from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas import ProviderCreate
from ..services.crud import create_provider
from ..database import AsyncSessionLocal

router = APIRouter()

async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/", status_code=201)
async def create_provider_endpoint(data: ProviderCreate, session: AsyncSession = Depends(get_session)):
    return await create_provider(session, data.name)
