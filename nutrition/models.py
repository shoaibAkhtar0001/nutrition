"""Data model for NutriTrack's nutrition engine.

Design notes
------------
* All nutrient quantities are Decimal columns (never floats).
* Food nutrients are stored per 100 g (or per 100 ml for liquids).
* A MealEntry stores a *snapshot* of the computed nutrients at logging time, so
  editing or deleting a Food later never silently rewrites a user's history.
* Every food records its provenance (source + confidence).
"""
import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

D = Decimal


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# --------------------------------------------------------------------------
# User profile & targets
# --------------------------------------------------------------------------
class UserProfile(TimeStamped):
    class Goal(models.TextChoices):
        LOSE = 'lose', 'Weight loss'
        MAINTAIN = 'maintain', 'Weight maintenance'
        GAIN = 'gain', 'Weight gain'
        MUSCLE = 'muscle', 'Muscle building'
        GENERAL = 'general', 'General nutrition improvement'

    class Activity(models.TextChoices):
        SEDENTARY = 'sedentary', 'Sedentary (desk job, little exercise)'
        LIGHT = 'light', 'Lightly active (1-3 workouts/week)'
        MODERATE = 'moderate', 'Moderately active (3-5 workouts/week)'
        HIGH = 'high', 'Very active (6-7 workouts/week)'

    class Diet(models.TextChoices):
        VEG = 'veg', 'Vegetarian'
        VEGAN = 'vegan', 'Vegan'
        EGG = 'egg', 'Eggetarian'
        NONVEG = 'nonveg', 'Non-vegetarian'

    class Sex(models.TextChoices):
        FEMALE = 'female', 'Female'
        MALE = 'male', 'Male'
        UNSPECIFIED = '', 'Prefer not to say'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='nt_profile')
    display_name = models.CharField(max_length=80, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=12, choices=Sex.choices, blank=True, default='')
    height_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    goal = models.CharField(max_length=12, choices=Goal.choices, default=Goal.GENERAL)
    target_weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    activity_level = models.CharField(max_length=12, choices=Activity.choices, default=Activity.LIGHT)
    diet_pattern = models.CharField(max_length=8, choices=Diet.choices, default=Diet.VEG)

    # Hard constraints (lowercase tags). Sensitive: only ever shown to the owner.
    allergies = models.JSONField(default=list, blank=True)
    excluded_ingredients = models.JSONField(default=list, blank=True)
    preferred_cuisines = models.JSONField(default=list, blank=True)

    meals_per_day = models.PositiveSmallIntegerField(default=4)
    cooking_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    daily_budget_inr = models.PositiveIntegerField(null=True, blank=True)

    # Targets (computed by nutrition.rules, user-editable)
    kcal_target = models.PositiveIntegerField(null=True, blank=True)
    protein_target_g = models.PositiveIntegerField(null=True, blank=True)
    carbs_target_g = models.PositiveIntegerField(null=True, blank=True)
    fat_target_g = models.PositiveIntegerField(null=True, blank=True)
    fibre_target_g = models.PositiveIntegerField(null=True, blank=True)
    water_target_ml = models.PositiveIntegerField(default=2500)
    targets_customised = models.BooleanField(default=False)
    rules_version = models.CharField(max_length=32, blank=True)

    onboarded = models.BooleanField(default=False)

    def __str__(self):
        return f'Profile<{self.user_id}>'


class AICoachConversation(TimeStamped):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_coach_conversations')
    title = models.CharField(max_length=160, default='Nutrition chat')
    last_message_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-last_message_at']

    def __str__(self):
        return f'{self.user.username}: {self.title}'


class AICoachMessage(TimeStamped):
    class Role(models.TextChoices):
        USER = 'user', 'User'
        ASSISTANT = 'assistant', 'Assistant'
        SYSTEM = 'system', 'System'

    conversation = models.ForeignKey(AICoachConversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.USER)
    content = models.TextField()
    provider_status = models.CharField(max_length=32, default='pending')

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.conversation_id}::{self.role}'


