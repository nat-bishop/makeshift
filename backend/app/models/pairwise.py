from pydantic import BaseModel


class PairwiseResult(BaseModel):
    damage_a: int = 0
    damage_b: int = 0
    state_change_a: int = 0  # 0-14
    state_change_b: int = 0  # 0-14
    force_b: int = 0
    direction_b: int = 0  # 0=push, 1=pull
    destroy_a: bool = False
    destroy_b: bool = False
    mode: int = 0  # 0=instant, 1=continuous
