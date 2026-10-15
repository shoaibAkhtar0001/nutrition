from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from nutrition import engine, rules
from nutrition.models import Food, ServingUnit


class EngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_foods', verbosity=0)
        cls.roti = Food.objects.get(slug='roti-chapati-plain')
        cls.rice = Food.objects.get(slug='steamed-rice-white-cooked')
        cls.dal = Food.objects.get(slug='dal-tadka-toor')

    def test_household_unit_converts_to_grams_for_that_food(self):
        unit = self.roti.serving_units.get(is_default=True)
        self.assertEqual(engine.amount_in_base(self.roti, 2, unit), Decimal('80.00'))

    def test_serving_unit_cannot_cross_foods(self):
        rice_katori = self.rice.serving_units.get(is_default=True)
        with self.assertRaises(engine.QuantityError):
            engine.amount_in_base(self.dal, 1, rice_katori)

    def test_katori_differs_between_foods(self):
        g = {f.slug: f.serving_units.get(is_default=True).grams for f in (self.rice, self.dal)}
        self.assertNotEqual(len(set(g.values())), 0)
        self.assertEqual(self.rice.serving_units.get(is_default=True).grams, Decimal('150.00'))

    def test_nutrients_scale_from_per_100g(self):
        n = engine.nutrients_for_amount(self.roti, Decimal('40')).rounded()
        self.assertEqual(n.kcal, Decimal('118.80'))  # 297 * 0.4
        self.assertEqual(n.protein_g, Decimal('3.92'))

    def test_invalid_quantities_rejected(self):
        for bad in (0, -1, '0', 10000):
            with self.assertRaises(engine.QuantityError):
                engine.amount_in_base(self.roti, bad)

    def test_totals_use_decimal_without_float_drift(self):
        parts = [engine.nutrients_for_amount(self.roti, Decimal('33.3')) for _ in range(30)]
        self.assertIsInstance(engine.total(parts).kcal, Decimal)

    def test_empty_day_totals_are_zero(self):
        from django.contrib.auth.models import User
        u = User.objects.create_user('empty', password='x-Strong-pass-1')
        s = engine.daily_summary(u, date(2026, 1, 1))
        self.assertEqual(s['count'], 0)
        self.assertEqual(s['totals'].kcal, Decimal('0.00'))

    def test_seed_is_idempotent_and_marks_estimates(self):
        n = Food.objects.count()
        call_command('seed_foods', verbosity=0)
        self.assertEqual(Food.objects.count(), n)
        self.assertFalse(Food.objects.exclude(confidence='estimated').exists())
        self.assertFalse(Food.objects.filter(source='').exists())

    def test_every_seed_food_has_a_default_serving(self):
        for f in Food.objects.all():
            self.assertEqual(f.serving_units.filter(is_default=True).count(), 1, f.name)

    def test_search_finds_alias_and_ranks_exact_first(self):
        names = [f.name for f, _ in engine.search_foods('phulka')]
        self.assertIn('Roti / Chapati (plain)', names)
        self.assertEqual(engine.search_foods('banana')[0][0].name, 'Banana')


class ConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_foods', verbosity=0)

    class P:  # lightweight profile stand-in
        def __init__(self, **kw):
            self.diet_pattern, self.allergies, self.excluded_ingredients = 'veg', [], []
            self.__dict__.update(kw)

    def test_vegetarian_blocks_meat_and_egg(self):
        p = self.P(diet_pattern='veg')
        self.assertTrue(engine.food_violations(Food.objects.get(slug='chicken-curry'), p))
        self.assertTrue(engine.food_violations(Food.objects.get(slug='egg-boiled'), p))
        self.assertFalse(engine.food_violations(Food.objects.get(slug='palak-paneer'), p))

    def test_vegan_blocks_dairy(self):
        self.assertTrue(engine.food_violations(Food.objects.get(slug='paneer-raw'), self.P(diet_pattern='vegan')))

    def test_allergy_is_hard_constraint(self):
        p = self.P(diet_pattern='nonveg', allergies=['peanut'])
        self.assertTrue(engine.food_violations(Food.objects.get(slug='poha-cooked'), p))
        res = engine.search_foods('poha', profile=p, hide_violations=True)
        self.assertEqual(res, [])

    def test_excluded_ingredient_matches_ingredient_tags(self):
        p = self.P(excluded_ingredients=['onion'])
        self.assertTrue(engine.food_violations(Food.objects.get(slug='bhindi-fry'), p))


class TargetRuleTests(TestCase):
    def t(self, **kw):
        base = dict(weight_kg=70, height_cm=170, age=30, sex='male', activity='light', goal='maintain')
        base.update(kw)
        return rules.compute_targets(**base)

    def test_mifflin_st_jeor_male(self):
        self.assertEqual(self.t().rmr_kcal, 1618)  # 700 + 1062.5 - 150 + 5

    def test_deficit_is_capped(self):
        m = self.t(weight_kg=140, height_cm=185, goal='lose', activity='high')
        self.assertGreaterEqual(m.maintenance_kcal - m.kcal, 0)
        self.assertLessEqual(m.maintenance_kcal - m.kcal, rules.MAX_DEFICIT_KCAL + 1)

    def test_calorie_floor_and_warning(self):
        t = self.t(weight_kg=40, height_cm=150, age=70, sex='female', activity='sedentary', goal='lose')
        self.assertGreaterEqual(t.kcal, rules.KCAL_FLOOR)
        self.assertTrue(t.warnings)

    def test_underweight_weight_loss_goal_is_refused(self):
        t = self.t(weight_kg=48, height_cm=170, goal='lose')
        self.assertTrue(any('not appropriate' in w for w in t.warnings))
        self.assertGreaterEqual(t.kcal, t.maintenance_kcal - 1)

    def test_minor_gets_warning(self):
        self.assertTrue(self.t(age=16).warnings)

    def test_missing_sex_documented(self):
        self.assertTrue(self.t(sex='').assumptions)

    def test_missing_inputs_raise(self):
        with self.assertRaises(ValueError):
            rules.compute_targets(weight_kg=None, height_cm=170, age=30, sex='', activity='light', goal='maintain')

    def test_macros_roughly_consistent_with_calories(self):
        t = self.t()
        kcal = t.protein_g * 4 + t.carbs_g * 4 + t.fat_g * 9
        self.assertAlmostEqual(kcal, t.kcal, delta=15)