# --------------------------------------------------------------------------
# Exercise library & workout plans
# --------------------------------------------------------------------------
class Exercise(TimeStamped):
    class MuscleGroup(models.TextChoices):
        CHEST = 'chest', 'Chest'
        BACK = 'back', 'Back'
        SHOULDERS = 'shoulders', 'Shoulders'
        BICEPS = 'biceps', 'Biceps'
        TRICEPS = 'triceps', 'Triceps'
        LEGS = 'legs', 'Legs'
        GLUTES = 'glutes', 'Glutes'
        ABS_CORE = 'abs_and_core', 'Abs and Core'
        FOREARMS = 'forearms', 'Forearms'
        FULL_BODY = 'full_body', 'Full Body'

    class Equipment(models.TextChoices):
        BODYWEIGHT = 'bodyweight', 'Bodyweight'
        DUMBBELLS = 'dumbbells', 'Dumbbells'
        BARBELLS = 'barbells', 'Barbells'
        RESISTANCE_BANDS = 'resistance_bands', 'Resistance bands'
        CABLES = 'cables', 'Cables'
        MACHINES = 'machines', 'Machines'
        KETTLEBELLS = 'kettlebells', 'Kettlebells'
        NO_EQUIPMENT = 'no_equipment', 'No equipment'

    class Difficulty(models.TextChoices):
        BEGINNER = 'beginner', 'Beginner'
        INTERMEDIATE = 'intermediate', 'Intermediate'
        ADVANCED = 'advanced', 'Advanced'

    class ExerciseType(models.TextChoices):
        STRENGTH = 'strength', 'Strength'
        CARDIO = 'cardio', 'Cardio'
        MOBILITY = 'mobility', 'Mobility'
        STRETCHING = 'stretching', 'Stretching'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField()
    primary_muscle = models.CharField(max_length=25, choices=MuscleGroup.choices)
    secondary_muscles = models.JSONField(default=list, blank=True)
    equipment = models.CharField(max_length=25, choices=Equipment.choices, default=Equipment.BODYWEIGHT)
    difficulty = models.CharField(max_length=16, choices=Difficulty.choices, default=Difficulty.BEGINNER)
    exercise_type = models.CharField(max_length=16, choices=ExerciseType.choices, default=ExerciseType.STRENGTH)
    instructions = models.JSONField(default=list, blank=True)
    common_mistakes = models.JSONField(default=list, blank=True)
    safety_notes = models.JSONField(default=list, blank=True)
    default_sets = models.PositiveSmallIntegerField(default=3)
    default_reps = models.CharField(max_length=30, default='8-12')
    rest_seconds = models.PositiveSmallIntegerField(default=60)
    duration_seconds = models.PositiveSmallIntegerField(null=True, blank=True)
    estimated_calories = models.CharField(max_length=40, blank=True)
    video_url = models.URLField(max_length=500, blank=True)
    thumbnail_url = models.URLField(max_length=500, blank=True)
    data_source = models.CharField(max_length=120, default='starter library')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    @property
    def visual_emoji(self):
        visual_map = {
            'push-ups': '🏋️',
            'bench-press': '🏋️',
            'incline-dumbbell-press': '🏋️',
            'lat-pulldown': '🏋️',
            'pull-ups': '🏋️',
            'seated-rows': '🏋️',
            'shoulder-press': '🏋️',
            'lateral-raises': '🏋️',
            'biceps-curls': '💪',
            'hammer-curls': '💪',
            'triceps-pushdowns': '💪',
            'squats': '🏋️‍♂️',
            'lunges': '🏃',
            'romanian-deadlifts': '🏋️',
            'leg-press': '🏋️',
            'calf-raises': '🦵',
            'planks': '🧘',
            'crunches': '🧘',
            'leg-raises': '🧘',
            'glute-bridges': '🧍',
            'walking': '🚶',
            'jumping-jacks': '🤸',
            'cat-cow-stretch': '🧘',
            'hamstring-stretch': '🧘',
        }
        return visual_map.get(self.slug, '🏋️')

    @property
    def embed_url(self):
        if not self.video_url:
            return ''
        match = re.search(r'(?:v=|/)([A-Za-z0-9_-]{11})(?:[?&]|$)', self.video_url)
        if not match:
            return self.video_url
        return f'https://www.youtube.com/embed/{match.group(1)}'

    def __str__(self):
        return self.name


