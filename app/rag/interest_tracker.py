from app.schemas.user import PlanEnum, PlanLimits

MAX_INTERESTS = PlanLimits.INTERESTS


async def track_interests(
    query: str,
    answer: str,
    user_id: str,
    plan: PlanEnum,
) -> None:
    """Infer user interests from query/answer and upsert into Qdrant.

    Steps:
        1. Skip if plan is FREE (no interest tracking)
        2. Extract interest keywords/topics from query + answer
        3. Generate embedding for the interest
        4. Check current count against plan quota
        5. If at limit, evict oldest interest (sliding window)
        6. Upsert new interest vector

    TODO: implement interest inference + Qdrant upsert
    """
    limit = MAX_INTERESTS.get(plan, 0)
    if limit == 0:
        return

    # TODO: infer interest text from query + answer
    # TODO: generate embedding via text-embedding-004
    # TODO: count current interests for user_id
    # TODO: if count >= limit, delete oldest (by created_at)
    # TODO: upsert new interest with payload {user_id, text, created_at}


async def count_user_interests(user_id: str) -> int:
    """Count existing interest vectors for a user.

    TODO: Qdrant count with payload filter {user_id}
    """
    return 0


async def evict_oldest_interest(user_id: str) -> None:
    """Remove the oldest interest vector for a user (sliding window).

    TODO: Qdrant scroll + delete with payload filter {user_id}, order by created_at ASC, limit 1
    """
