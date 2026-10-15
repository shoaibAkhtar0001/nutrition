"""Starter food catalogue.

PROVENANCE WARNING: these values are approximate figures per 100 g (or 100 ml)
of the *prepared* food as typically eaten, compiled as a development starter
set. They are NOT laboratory measurements and NOT copied from IFCT 2017.
Every row is stored with confidence='estimated'. Replace/extend them with
licensed reference data via:  python manage.py import_foods path/to/file.csv

Tuple layout:
 name, category, diet, kcal, protein, carbs, fat, fibre, preparation,
 ingredients_tags, allergens, [(serving label, grams/ml, is_default, note)], [(alias, language)]
"""
SOURCE = 'NutriTrack starter set (approximate; not IFCT laboratory data)'
NOTE = 'Typical value for the dish as eaten; real values vary with recipe, oil and portion.'

ML = '__ml__'  # marker: food measured per 100 ml

FOODS = [
 # ---- breads
 ('Roti / Chapati (plain)', 'bread', 'vegan', 297, 9.8, 55, 3.7, 4.8, 'Tawa-cooked, no ghee', 'wheat flour', ['gluten'],
  [('1 roti (medium, ~40 g)', 40, True, 'Medium home-style roti; thin phulka is ~25-30 g'), ('1 roti (large, ~60 g)', 60, False, '')],
  [('phulka', 'Hindi'), ('chapati', 'English'), ('rotli', 'Gujarati')]),
 ('Paratha (plain, with oil)', 'bread', 'veg', 326, 7.2, 46, 13, 3.5, 'Shallow-fried', 'wheat flour, oil', ['gluten'],
  [('1 paratha (medium, ~60 g)', 60, True, '')], []),
 ('Naan (plain)', 'bread', 'veg', 290, 9, 50, 5, 2, 'Tandoor baked', 'refined wheat flour, curd', ['gluten', 'milk'],
  [('1 naan (~90 g)', 90, True, '')], []),
 # ---- rice
 ('Steamed rice (white, cooked)', 'rice', 'vegan', 130, 2.7, 28, 0.3, 0.4, 'Boiled/steamed', 'rice', [],
  [('1 katori (~150 g cooked)', 150, True, 'Katori sizes vary; this assumes a ~150 g cooked portion'), ('1 plate (~250 g cooked)', 250, False, '')],
  [('chawal', 'Hindi'), ('bhaat', 'Marathi')]),
 ('Jeera rice', 'rice', 'veg', 150, 3, 28, 3, 0.8, 'Tempered with ghee/oil and cumin', 'rice, cumin, ghee', ['milk'],
  [('1 katori (~150 g cooked)', 150, True, '')], []),
 ('Vegetable pulao', 'rice', 'veg', 150, 3.2, 26, 3.5, 1.2, 'One-pot rice with vegetables', 'rice, vegetables, oil, onion', [],
  [('1 katori (~150 g)', 150, True, '')], []),
 ('Chicken biryani', 'rice', 'nonveg', 180, 9, 22, 6.5, 1, 'Layered rice and chicken', 'rice, chicken, oil, onion, curd', ['milk'],
  [('1 plate (~300 g)', 300, True, '')], []),
 ('Khichdi (dal-rice)', 'rice', 'vegan', 120, 4.5, 20, 2.5, 1.8, 'Rice and moong dal, lightly tempered', 'rice, moong dal, oil', [],
  [('1 katori (~180 g)', 180, True, '')], []),
 # ---- dal & legumes
 ('Dal tadka (toor)', 'dal', 'veg', 95, 5, 12, 3, 3.5, 'Boiled dal with ghee tadka', 'toor dal, ghee, onion, garlic', ['milk'],
  [('1 katori (~150 g)', 150, True, '')], [('arhar dal', 'Hindi')]),
 ('Moong dal (cooked)', 'dal', 'vegan', 85, 5.5, 12, 1.8, 3, 'Boiled, light tempering', 'moong dal, oil', [],
  [('1 katori (~150 g)', 150, True, '')], []),
 ('Rajma masala', 'dal', 'vegan', 120, 6, 15, 4, 5, 'Kidney beans in onion-tomato gravy', 'rajma, onion, tomato, oil', [],
  [('1 katori (~150 g)', 150, True, '')], []),
 ('Chole (chana masala)', 'dal', 'vegan', 150, 7, 20, 5, 6, 'Chickpeas in spiced gravy', 'chickpea, onion, tomato, oil', [],
  [('1 katori (~150 g)', 150, True, '')], [('chana masala', 'Hindi')]),
 ('Dal makhani', 'dal', 'veg', 140, 6, 14, 7, 4, 'Black lentils with butter and cream', 'urad dal, rajma, butter, cream', ['milk'],
  [('1 katori (~150 g)', 150, True, '')], []),
 ('Sambar', 'south', 'vegan', 55, 2.8, 8, 1.5, 2, 'Toor dal and vegetable stew', 'toor dal, vegetables, tamarind', [],
  [('1 katori (~150 g)', 150, True, '')], []),
 ('Kadhi', 'dal', 'veg', 75, 2.8, 7, 4, 0.5, 'Curd and besan gravy', 'curd, besan', ['milk'],
  [('1 katori (~150 g)', 150, True, '')], []),
 ('Soya chunks (dry)', 'dal', 'vegan', 345, 52, 33, 0.5, 13, 'Dry weight, before soaking', 'soy', ['soy'],
  [('1 small handful (~25 g dry)', 25, True, 'Absorbs water when cooked')], [('nutrela', 'Brand-generic')]),
 # ---- sabzi
 ('Palak paneer', 'sabzi', 'veg', 150, 7, 5, 11, 2, 'Spinach gravy with paneer', 'spinach, paneer, onion, oil', ['milk'],
  [('1 katori (~150 g)', 150, True, '')], []),
 ('Aloo gobi', 'sabzi', 'vegan', 85, 2.3, 10, 4, 2.5, 'Dry sabzi', 'potato, cauliflower, oil, onion', [],
  [('1 katori (~120 g)', 120, True, '')], []),
 ('Bhindi fry', 'sabzi', 'vegan', 100, 2, 8, 7, 3, 'Stir-fried okra', 'okra, oil, onion', [],
  [('1 katori (~100 g)', 100, True, '')], [('okra', 'English'), ('lady finger', 'English')]),
 ('Mixed vegetable sabzi', 'sabzi', 'vegan', 80, 2.5, 8, 4, 2.8, 'Light gravy', 'mixed vegetables, oil, onion', [],
  [('1 katori (~120 g)', 120, True, '')], []),
 ('Paneer (raw)', 'dairy', 'veg', 265, 18, 1.2, 20.8, 0, 'Fresh cottage cheese', 'paneer', ['milk'],
  [('1 serving (~50 g)', 50, True, ''), ('100 g', 100, False, '')], [('cottage cheese', 'English')]),
 ('Paneer bhurji', 'dairy', 'veg', 230, 14, 5, 17, 1, 'Scrambled with onion-tomato', 'paneer, onion, tomato, oil', ['milk'],
  [('1 katori (~100 g)', 100, True, '')], []),
 # ---- south / breakfast
 ('Idli', 'south', 'vegan', 135, 4, 28, 0.4, 1, 'Steamed rice-urad batter', 'rice, urad dal', [],
  [('1 idli (medium, ~40 g)', 40, True, '')], []),
 ('Plain dosa', 'south', 'vegan', 170, 4, 28, 4.5, 1.2, 'Tawa-cooked with a little oil', 'rice, urad dal, oil', [],
  [('1 dosa (~90 g)', 90, True, '')], []),
 ('Masala dosa', 'south', 'vegan', 160, 3.5, 24, 6, 1.8, 'Dosa with potato filling', 'rice, urad dal, potato, onion, oil', [],
  [('1 dosa (~180 g)', 180, True, '')], []),
 ('Poha (cooked)', 'breakfast', 'vegan', 130, 2.6, 22, 3.2, 1.5, 'Flattened rice tempered with oil, onion, peanuts', 'poha, onion, oil, peanut', ['peanut'],
  [('1 plate (~150 g)', 150, True, '')], [('flattened rice', 'English'), ('pohe', 'Marathi')]),
 ('Upma', 'breakfast', 'veg', 140, 3.5, 22, 4.5, 1.5, 'Semolina tempered with oil', 'semolina, oil, onion', ['gluten'],
  [('1 plate (~150 g)', 150, True, '')], [('rava upma', 'Hindi')]),
 ('Besan chilla', 'breakfast', 'vegan', 190, 8, 20, 8, 3.5, 'Gram flour pancake', 'besan, onion, oil', [],
  [('1 chilla (~70 g)', 70, True, '')], []),
 ('Oats (dry, rolled)', 'breakfast', 'vegan', 380, 13, 66, 7, 10, 'Dry weight', 'oats', ['gluten'],
  [('1 katori (~40 g dry)', 40, True, '')], []),
 # ---- egg / meat / fish
 ('Egg (boiled)', 'eggmeat', 'egg', 155, 13, 1.1, 11, 0, 'Hard boiled', 'egg', ['egg'],
  [('1 egg (~50 g)', 50, True, '')], [('anda', 'Hindi')]),
 ('Egg bhurji', 'eggmeat', 'egg', 170, 11, 3, 12, 0.5, 'Scrambled with onion, tomato, oil', 'egg, onion, tomato, oil', ['egg'],
  [('1 serving (2 eggs, ~130 g)', 130, True, '')], []),
 ('Chicken curry', 'eggmeat', 'nonveg', 140, 14, 4, 7.5, 0.8, 'Home-style gravy, with bone excluded', 'chicken, onion, tomato, oil', [],
  [('1 katori (~150 g)', 150, True, '')], []),
 ('Tandoori chicken', 'eggmeat', 'nonveg', 150, 20, 3, 6, 0.5, 'Marinated and grilled', 'chicken, curd, spices', ['milk'],
  [('1 leg piece (~120 g)', 120, True, '')], []),
 ('Fish curry', 'eggmeat', 'nonveg', 120, 13, 3, 6, 0.5, 'Coastal-style gravy', 'fish, onion, tomato, oil', ['fish'],
  [('1 katori (~150 g)', 150, True, '')], []),
 # ---- dairy / beverages
 ('Curd / Dahi (full-fat)', 'dairy', 'veg', 61, 3.5, 4.7, 3.3, 0, 'Set curd', 'milk', ['milk'],
  [('1 katori (~100 g)', 100, True, '')], [('yogurt', 'English'), ('dahi', 'Hindi')]),
 ('Milk (full-fat cow)', 'beverage', 'veg', 67, 3.2, 4.5, 4.1, 0, 'Plain', 'milk', ['milk'],
  [('1 glass (200 ml)', 200, True, 'Volume measure'), ('1 cup (150 ml)', 150, False, '')], [('doodh', 'Hindi')]),
 ('Masala chai (with milk and sugar)', 'beverage', 'veg', 50, 1.5, 6.5, 1.8, 0, 'Milk tea with ~1 tsp sugar per cup', 'milk, tea, sugar', ['milk'],
  [('1 cup (150 ml)', 150, True, '')], []),
 # ---- fruit
 ('Banana', 'fruit', 'vegan', 89, 1.1, 23, 0.3, 2.6, 'Raw, peeled', 'banana', [],
  [('1 medium banana (~100 g peeled)', 100, True, '')], [('kela', 'Hindi')]),
 ('Apple', 'fruit', 'vegan', 52, 0.3, 14, 0.2, 2.4, 'Raw, with skin', 'apple', [],
  [('1 medium apple (~150 g)', 150, True, '')], [('seb', 'Hindi')]),
 ('Mango', 'fruit', 'vegan', 60, 0.8, 15, 0.4, 1.6, 'Ripe flesh', 'mango', [],
  [('1 katori sliced (~150 g)', 150, True, '')], [('aam', 'Hindi')]),
 # ---- snacks / nuts / sweets
 ('Roasted chana', 'snack', 'vegan', 370, 20, 58, 5.5, 17, 'Dry roasted', 'chickpea', [],
  [('1 handful (~30 g)', 30, True, '')], [('bhuna chana', 'Hindi')]),
 ('Peanuts (roasted)', 'nuts', 'vegan', 590, 26, 16, 49, 8.5, 'Dry roasted, unsalted', 'peanut', ['peanut'],
  [('1 handful (~30 g)', 30, True, ''), ('1 tablespoon (~10 g)', 10, False, '')], [('moongfali', 'Hindi')]),
 ('Almonds', 'nuts', 'vegan', 580, 21, 22, 50, 12.5, 'Raw', 'almond', ['tree nut'],
  [('5 almonds (~6 g)', 6, False, 'About 1.2 g each'), ('10 almonds (~12 g)', 12, True, '')], [('badam', 'Hindi')]),
 ('Makhana (roasted)', 'snack', 'vegan', 350, 10, 77, 0.5, 14, 'Dry roasted fox nuts', 'makhana', [],
  [('1 cup (~30 g)', 30, True, '')], [('fox nuts', 'English'), ('lotus seeds', 'English')]),
 ('Samosa', 'snack', 'veg', 262, 4.5, 28, 15, 2.5, 'Deep fried potato-filled pastry', 'refined flour, potato, oil', ['gluten'],
  [('1 samosa (~60 g)', 60, True, '')], []),
 ('Gulab jamun', 'sweet', 'veg', 320, 4, 50, 11, 0.3, 'Fried milk-solid balls in sugar syrup', 'khoya, sugar, refined flour', ['milk', 'gluten'],
  [('1 piece (~40 g)', 40, True, '')], []),
 ('Jalebi', 'sweet', 'veg', 380, 2, 65, 13, 0.5, 'Deep-fried and soaked in syrup', 'refined flour, sugar, oil', ['gluten'],
  [('1 piece (~30 g)', 30, True, '')], []),
 # ---- fats
 ('Ghee', 'fat', 'veg', 900, 0, 0, 100, 0, 'Clarified butter', 'ghee', ['milk'],
  [('1 teaspoon (~5 g)', 5, True, ''), ('1 tablespoon (~14 g)', 14, False, '')], []),
 ('Sugar', 'fat', 'vegan', 400, 0, 100, 0, 0, 'White sugar', 'sugar', [],
  [('1 teaspoon (~4 g)', 4, True, '')], [('cheeni', 'Hindi')]),
]

VOLUME_FOODS = {'Milk (full-fat cow)', 'Masala chai (with milk and sugar)'}