class WorkoutPlan(TimeStamped):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workout_plans')
    name = models.CharField(max_length=120, default='My workout plan')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username}: {self.name}'


class WorkoutPlanExercise(TimeStamped):
    plan = models.ForeignKey(WorkoutPlan, on_delete=models.CASCADE, related_name='exercises')
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='plan_entries')
    order = models.PositiveSmallIntegerField(default=0)
    sets = models.PositiveSmallIntegerField(default=3)
    reps = models.CharField(max_length=30, default='8-12')
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    rest_seconds = models.PositiveSmallIntegerField(default=60)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f'{self.plan.name} - {self.exercise.name}'


class WorkoutSession(TimeStamped):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        SKIPPED = 'skipped', 'Skipped'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workout_sessions')
    name = models.CharField(max_length=160, default='Workout')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    workout_plan = models.ForeignKey(WorkoutPlan, null=True, blank=True, on_delete=models.SET_NULL, related_name='sessions')
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    elapsed_seconds = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.user.username}: {self.name}'


class WorkoutSessionExercise(TimeStamped):
    class ExecutionStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        SKIPPED = 'skipped', 'Skipped'

    session = models.ForeignKey(WorkoutSession, on_delete=models.CASCADE, related_name='exercise_entries')
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='session_entries')
    order = models.PositiveSmallIntegerField(default=0)
    sets_target = models.PositiveSmallIntegerField(default=3)
    reps = models.CharField(max_length=30, default='8-12')
    rest_seconds = models.PositiveSmallIntegerField(default=60)
    status = models.CharField(max_length=16, choices=ExecutionStatus.choices, default=ExecutionStatus.PENDING)
    completed_sets = models.PositiveSmallIntegerField(default=0)
    set_data = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f'{self.session.name} - {self.exercise.name}'


# --------------------------------------------------------------------------
# Food database
# --------------------------------------------------------------------------
class Food(TimeStamped):
    class Category(models.TextChoices):
        BREAD = 'bread', 'Roti, paratha & breads'
        RICE = 'rice', 'Rice, pulao & biryani'
        DAL = 'dal', 'Dal & legumes'
        SABZI = 'sabzi', 'Sabzi & curries'
        SOUTH = 'south', 'Idli, dosa & South Indian'
        BREAKFAST = 'breakfast', 'Poha, upma & breakfast'
        DAIRY = 'dairy', 'Paneer & dairy'
        EGGMEAT = 'eggmeat', 'Eggs, fish & meat'
        FRUIT = 'fruit', 'Fruits'
        VEG = 'veg', 'Vegetables'
        SNACK = 'snack', 'Snacks & street food'
        SWEET = 'sweet', 'Sweets & desserts'
        NUTS = 'nuts', 'Nuts, seeds & dry fruit'
        BEVERAGE = 'beverage', 'Beverages'
        FAT = 'fat', 'Oils, ghee & sugar'
        PACKAGED = 'packaged', 'Packaged foods'

    class DietType(models.TextChoices):
        VEGAN = 'vegan', 'Vegan'
        VEG = 'veg', 'Vegetarian'
        EGG = 'egg', 'Contains egg'
        NONVEG = 'nonveg', 'Non-vegetarian'

    class Confidence(models.TextChoices):
        MEASURED = 'measured', 'Laboratory / published table value'
        DERIVED = 'derived', 'Calculated from a recipe'
        ESTIMATED = 'estimated', 'Estimate (not laboratory verified)'

    class BaseUnit(models.TextChoices):
        GRAM = 'g', 'grams'
        ML = 'ml', 'millilitres'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    category = models.CharField(max_length=16, choices=Category.choices)
    diet_type = models.CharField(max_length=8, choices=DietType.choices, default=DietType.VEG)
    base_unit = models.CharField(max_length=2, choices=BaseUnit.choices, default=BaseUnit.GRAM)

    # Per 100 g (or 100 ml)
    kcal = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])
    protein_g = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(0)])
    carbs_g = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(0)])
    fat_g = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(0)])
    fibre_g = models.DecimalField(max_digits=6, decimal_places=2, default=D('0'), validators=[MinValueValidator(0)])
    extra_nutrients = models.JSONField(default=dict, blank=True)  # e.g. {"iron_mg": 2.1}

    preparation = models.CharField(max_length=120, blank=True)
    ingredients_text = models.CharField(max_length=300, blank=True,
                                        help_text='Comma-separated lowercase ingredient tags used for exclusions.')
    allergens = models.JSONField(default=list, blank=True)  # e.g. ["milk", "gluten"]
    est_cost_inr_per_100g = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)

    source = models.CharField(max_length=200)
    source_note = models.CharField(max_length=300, blank=True)
    confidence = models.CharField(max_length=10, choices=Confidence.choices, default=Confidence.ESTIMATED)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                              related_name='custom_foods', help_text='Null = shared catalogue food.')
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=['name']), models.Index(fields=['category', 'diet_type'])]
        ordering = ['name']

    def __str__(self):
        return self.name


