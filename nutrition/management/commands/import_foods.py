"""Import foods from a CSV (e.g. a licensed IFCT 2017 extract).

Required columns: name, category, diet_type, kcal, protein_g, carbs_g, fat_g, fibre_g, source
Optional: preparation, ingredients_text, allergens (semicolon list), confidence, base_unit, aliases (semicolon list)
Serving units (optional): serving_label, serving_grams
"""
import csv
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from nutrition.models import Food, FoodAlias, ServingUnit

REQUIRED = ['name', 'category', 'diet_type', 'kcal', 'protein_g', 'carbs_g', 'fat_g', 'fibre_g', 'source']


class Command(BaseCommand):
    help = 'Import foods from CSV with provenance. Existing foods are matched by slug and updated.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path')

    @transaction.atomic
    def handle(self, *args, csv_path, **opts):
        with open(csv_path, newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
            if missing:
                raise CommandError(f'Missing columns: {", ".join(missing)}')
            n = 0
            for i, row in enumerate(reader, start=2):
                try:
                    nums = {k: Decimal(row[k]) for k in ('kcal', 'protein_g', 'carbs_g', 'fat_g', 'fibre_g')}
                except InvalidOperation:
                    raise CommandError(f'Row {i}: non-numeric nutrient value')
                if any(v < 0 for v in nums.values()):
                    raise CommandError(f'Row {i}: negative nutrient value')
                if row['category'] not in Food.Category.values or row['diet_type'] not in Food.DietType.values:
                    raise CommandError(f'Row {i}: invalid category or diet_type')
                food, _ = Food.objects.update_or_create(slug=slugify(row['name']), defaults=dict(
                    name=row['name'], category=row['category'], diet_type=row['diet_type'], source=row['source'],
                    preparation=row.get('preparation', ''), ingredients_text=row.get('ingredients_text', ''),
                    allergens=[a.strip() for a in row.get('allergens', '').split(';') if a.strip()],
                    confidence=row.get('confidence') or Food.Confidence.MEASURED,
                    base_unit=row.get('base_unit') or 'g', owner=None, **nums))
                for alias in (row.get('aliases') or '').split(';'):
                    if alias.strip():
                        FoodAlias.objects.get_or_create(food=food, alias=alias.strip())
                if row.get('serving_label') and row.get('serving_grams'):
                    ServingUnit.objects.update_or_create(food=food, label=row['serving_label'],
                                                         defaults={'grams': Decimal(row['serving_grams'])})
                n += 1
        self.stdout.write(self.style.SUCCESS(f'Imported {n} foods.'))
