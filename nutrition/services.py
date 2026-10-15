"""Application services: the only place that writes nutrition records."""
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q

from . import engine, rules
from .models import Food, MealEntry, ServingUnit, UserProfile


def get_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'display_name': user.get_username()})
    return profile


def apply_computed_targets(profile, today=None):
    """Compute targets from the profile and store them (unless the user customised them)."""
    age = rules.age_from_dob(profile.date_of_birth, today)
    t = rules.compute_targets(weight_kg=profile.weight_kg, height_cm=profile.height_cm, age=age,
                              sex=profile.sex, activity=profile.activity_level, goal=profile.goal, today=today)
    if not profile.targets_customised:
        profile.kcal_target, profile.protein_target_g = t.kcal, t.protein_g
        profile.carbs_target_g, profile.fat_target_g = t.carbs_g, t.fat_g
        profile.fibre_target_g, profile.water_target_ml = t.fibre_g, t.water_ml
        profile.rules_version = t.rules_version
        profile.save()
    return t


def accessible_foods(user):
    return Food.objects.filter(is_active=True).filter(Q(owner__isnull=True) | Q(owner=user))


@transaction.atomic
def log_food(user, *, day, meal_type, food, quantity, serving_unit=None, client_token=''):
    """Create a MealEntry with a nutrient snapshot. Idempotent on (user, client_token)."""
    if client_token:
        existing = MealEntry.objects.filter(user=user, client_token=client_token).first()
        if existing:
            return existing, False
    amount = engine.amount_in_base(food, quantity, serving_unit)
    n = engine.nutrients_for_amount(food, amount).rounded()
    try:
        with transaction.atomic():
            entry = MealEntry.objects.create(
                user=user, date=day, meal_type=meal_type, food=food, food_name=food.name,
                serving_unit=serving_unit, serving_label=serving_unit.label if serving_unit else food.base_unit,
                quantity=Decimal(str(quantity)), amount_base=amount, kcal=n.kcal, protein_g=n.protein_g,
                carbs_g=n.carbs_g, fat_g=n.fat_g, fibre_g=n.fibre_g,
                is_estimate=food.confidence != Food.Confidence.MEASURED, client_token=client_token)
    except IntegrityError:  # concurrent double submit
        return MealEntry.objects.get(user=user, client_token=client_token), False
    return entry, True


@transaction.atomic
def update_entry(entry, *, meal_type, quantity, serving_unit):
    food = entry.food
    if food is None:
        raise engine.QuantityError('This food has been removed from the catalogue and can no longer be edited.')
    amount = engine.amount_in_base(food, quantity, serving_unit)
    n = engine.nutrients_for_amount(food, amount).rounded()
    entry.meal_type, entry.quantity, entry.serving_unit = meal_type, Decimal(str(quantity)), serving_unit
    entry.serving_label = serving_unit.label if serving_unit else food.base_unit
    entry.amount_base = amount
    entry.kcal, entry.protein_g, entry.carbs_g, entry.fat_g, entry.fibre_g = n.kcal, n.protein_g, n.carbs_g, n.fat_g, n.fibre_g
    entry.save()
    return entry


@transaction.atomic
def copy_meal(user, *, from_day, to_day, meal_type):
    """Duplicate one meal section from another day (skips items already copied this call)."""
    src = MealEntry.objects.filter(user=user, date=from_day, meal_type=meal_type)
    created = []
    for e in src:
        created.append(MealEntry.objects.create(
            user=user, date=to_day, meal_type=meal_type, food=e.food, food_name=e.food_name,
            serving_unit=e.serving_unit, serving_label=e.serving_label, quantity=e.quantity,
            amount_base=e.amount_base, kcal=e.kcal, protein_g=e.protein_g, carbs_g=e.carbs_g,
            fat_g=e.fat_g, fibre_g=e.fibre_g, is_estimate=e.is_estimate))
    return created


def recent_foods(user, limit=8):
    seen, out = set(), []
    for e in MealEntry.objects.filter(user=user, food__isnull=False).order_by('-created_at').select_related('food')[:60]:
        if e.food_id not in seen:
            seen.add(e.food_id)
            out.append(e.food)
        if len(out) >= limit:
            break
    return out


def week_consistency(user, today):
    """Days with at least one logged entry in the 7 days ending today (inclusive)."""
    start = today - timedelta(days=6)
    days = set(MealEntry.objects.filter(user=user, date__range=(start, today)).values_list('date', flat=True))
    return [{'date': start + timedelta(days=i), 'logged': (start + timedelta(days=i)) in days} for i in range(7)]


