from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas import ProductCreate
from ..services.crud import create_product, list_products
from ..database import AsyncSessionLocal

router = APIRouter()

async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/", status_code=201)
async def create_product_endpoint(data: ProductCreate, session: AsyncSession = Depends(get_session)):
    return await create_product(session, data.name)

@router.get("/")
async def list_products_endpoint(session: AsyncSession = Depends(get_session)):
    return await list_products(session)
