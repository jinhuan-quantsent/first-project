import sys
sys.path.insert(0, "/opt/fund-sentiment/v5-deploy/backend")
#!/usr/bin/env python3
import asyncio, sys
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import select, update as sa_update
from app.core.config import settings
from app.engine.quantile import QuantileNorm
from app.models.factor_history import FactorHistory

async def main(target_date=None):
    if target_date is None:
        target_date = date.today().isoformat()
    print("Updating quantile for", target_date)
    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as session:
        quantile = QuantileNorm(session=session)
        result = await session.execute(select(FactorHistory).where(FactorHistory.trade_date == target_date))
        records = result.scalars().all()
        print("Found", len(records), "records")
        updated = 0
        for rec in records:
            pct = await quantile.calc_percentile(rec.raw_value, rec.index_code, rec.factor_name)
            if pct is not None:
                await session.execute(sa_update(FactorHistory).where(FactorHistory.id == rec.id).values(quantile_percentile=pct))
                updated += 1
        await session.commit()
        print("Updated", updated, "records")
    await engine.dispose()

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(target))