def suggest_next(user, profile, totals, limit=3):
    """Deterministic next-meal ideas: balance remaining kcal, protein and fibre while avoiding heavy dishes."""
    rem = engine.remaining(profile, totals)
    if rem['kcal'] is None:
        return []
    room = rem['kcal']
    if room < 80:
        return []
    want_protein = max(rem['protein_g'] or Decimal(0), Decimal(0))
    ranked = []
    for food in accessible_foods(user).prefetch_related('serving_units').exclude(category__in=['fat', 'sweet']):
        if engine.food_violations(food, profile):
            continue
        unit = next((u for u in food.serving_units.all() if u.is_default), None)
        if unit is None:
            continue
        n = engine.nutrients_for_amount(food, unit.grams)
        if n.kcal > room or n.kcal < 60:
            continue

        name = food.name.lower()
        heavy_dish_penalty = 0
        for keyword in ['biryani', 'fried', 'pizza', 'paratha', 'pulao', 'korma', 'butter', 'curry']:
            if keyword in name:
                heavy_dish_penalty += 25

        score = (n.protein_g * 4) + (n.fibre_g * 3) + (max(Decimal('0'), Decimal('20') - abs(n.kcal - (room / Decimal('3')))) * Decimal('0.8'))
        score -= Decimal(str(heavy_dish_penalty))
        if n.fat_g > Decimal('18'):
            score -= (n.fat_g - Decimal('18')) * Decimal('2')
        ranked.append((score, food, unit, n.rounded()))
    ranked.sort(key=lambda r: (-r[0], r[1].name))
    return [{'food': f, 'unit': u, 'nutrients': n} for _, f, u, n in ranked[:limit]]


def suggest_workout_plan(profile, totals=None):
    """Create a realistic weekly workout rhythm based on the user’s registered activity level."""
    level_map = {
        'sedentary': {'days': 2, 'label': 'Low frequency', 'focus': 'Movement + light strength'},
        'light': {'days': 3, 'label': 'Starter plan', 'focus': 'Full-body strength'},
        'moderate': {'days': 4, 'label': 'Balanced plan', 'focus': 'Strength + conditioning'},
        'high': {'days': 5, 'label': 'Performance plan', 'focus': 'Split strength + cardio'},
    }
    cfg = level_map.get(profile.activity_level or 'light', level_map['light'])
    days = cfg['days']
    choices = [
        ('Mon', 'Lower body + core'),
        ('Tue', 'Upper body strength'),
        ('Wed', 'Recovery walk + mobility'),
        ('Thu', 'Full body strength'),
        ('Fri', 'Upper body + core'),
        ('Sat', 'Conditioning + legs'),
        ('Sun', 'Recovery / mobility'),
    ]

    if days <= 2:
        chosen = [choices[0], choices[3]]
    elif days == 3:
        chosen = [choices[0], choices[2], choices[3]]
    elif days == 4:
        chosen = [choices[0], choices[1], choices[3], choices[5]]
    else:
        chosen = [choices[0], choices[1], choices[3], choices[4], choices[5]]

    plan = []
    exercise_pool = ['Squats', 'Push-ups', 'Deadlifts', 'Lunges', 'Rows', 'Planks', 'Walking', 'Shoulder press']
    for idx, (day, focus) in enumerate(chosen, start=1):
        picks = exercise_pool[idx - 1:idx + 2]
        if len(picks) < 3:
            picks = exercise_pool[:3]
        plan.append({
            'day': day,
            'focus': focus,
            'duration': 35 + (days * 5),
            'exercises': picks,
        })

    if (totals is not None) and getattr(profile, 'kcal_target', None):
        remaining = Decimal(profile.kcal_target or 0) - Decimal(str(totals.kcal))
        if remaining < Decimal('200'):
            for item in plan:
                if 'Recovery' not in item['focus'] and 'mobility' not in item['focus'].lower():
                    item['focus'] = 'Low-impact conditioning'
                    item['duration'] = 25

    return plan


def insight(profile, totals, today_count):
    """Plain, deterministic insight from calculated data (no LLM, no medical claims)."""
    if today_count == 0:
        return 'Nothing logged yet today. Add your first meal to see how you are tracking.'
    msgs = []
    if profile.protein_target_g:
        gap = Decimal(profile.protein_target_g) - totals.protein_g
        msgs.append(f'You have about {max(gap, Decimal(0)):.0f} g of protein left to reach today\'s target.'
                    if gap > 0 else 'You have reached today\'s protein target.')
    if profile.fibre_target_g and totals.fibre_g < Decimal(profile.fibre_target_g) * Decimal('0.5'):
        msgs.append('Fibre is a little low so far; dal, vegetables, fruit or whole grains can help.')
    return ' '.join(msgs)
