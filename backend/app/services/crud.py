from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Product, Provider, PriceAlert, UserPreference

async def create_product(session: AsyncSession, name: str) -> Product:
    product = Product(name=name)
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product

async def list_products(session: AsyncSession):
    result = await session.execute(select(Product))
    return result.scalars().all()

async def create_provider(session: AsyncSession, name: str) -> Provider:
    provider = Provider(name=name)
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    return provider

async def create_alert(session: AsyncSession, user_id: int, product_id: int, threshold: float) -> PriceAlert:
    alert = PriceAlert(user_id=user_id, product_id=product_id, threshold=threshold)
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return alert

async def get_user_preference(session: AsyncSession, user_id: int) -> UserPreference:
    pref = await session.get(UserPreference, user_id)
    if not pref:
        pref = UserPreference(user_id=user_id, default_currency="USD", notify_email=True)
        session.add(pref)
        await session.commit()
        await session.refresh(pref)
    return pref

async def update_user_preference(session: AsyncSession, user_id: int, **kwargs) -> UserPreference:
    pref = await get_user_preference(session, user_id)
    for k, v in kwargs.items():
        if v is not None:
            setattr(pref, k, v)
    session.add(pref)
    await session.commit()
    await session.refresh(pref)
    return pref