class FoodAlias(models.Model):
    food = models.ForeignKey(Food, on_delete=models.CASCADE, related_name='aliases')
    alias = models.CharField(max_length=120, db_index=True)
    language = models.CharField(max_length=20, blank=True, help_text='e.g. Hindi, Tamil, region name')

    class Meta:
        unique_together = [('food', 'alias')]

    def __str__(self):
        return self.alias


class ServingUnit(models.Model):
    """A household measure for ONE specific food. Never shared across foods."""
    food = models.ForeignKey(Food, on_delete=models.CASCADE, related_name='serving_units')
    label = models.CharField(max_length=80)           # "1 roti (medium)"
    grams = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(D('0.01'))])
    is_default = models.BooleanField(default=False)
    note = models.CharField(max_length=160, blank=True)  # documents the assumption

    class Meta:
        unique_together = [('food', 'label')]

    def __str__(self):
        return f'{self.food.name}: {self.label} = {self.grams} {self.food.base_unit}'


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
class MealEntry(TimeStamped):
    class MealType(models.TextChoices):
        BREAKFAST = 'breakfast', 'Breakfast'
        LUNCH = 'lunch', 'Lunch'
        SNACK = 'snack', 'Snacks'
        DINNER = 'dinner', 'Dinner'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='meal_entries')
    date = models.DateField(db_index=True)
    meal_type = models.CharField(max_length=10, choices=MealType.choices)
    food = models.ForeignKey(Food, null=True, on_delete=models.SET_NULL, related_name='entries')
    food_name = models.CharField(max_length=160)  # snapshot
    serving_unit = models.ForeignKey(ServingUnit, null=True, blank=True, on_delete=models.SET_NULL)
    serving_label = models.CharField(max_length=80, blank=True)  # snapshot
    quantity = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(D('0.01'))])
    amount_base = models.DecimalField(max_digits=8, decimal_places=2)  # grams / ml actually eaten

    kcal = models.DecimalField(max_digits=8, decimal_places=2)
    protein_g = models.DecimalField(max_digits=7, decimal_places=2)
    carbs_g = models.DecimalField(max_digits=7, decimal_places=2)
    fat_g = models.DecimalField(max_digits=7, decimal_places=2)
    fibre_g = models.DecimalField(max_digits=7, decimal_places=2)
    is_estimate = models.BooleanField(default=True)

    # Guards against double-submits (same token from the same user is accepted once).
    client_token = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ['date', 'created_at']
        indexes = [models.Index(fields=['user', 'date'])]
        constraints = [
            models.UniqueConstraint(fields=['user', 'client_token'], condition=~models.Q(client_token=''),
                                    name='uniq_meal_client_token'),
        ]


class WaterEntry(TimeStamped):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='water_entries')
    date = models.DateField(db_index=True)
    ml = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        indexes = [models.Index(fields=['user', 'date'])]


class WeightEntry(TimeStamped):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='weight_entries')
    date = models.DateField()
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, validators=[MinValueValidator(D('20'))])

    class Meta:
        unique_together = [('user', 'date')]
        ordering = ['date']
