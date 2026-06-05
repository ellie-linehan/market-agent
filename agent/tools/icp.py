from motor.motor_asyncio import AsyncIOMotorDatabase
from models.schemas import ICPSignal


async def store_icp_profile(profile: dict, db: AsyncIOMotorDatabase) -> str:
    """Persist an ICP profile to MongoDB. Returns the inserted id."""
    result = await db.icp_profiles.insert_one(profile)
    return str(result.inserted_id)


async def find_matching_prospects(icp_criteria: dict, db: AsyncIOMotorDatabase) -> list[dict]:
    """Query MongoDB for companies matching the given ICP criteria."""
    cursor = db.prospects.find(icp_criteria).limit(20)
    return await cursor.to_list(length=20)


async def save_prospect(prospect: dict, db: AsyncIOMotorDatabase) -> None:
    """Upsert a prospect by website URL."""
    await db.prospects.update_one(
        {"website": prospect["website"]},
        {"$set": prospect},
        upsert=True,
    )
