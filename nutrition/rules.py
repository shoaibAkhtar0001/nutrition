"""Versioned, configurable nutrition rules.

IMPORTANT: these are conservative *product defaults*, not official dietary
guidance and not medical advice. Each rule records where it comes from so it can
be reviewed (ideally by a registered dietitian) and changed in one place.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

RULES_VERSION = '2026.10-draft1'

# Mifflin-St Jeor (Mifflin et al., Am J Clin Nutr 1990) resting energy equation.
# For users who skip "sex" we use the midpoint of the male and female constants
# (-78 kcal) and say so in the UI. It is an estimate either way.
MSJ_CONSTANT = {'male': 5, 'female': -161, '': -78}

# Conventional activity factors applied to RMR (widely used convention, not a
# measured value for any individual).
ACTIVITY_FACTOR = {'sedentary': Decimal('1.2'), 'light': Decimal('1.375'),
                   'moderate': Decimal('1.55'), 'high': Decimal('1.725')}

# Energy adjustment by goal, as a fraction of maintenance. Deliberately mild.
GOAL_ADJUSTMENT = {'lose': Decimal('-0.15'), 'maintain': Decimal('0'), 'gain': Decimal('0.10'),
                   'muscle': Decimal('0.08'), 'general': Decimal('0')}
MAX_DEFICIT_KCAL = 500      # never prescribe a bigger daily deficit than this
MAX_SURPLUS_KCAL = 400
KCAL_FLOOR = 1200           # never target below this without professional oversight

# Protein, g per kg body weight, by goal (product defaults; review with an RD).
PROTEIN_G_PER_KG = {'lose': Decimal('1.2'), 'maintain': Decimal('1.0'), 'gain': Decimal('1.1'),
                    'muscle': Decimal('1.6'), 'general': Decimal('1.0')}
FAT_ENERGY_FRACTION = Decimal('0.28')
FIBRE_G_PER_1000_KCAL = Decimal('14')   # US DRI-style heuristic, shown as "approximate"
WATER_ML_DEFAULT = 2500

MIN_ADULT_AGE = 18
BMI_LOW_FLAG = Decimal('18.5')


@dataclass
class Targets:
    kcal: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fibre_g: int
    water_ml: int
    rmr_kcal: int
    maintenance_kcal: int
    warnings: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    rules_version: str = RULES_VERSION


def age_from_dob(dob, today=None):
    if not dob:
        return None
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def compute_targets(*, weight_kg, height_cm, age, sex, activity, goal, today=None) -> Targets:
    """Deterministic target calculation. Raises ValueError for missing inputs."""
    if weight_kg is None or height_cm is None or age is None:
        raise ValueError('weight, height and age are required to estimate targets')
    weight_kg, height_cm = Decimal(weight_kg), Decimal(height_cm)
    warnings, assumptions = [], []

    rmr = Decimal(10) * weight_kg + Decimal('6.25') * height_cm - Decimal(5) * Decimal(age) \
        + Decimal(MSJ_CONSTANT.get(sex or '', -78))
    if not sex:
        assumptions.append('Sex not provided: used the midpoint of the male and female equation constants.')
    maintenance = rmr * ACTIVITY_FACTOR.get(activity, Decimal('1.375'))

    delta = maintenance * GOAL_ADJUSTMENT.get(goal, Decimal('0'))
    delta = max(Decimal(-MAX_DEFICIT_KCAL), min(Decimal(MAX_SURPLUS_KCAL), delta))
    kcal = maintenance + delta
    if kcal < KCAL_FLOOR:
        kcal = Decimal(KCAL_FLOOR)
        warnings.append(f'Your estimated needs are low, so the target was held at a {KCAL_FLOOR} kcal minimum. '
                        'Please speak to a doctor or registered dietitian before eating less.')

    height_m = height_cm / Decimal(100)
    bmi = weight_kg / (height_m * height_m)
    if age < MIN_ADULT_AGE:
        warnings.append('NutriTrack targets are designed for adults. For anyone under 18, please use guidance '
                        'from a paediatrician or registered dietitian.')
    if bmi < BMI_LOW_FLAG and goal == 'lose':
        warnings.append('A weight-loss goal is not appropriate at this body weight. Targets were set to '
                        'maintenance; please consult a healthcare professional.')
        kcal = max(Decimal(KCAL_FLOOR), maintenance)

    protein = Decimal(weight_kg) * PROTEIN_G_PER_KG.get(goal, Decimal('1.0'))
    fat = kcal * FAT_ENERGY_FRACTION / Decimal(9)
    carbs = (kcal - protein * 4 - fat * 9) / Decimal(4)
    fibre = kcal / Decimal(1000) * FIBRE_G_PER_1000_KCAL

    r = lambda x: int(Decimal(x).quantize(Decimal('1')))
    return Targets(kcal=r(kcal), protein_g=r(protein), carbs_g=r(max(carbs, Decimal(0))), fat_g=r(fat),
                   fibre_g=r(fibre), water_ml=WATER_ML_DEFAULT, rmr_kcal=r(rmr),
                   maintenance_kcal=r(maintenance), warnings=warnings, assumptions=assumptions)
