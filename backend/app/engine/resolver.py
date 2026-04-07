from app.cache.manager import CacheManager
from app.models.pairwise import PairwiseResult


class V3Resolver:
    def __init__(self, cache: CacheManager):
        self._cache = cache

    async def resolve(self, name_a: str, name_b: str) -> PairwiseResult | None:
        pair_key = CacheManager.pair_key(name_a, name_b)
        data = await self._cache.get("pairwise", pair_key)
        return PairwiseResult(**data) if data else None
