from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from nutrition.models import Food, FoodAlias, ServingUnit
from nutrition.seed_data import FOODS, NOTE, SOURCE, VOLUME_FOODS


class Command(BaseCommand):
    help = 'Load/refresh the starter Indian food catalogue (idempotent). Values are estimates, see seed_data.py.'

    @transaction.atomic
    def handle(self, *args, **opts):
        created = updated = 0
        for (name, cat, diet, kcal, p, c, f, fib, prep, ingr, allergens, units, aliases) in FOODS:
            food, was_created = Food.objects.update_or_create(
                slug=slugify(name), defaults=dict(
                    name=name, category=cat, diet_type=diet, kcal=Decimal(str(kcal)), protein_g=Decimal(str(p)),
                    carbs_g=Decimal(str(c)), fat_g=Decimal(str(f)), fibre_g=Decimal(str(fib)), preparation=prep,
                    ingredients_text=ingr, allergens=allergens, source=SOURCE, source_note=NOTE,
                    confidence=Food.Confidence.ESTIMATED, owner=None, is_active=True,
                    base_unit='ml' if name in VOLUME_FOODS else 'g'))
            created += was_created
            updated += not was_created
            for label, grams, default, note in units:
                ServingUnit.objects.update_or_create(food=food, label=label, defaults=dict(
                    grams=Decimal(str(grams)), is_default=default, note=note))
            for alias, lang in aliases:
                FoodAlias.objects.get_or_create(food=food, alias=alias, defaults={'language': lang})
        self.stdout.write(self.style.SUCCESS(f'Foods: {created} created, {updated} updated.'))
