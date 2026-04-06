"""Tests for trait derivation: substance + element + tags → traits + profiles."""

from app.engine.trait_deriver import compute_combat_profile, derive_traits, resolve_profile
from app.models.substances import Element, Substance
from app.models.tags import Category, Tag


class TestDeriveTraits:
    def test_metal_burning_sharp(self) -> None:
        traits = derive_traits(Substance.METAL, Element.BURNING, [Tag.SHARP])
        assert set(traits) == {Tag.HEAT_SOURCE, Tag.HOT, Tag.METALLIC, Tag.RIGID, Tag.SHARP}

    def test_ice_heavy(self) -> None:
        traits = derive_traits(Substance.ICE, None, [Tag.HEAVY])
        assert set(traits) == {Tag.BRITTLE, Tag.COLD, Tag.FROZEN, Tag.HEAVY, Tag.RIGID}

    def test_flesh_creature_destroy_verb(self) -> None:
        """CREATURE → LIVING, destroy → HOSTILE."""
        traits = derive_traits(
            Substance.FLESH, None, [], behavior_verbs=["destroy"],
            categories=[Category.CREATURE],
        )
        assert set(traits) == {Tag.HOSTILE, Tag.LIVING}

    def test_creature_category_derives_living(self) -> None:
        traits = derive_traits(Substance.FLESH, None, [], categories=[Category.CREATURE])
        assert Tag.LIVING in traits

    def test_food_category_no_living(self) -> None:
        traits = derive_traits(Substance.CLOTH, None, [], categories=[Category.FOOD])
        assert Tag.LIVING not in traits

    def test_rubber_light(self) -> None:
        traits = derive_traits(Substance.RUBBER, None, [Tag.LIGHT])
        assert set(traits) == {Tag.BOUNCY, Tag.INSULATING, Tag.LIGHT}

    def test_glass_acidic(self) -> None:
        traits = derive_traits(Substance.GLASS, Element.ACIDIC, [])
        assert set(traits) == {Tag.ACIDIC, Tag.BREAKABLE, Tag.REFLECTIVE}

    def test_stone_no_element_no_tags(self) -> None:
        traits = derive_traits(Substance.STONE, None, [])
        assert set(traits) == {Tag.RIGID, Tag.HEAVY}

    def test_flesh_no_traits_without_tags(self) -> None:
        traits = derive_traits(Substance.FLESH, None, [])
        assert traits == []

    def test_fire_substance(self) -> None:
        traits = derive_traits(Substance.FIRE, None, [])
        assert set(traits) == {Tag.GAS, Tag.HEAT_SOURCE, Tag.HOT}


class TestResolveProfile:
    def test_metal_burning_heat_output(self) -> None:
        profile = resolve_profile(Substance.METAL, Element.BURNING, [Tag.SHARP])
        assert profile.heat_output == 1.0  # max(0.0, 1.0) from burning element
        assert profile.mass == 3.0

    def test_ice_heavy_mass(self) -> None:
        profile = resolve_profile(Substance.ICE, None, [Tag.HEAVY])
        assert profile.mass == 7.0  # 2.0 + 5.0 from HEAVY

    def test_rubber_light_mass(self) -> None:
        profile = resolve_profile(Substance.RUBBER, None, [Tag.LIGHT])
        assert profile.mass == 0.8 * 0.15  # 0.12

    def test_breakable_durability(self) -> None:
        profile = resolve_profile(Substance.GLASS, None, [Tag.BREAKABLE])
        assert profile.durability == 40 * 0.4  # 16.0

    def test_flying_zero_gravity(self) -> None:
        profile = resolve_profile(Substance.FLESH, None, [Tag.FLYING])
        assert profile.gravity == 0.0
        assert profile.damping == 2.0

    def test_bouncy_friction(self) -> None:
        profile = resolve_profile(Substance.RUBBER, None, [Tag.BOUNCY])
        assert profile.bounce == 0.9
        assert profile.friction <= 0.2

    def test_electric_conductivity(self) -> None:
        profile = resolve_profile(Substance.WOOD, Element.ELECTRIC, [])
        assert profile.conductivity == 0.5  # max(0.05, 0.5)


class TestCombatProfile:
    def test_metal_sharp_melee(self) -> None:
        profile = resolve_profile(Substance.METAL, None, [Tag.SHARP])
        combat = compute_combat_profile(profile)
        assert combat["melee_damage"] == 50.0  # 25 * 3.0 / 1.5 = 50

    def test_cloth_sharp_melee(self) -> None:
        profile = resolve_profile(Substance.CLOTH, None, [Tag.SHARP])
        combat = compute_combat_profile(profile)
        assert combat["melee_damage"] == 10.0  # 25 * 0.3 / 1.5 = 5.0, clamped to 10

    def test_fire_dps(self) -> None:
        profile = resolve_profile(Substance.LAVA, None, [])
        combat = compute_combat_profile(profile)
        assert combat["fire_dps_coefficient"] == 30.0  # 10 * 3.0

    def test_crush_damage_stone(self) -> None:
        profile = resolve_profile(Substance.STONE, None, [Tag.HEAVY])
        combat = compute_combat_profile(profile)
        # mass = 4.0 + 5.0 = 9.0, crush = 20 * 9.0 / 5.0 = 36.0
        assert combat["crush_damage"] == 36.0
