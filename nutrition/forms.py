from datetime import date
from decimal import Decimal

from django import forms

from .models import ServingUnit, UserProfile, MealEntry, WaterEntry, WeightEntry
from . import services


def _split(value):
    return [p.strip().lower() for p in (value or '').replace('\n', ',').split(',') if p.strip()]


class ProfileForm(forms.ModelForm):
    allergies_text = forms.CharField(required=False, label='Food allergies', help_text='Comma separated, e.g. peanut, milk')
    excluded_text = forms.CharField(required=False, label='Ingredients to avoid', help_text='Comma separated, e.g. mushroom, onion')

    class Meta:
        model = UserProfile
        fields = ['display_name', 'date_of_birth', 'sex', 'height_cm', 'weight_kg', 'goal', 'activity_level',
                  'diet_pattern', 'meals_per_day', 'cooking_minutes', 'daily_budget_inr']
        widgets = {'date_of_birth': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if self.instance.pk:
            self.fields['allergies_text'].initial = ', '.join(self.instance.allergies or [])
            self.fields['excluded_text'].initial = ', '.join(self.instance.excluded_ingredients or [])
        for name in ('sex', 'date_of_birth', 'cooking_minutes', 'daily_budget_inr'):
            self.fields[name].required = False
        self.fields['date_of_birth'].required = True  # needed for energy estimate
        self.fields['height_cm'].required = True
        self.fields['weight_kg'].required = True

    def clean_date_of_birth(self):
        dob = self.cleaned_data['date_of_birth']
        if dob and dob > date.today():
            raise forms.ValidationError('Date of birth cannot be in the future.')
        return dob

    def clean_height_cm(self):
        v = self.cleaned_data['height_cm']
        if v is not None and not (Decimal(90) <= v <= Decimal(230)):
            raise forms.ValidationError('Enter a height between 90 and 230 cm.')
        return v

    def clean_weight_kg(self):
        v = self.cleaned_data['weight_kg']
        if v is not None and not (Decimal(25) <= v <= Decimal(300)):
            raise forms.ValidationError('Enter a weight between 25 and 300 kg.')
        return v

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.allergies = _split(self.cleaned_data.get('allergies_text'))
        obj.excluded_ingredients = _split(self.cleaned_data.get('excluded_text'))
        if commit:
            obj.save()
        return obj


class TargetsForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['kcal_target', 'protein_target_g', 'carbs_target_g', 'fat_target_g', 'fibre_target_g', 'water_target_ml']

    def clean_kcal_target(self):
        v = self.cleaned_data['kcal_target']
        if v is None or not (800 <= v <= 5000):
            raise forms.ValidationError('Choose a calorie target between 800 and 5000.')
        return v


class EntryForm(forms.Form):
    food_id = forms.UUIDField()
    meal_type = forms.ChoiceField(choices=MealEntry.MealType.choices)
    quantity = forms.DecimalField(min_value=Decimal('0.01'), max_value=Decimal('5000'), decimal_places=2)
    unit_id = forms.IntegerField(required=False)
    date = forms.DateField()
    token = forms.CharField(required=False, max_length=64)

    def __init__(self, *a, user, **kw):
        super().__init__(*a, **kw)
        self.user = user

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        food = services.accessible_foods(self.user).filter(pk=data['food_id']).first()
        if food is None:
            raise forms.ValidationError('That food could not be found.')
        unit = None
        if data.get('unit_id'):
            unit = ServingUnit.objects.filter(pk=data['unit_id'], food=food).first()
            if unit is None:
                raise forms.ValidationError('That serving size does not belong to this food.')
        data['food'], data['unit'] = food, unit
        return data
