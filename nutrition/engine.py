"""Deterministic nutrition calculations (Layer 1). No LLM, no I/O besides ORM reads."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q

D = Decimal
TWO = D('0.01')


def q2(x):
    return D(x).quantize(TWO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Nutrients:
    kcal: Decimal = D('0')
    protein_g: Decimal = D('0')
    carbs_g: Decimal = D('0')
    fat_g: Decimal = D('0')
    fibre_g: Decimal = D('0')

    def __add__(self, o):
        return Nutrients(self.kcal + o.kcal, self.protein_g + o.protein_g, self.carbs_g + o.carbs_g,
                         self.fat_g + o.fat_g, self.fibre_g + o.fibre_g)

    def rounded(self):
        return Nutrients(q2(self.kcal), q2(self.protein_g), q2(self.carbs_g), q2(self.fat_g), q2(self.fibre_g))

    def as_dict(self):
        return {k: float(v) for k, v in self.__dict__.items()}


ZERO = Nutrients()


class QuantityError(ValueError):
    pass


def amount_in_base(food, quantity, serving_unit=None):
    """Convert a user quantity to grams/ml for *this* food.

    A ServingUnit is only valid for the food it belongs to: a katori of rice is
    not a katori of dal.
    """
    quantity = D(str(quantity))
    if quantity <= 0:
        raise QuantityError('Quantity must be greater than zero.')
    if quantity > D('5000'):
        raise QuantityError('Quantity is unrealistically large.')
    if serving_unit is None:
        return q2(quantity)  # quantity is already grams / ml
    if serving_unit.food_id != food.id:
        raise QuantityError('That serving size does not belong to this food.')
    return q2(quantity * serving_unit.grams)


def nutrients_for_amount(food, amount_base):
    f = D(amount_base) / D(100)
    return Nutrients(food.kcal * f, food.protein_g * f, food.carbs_g * f, food.fat_g * f, food.fibre_g * f)


def total(items):
    out = ZERO
    for n in items:
        out = out + n
    return out


def entry_nutrients(entry):
    return Nutrients(entry.kcal, entry.protein_g, entry.carbs_g, entry.fat_g, entry.fibre_g)


def daily_summary(user, day):
    """Totals per meal type and overall for one calendar day, from stored entries."""
    from .models import MealEntry
    entries = list(MealEntry.objects.filter(user=user, date=day).select_related('food'))
    by_meal = {k: [] for k, _ in MealEntry.MealType.choices}
    for e in entries:
        by_meal[e.meal_type].append(e)
    meal_totals = {k: total(entry_nutrients(e) for e in v).rounded() for k, v in by_meal.items()}
    return {'entries': by_meal, 'meal_totals': meal_totals,
            'totals': total(entry_nutrients(e) for e in entries).rounded(), 'count': len(entries)}


def remaining(profile, totals):
    """Remaining vs targets (never negative display handled in UI; raw value kept)."""
    def rem(t, used):
        return None if t is None else D(t) - used
    return {'kcal': rem(profile.kcal_target, totals.kcal), 'protein_g': rem(profile.protein_target_g, totals.protein_g),
            'carbs_g': rem(profile.carbs_target_g, totals.carbs_g), 'fat_g': rem(profile.fat_target_g, totals.fat_g),
            'fibre_g': rem(profile.fibre_target_g, totals.fibre_g)}


# ---------------------------------------------------------------- constraints
DIET_RANK = {'vegan': 0, 'veg': 1, 'egg': 2, 'nonveg': 3}
DIET_ALLOWS = {  # user's diet pattern -> food diet types that are acceptable
    'vegan': {'vegan'}, 'veg': {'vegan', 'veg'}, 'egg': {'vegan', 'veg', 'egg'},
    'nonveg': {'vegan', 'veg', 'egg', 'nonveg'},
}


def food_violations(food, profile):
    """Hard-constraint check. Returns a list of human-readable reasons (empty = OK).

    Allergen and ingredient tags are only as complete as the food's data; the UI
    states that composite dishes may contain undeclared ingredients.
    """
    reasons = []
    if food.diet_type not in DIET_ALLOWS.get(profile.diet_pattern, set()):
        reasons.append('does not match your dietary pattern')
    allergies = {a.strip().lower() for a in (profile.allergies or [])}
    hit = allergies & {a.lower() for a in (food.allergens or [])}
    if hit:
        reasons.append('contains ' + ', '.join(sorted(hit)) + ' (your allergy list)')
    excluded = {e.strip().lower() for e in (profile.excluded_ingredients or []) if e.strip()}
    text = f'{food.name} {food.ingredients_text}'.lower()
    hit = {e for e in excluded if e in text}
    if hit:
        reasons.append('contains ' + ', '.join(sorted(hit)) + ' (your exclusions)')
    return reasons


# --------------------------------------------------------------------- search
def search_foods(query, user=None, limit=20, category=None, profile=None, hide_violations=False):
    from .models import Food
    qs = Food.objects.filter(is_active=True)
    qs = qs.filter(Q(owner__isnull=True) | Q(owner=user)) if user is not None else qs.filter(owner__isnull=True)
    if category:
        qs = qs.filter(category=category)
    query = (query or '').strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(aliases__alias__icontains=query)).distinct()
    foods = list(qs.prefetch_related('aliases', 'serving_units')[:200])
    ql = query.lower()

    def score(f):
        names = [f.name.lower()] + [a.alias.lower() for a in f.aliases.all()]
        if ql in names:
            return 0
        if any(n.startswith(ql) for n in names):
            return 1
        if any(f' {ql}' in n for n in names):
            return 2
        return 3
    foods.sort(key=lambda f: (score(f), len(f.name), f.name))
    out = []
    for f in foods:
        bad = food_violations(f, profile) if profile else []
        if bad and hide_violations:
            continue
        out.append((f, bad))
        if len(out) >= limit:
            break
    return out
