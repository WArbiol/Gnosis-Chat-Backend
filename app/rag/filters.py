def build_book_filters(chamber_level: int) -> dict:
    """Build Qdrant payload filters for gnosis_books collection.

    chamber_level 1: only public PDFs
    chamber_level 2: public + chamber_2 PDFs

    TODO: return LlamaIndex MetadataFilters or Qdrant Filter object
    """
    if chamber_level >= 2:
        return {}  # no filter — access all
    return {"access": "public"}


def build_interest_filters(user_id: str) -> dict:
    """Build Qdrant payload filters for user_interests collection.

    TODO: return filter for {user_id: user_id}, ordered by created_at desc
    """
    return {"user_id": user_id}
