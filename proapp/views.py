from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.contrib.auth import logout
import random  
from django.http import HttpResponse
import requests
from django.conf import settings


def home_view(request):
    return render(request, 'home.html')  # Homepage

def login_view(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('nt_dashboard')
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials'})
    return render(request, 'login.html')


def signup_view(request):
    if request.method == "POST":
        username = request.POST['username']
        email = request.POST['email']
        password1 = request.POST['password1']
        password2 = request.POST['password2']

        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        def friendly_error(message):
            lower = message.lower()
            if 'too similar to the username' in lower:
                return 'This password is too similar to the username. Please choose a more unique password.'
            if 'too common' in lower:
                return 'This password is too common. Please choose something more personal and unique.'
            if 'minimum length' in lower or 'at least 8' in lower or 'too short' in lower:
                return 'This password is too short. Please use at least 8 characters, with a number and a symbol.'
            if 'numeric' in lower:
                return 'This password needs at least one number.'
            if 'not enough' in lower or 'special' in lower:
                return 'Please add a number and a special character to make your password stronger.'
            return message

        if password1 != password2:
            return render(request, 'signup.html', {'error': 'Passwords do not match. Please try again.'})
        if User.objects.filter(username__iexact=username).exists():
            return render(request, 'signup.html', {'error': 'This username is already taken. Please choose a different one.'})
        try:
            validate_password(password1, user=User(username=username, email=email))
        except ValidationError as exc:
            friendly_messages = [friendly_error(msg) for msg in exc.messages]
            return render(request, 'signup.html', {'error': ' '.join(dict.fromkeys(friendly_messages))})
        user = User.objects.create_user(username=username, email=email, password=password1)
        login(request, user)
        return redirect('nt_onboarding')
    return render(request, 'signup.html')
from django.contrib.auth.decorators import login_required

@login_required
def dashboard_view(request, username):
    if request.user.username != username:
        return redirect('login')  # Restrict access to other users' homepages
    return redirect('nt_dashboard')  # legacy URL now forwards to the new dashboard
def logout_view(request):
    logout(request)
    return redirect('home')  # Redirect to homepage after logout


# CALORIE CALCULATOR VIEW
# ----------------------
def calorie_calculator(request):
    if request.method == "POST":
        print("POST request received!")  # Debugging
        
        # Print received form data
        print(request.POST)

        try:
            age = int(request.POST.get('age'))
            height = float(request.POST.get('height'))
            weight = float(request.POST.get('weight'))
            gender = request.POST.get('gender')
            activity_level = float(request.POST.get('activity_level'))

            if gender == 'male':
                bmr = 10 * weight + 6.25 * height - 5 * age + 5
            else:
                bmr = 10 * weight + 6.25 * height - 5 * age - 161

            maintenance_calories = round(bmr * activity_level)
            weight_loss_calories = maintenance_calories - 500
            weight_gain_calories = maintenance_calories + 500

            return render(request, 'calorie_result.html', {
                'maintenance_calories': maintenance_calories,
                'weight_loss_calories': weight_loss_calories,
                'weight_gain_calories': weight_gain_calories,
                'age': age,
                'height': height,
                'weight': weight,
                'gender': gender,
                'activity_level': activity_level
            })

        except Exception as e:
            print("Error:", e)  # Print error in the console
            return render(request, 'calorie_calculator.html', {'error': 'Invalid input! Please enter valid numbers.'})

    return render(request, 'calorie_calculator.html')

def calorie_result(request):
    results = request.session.get('calorie_results', None)
    if not results:
        return redirect('calorie_calculator')  # Redirect back if no data

    return render(request, 'calorie_result.html', results)



FOOD_ITEMS = {
    "breakfast": [
        {"name": "Oats with Milk", "calories": 300},
        {"name": "Poha", "calories": 250},
        {"name": "Paratha with Curd", "calories": 350},
        {"name": "Egg Bhurji with Roti", "calories": 400},
        {"name": "Idli with Sambar", "calories": 275},
        {"name": "Upma", "calories": 300},
        {"name": "Dosa with Chutney", "calories": 350},
        {"name": "Sprouts Salad", "calories": 200},
        {"name": "Paneer Bhurji with Toast", "calories": 350},
        {"name": "Banana Shake", "calories": 250},
        {"name": "Aloo Poha", "calories": 270},
        {"name": "Vegetable Daliya", "calories": 280},
        {"name": "Methi Paratha with Curd", "calories": 320},
        {"name": "Besan Chilla with Chutney", "calories": 300},
        {"name": "Egg Toast", "calories": 350}
    ],
    "lunch": [
        {"name": "Roti with Dal & Bhindi Sabzi", "calories": 500},
        {"name": "Roti with Rajma & Jeera Rice", "calories": 550},
        {"name": "Roti with Chole & Salad", "calories": 500},
        {"name": "Roti with Paneer Butter Masala", "calories": 600},
        {"name": "Roti with Aloo Gobhi & Dal", "calories": 550},
        {"name": "Rice with Sambar & Curd", "calories": 500},
        {"name": "Roti with Baingan Bharta & Dal", "calories": 450},
        {"name": "Roti with Lauki Chana Dal", "calories": 480},
        {"name": "Roti with Mix Veg & Masoor Dal", "calories": 500},
        {"name": "Roti with Methi Aloo & Dal Tadka", "calories": 520},
        {"name": "Roti with Bhindi Fry & Moong Dal", "calories": 500},
        {"name": "Rice with Dal Makhani & Salad", "calories": 600},
        {"name": "Roti with Shahi Paneer & Salad", "calories": 650},
        {"name": "Roti with Egg Curry & Salad", "calories": 550},
        {"name": "Mutton Curry with Roti & Rice", "calories": 750},
        {"name": "Chicken Curry with Roti & Salad", "calories": 700},
        {"name": "Kadhi Chawal with Papad", "calories": 500},
        {"name": "Palak Paneer with Roti & Curd", "calories": 550},
        {"name": "Veg Biryani with Raita & Salad", "calories": 600}
    ],
    "dinner": [
        {"name": "Roti with Dal & Bhindi Fry", "calories": 480},
        {"name": "Roti with Aloo Tamatar Sabzi & Dal", "calories": 500},
        {"name": "Roti with Gobi Matar Sabzi & Salad", "calories": 480},
        {"name": "Roti with Lauki Chana Dal & Salad", "calories": 500},
        {"name": "Roti with Palak Paneer & Salad", "calories": 550},
        {"name": "Roti with Tinda Sabzi & Moong Dal", "calories": 490},
        {"name": "Roti with Baingan Bharta & Dal Tadka", "calories": 500},
        {"name": "Roti with Methi Thepla & Curd", "calories": 450},
        {"name": "Roti with Mix Veg & Masoor Dal", "calories": 500},
        {"name": "Roti with Tandoori Chicken & Salad", "calories": 650},
        {"name": "Roti with Rajma Masala & Curd", "calories": 520},
        {"name": "Roti with Kadhi & Rice", "calories": 500},
        {"name": "Roti with Dal Makhani & Salad", "calories": 600},
        {"name": "Roti with Fish Curry & Salad", "calories": 650},
        {"name": "Roti with Egg Bhurji & Curd", "calories": 500},
        {"name": "Khichdi with Ghee & Papad", "calories": 550},
        {"name": "Dal Khichdi with Salad & Pickle", "calories": 500},
        {"name": "Curd Rice with Salad", "calories": 450}
    ],
    "snacks": [
        {"name": "Fruit Salad", "calories": 200},
        {"name": "Roasted Chana", "calories": 250},
        {"name": "Masala Corn", "calories": 220},
        {"name": "Greek Yogurt with Nuts", "calories": 300},
        {"name": "Protein Shake", "calories": 350},
        {"name": "Hummus with Veggies", "calories": 280},
        {"name": "Bhel Puri", "calories": 350},
        {"name": "Dry Fruits & Nuts", "calories": 400},
        {"name": "Chana Chaat", "calories": 300},
        {"name": "Sprout Chaat", "calories": 250},
        {"name": "Makhana (Fox Nuts)", "calories": 180},
        {"name": "Coconut Water with Nuts", "calories": 150},
        {"name": "Peanut Chikki", "calories": 350},
        {"name": "Moong Dal Pakora", "calories": 450}
    ]
}


def generate_diet_plan(calories, meals):
    meal_ratios = {"breakfast": 0.3, "lunch": 0.4, "dinner": 0.3}
    
    diet_plan = {}
    for meal, ratio in meal_ratios.items():
        meal_calories = int(calories * ratio)
        meal_items = []
        total_cals = 0
        available_foods = FOOD_ITEMS[meal]  # Get list of food items
        
        random.shuffle(available_foods)  # Shuffle to avoid repetition
        for food in available_foods:
            if total_cals + food["calories"] <= meal_calories:
                meal_items.append(food)
                total_cals += food["calories"]
        
        diet_plan[meal] = meal_items

    return diet_plan



def diet_plan_view(request):
    if request.method == "POST":
        calories = int(request.POST.get("calories"))
        meals = int(request.POST.get("meals_count"))
        diet_plan = generate_diet_plan(calories, meals)
        return render(request, "diet_plan.html", {"diet_plan": diet_plan, "user_calories": calories})
    return render(request, "diet_form.html")




import random

def generate_workout_plan(frequency, experience, goal, equipment, muscle_groups, duration):
    # Define a structured workout plan with better variety
    workout_exercises = {
        "Push": ["Bench Press (4x8)", "Overhead Press (3x10)", "Dips (3x12)", "Triceps Pushdown (3x12)"],
        "Pull": ["Pull-ups (3x8)", "Deadlifts (4x6)", "Bent-over Rows (3x10)", "Face Pulls (3x12)"],
        "Legs": ["Squats (4x8)", "Lunges (3x12 each leg)", "Leg Press (3x10)", "Hamstring Curls (3x12)"],
        "Chest": ["Bench Press (4x8)", "Incline Dumbbell Press (3x10)", "Chest Flys (3x12)"],
        "Back": ["Pull-ups (3x8)", "Deadlifts (4x6)", "Lat Pulldown (3x10)"],
        "Arms": ["Bicep Curls (3x12)", "Triceps Dips (3x12)", "Hammer Curls (3x10)", "Skull Crushers (3x10)"],
        "Shoulders": ["Overhead Press (3x10)", "Lateral Raises (3x12)", "Arnold Press (3x10)"],
        "Core": ["Planks (3x30s)", "Leg Raises (3x12)", "Russian Twists (3x20)"],
        "Full Body": ["Burpees (3x15)", "Kettlebell Swings (3x12)", "Snatches (3x8)", "Clean and Press (3x10)"]
    }

    # Adjust difficulty based on experience level
    experience_modifiers = {
        "beginner": {"sets": 3, "reps": "8-12", "rest": "60s"},
        "intermediate": {"sets": 4, "reps": "6-10", "rest": "45s"},
        "advanced": {"sets": 5, "reps": "4-8", "rest": "30s"},
    }

    # Get experience-based parameters
    mod = experience_modifiers.get(experience, experience_modifiers["beginner"])

    # Create a structured plan
    plan = {}
    training_splits = {
        3: ["Full Body", "Upper Body", "Lower Body"],
        4: ["Push", "Pull", "Legs", "Core"],
        5: ["Push", "Pull", "Legs", "Arms", "Conditioning"],
        6: ["Chest", "Back", "Legs", "Arms", "Shoulders", "Core"]
    }

    split = training_splits.get(frequency, ["Full Body"] * frequency)

    for i in range(frequency):
        muscle_group = split[i % len(split)]
        if muscle_group not in workout_exercises:
            continue  # Skip if muscle group is missing

        exercises = random.sample(workout_exercises[muscle_group], min(3, len(workout_exercises[muscle_group])))
        formatted_exercises = [f"{ex} | {mod['sets']} sets x {mod['reps']} reps | Rest: {mod['rest']}" for ex in exercises]

        plan[f"Day {i+1} - {muscle_group} Focus"] = formatted_exercises

    return plan




def workout_form_view(request):
    return render(request, 'workout_form.html')  

def workout_plan_view(request):
    if request.method == "POST":
        print(request.POST)  # Debugging line to check POST data
        
        workout_days = request.POST.get("workout_frequency")  # Make sure the form input name matches
        
        if not workout_days:
            return HttpResponse("Invalid input. Please select workout days.", status=400)

        try:
            workout_days = int(workout_days)
        except ValueError:
            return HttpResponse("Invalid input format.", status=400)

        # Dummy values for other required parameters
        experience = "beginner"  
        goal = "muscle_gain"
        equipment = "bodyweight"
        muscle_groups = ["Chest", "Back", "Legs", "Arms", "Shoulders", "Core", "Full Body"]
        duration = 30  

        workout_plan = generate_workout_plan(workout_days, experience, goal, equipment, muscle_groups, duration)
        return render(request, "workout_plan.html", {"workout_plan": workout_plan})

    return render(request, "workout_form.html")  




def food_search(request):
    query = request.GET.get("query", "").strip()  # Get search input
    food_data = None

    if query:
        url = "https://trackapi.nutritionix.com/v2/natural/nutrients"
        headers = {
            "x-app-id": settings.NUTRITIONIX_APP_ID,
            "x-app-key": settings.NUTRITIONIX_API_KEY,
            "Content-Type": "application/json"
        }
        data = {"query": query}

        try:
            response = requests.post(url, headers=headers, json=data, timeout=8)
            if response.status_code == 200:
                food_data = response.json()
        except requests.RequestException:
            food_data = None

    return render(request, "food_search.html", {"food_data": food_data, "query": query})




BASE_URL = "https://exercisedb.p.rapidapi.com/exercises"

def get_workout(request):
    exercises = []
    if request.method == "POST":
        body_part = request.POST["body_part"]
        
        url = f"{BASE_URL}/bodyPart/{body_part}"
        headers = {
            "x-rapidapi-key": settings.EXERCISEDB_API_KEY,
            "x-rapidapi-host": "exercisedb.p.rapidapi.com"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=8)
            exercises = response.json() if response.status_code == 200 else []
        except requests.RequestException:
            exercises = []
        
    return render(request, "workout.html", {"exercises": exercises})


from django.shortcuts import render, redirect
from .models import WorkoutLog
from .forms import WorkoutLogForm
from django.contrib.auth.decorators import login_required

@login_required
def log_workout(request):
    if request.method == 'POST':
        form = WorkoutLogForm(request.POST)
        if form.is_valid():
            workout = form.save(commit=False)
            workout.user = request.user  
            workout.date = now()
            # 🔴 If the date is missing, return an error
              

            workout.save()
            return redirect('workout_history')
    else:
        form = WorkoutLogForm()
    
    return render(request, 'log_workout.html', {'form': form})

@login_required
def workout_history(request):
    return redirect('nt_workout_history')


from django.utils.timezone import now, timedelta
from django.http import JsonResponse
from .models import WorkoutLog

def streak_data(request):
    workouts = WorkoutLog.objects.values_list("date", flat=True).order_by("date")
    
    # Convert workout dates to a set for quick lookup
    workout_dates = set(workouts)
    
    # Calculate streak
    streak = 0
    today = now().date()
    
    for i in range(30):  # Check past 30 days
        if today - timedelta(days=i) in workout_dates:
            streak += 1
        else:
            break  # Streak ends if a day is missing
    
    return JsonResponse({
        "streak": streak,
        "workout_dates": [date.strftime("%Y-%m-%d") for date in workout_dates]
    })



from django.db.models import Sum, Count
from django.utils.timezone import now, timedelta
from django.http import JsonResponse
from .models import WorkoutLog

def progress_data(request):
    # Get past 30 days data
    start_date = now().date() - timedelta(days=30)
    workouts = WorkoutLog.objects.filter(date__gte=start_date)

    # Group by date & sum weights
    weight_data = workouts.values("date").annotate(total_weight=Sum("weight")).order_by("date")

    # Count workouts per week
    workout_frequency = workouts.extra({'week': "strftime('%%Y-%%W', date)"}).values("week").annotate(count=Count("id"))

    # Count exercise types
    exercise_counts = workouts.values("exercise_name").annotate(count=Count("id"))

    return JsonResponse({
        "weight_data": [{"date": w["date"].strftime("%Y-%m-%d"), "total_weight": w["total_weight"] or 0} for w in weight_data],
        "workout_frequency": [{"week": w["week"], "count": w["count"]} for w in workout_frequency],
        "exercise_distribution": [{"exercise": e["exercise_name"], "count": e["count"]} for e in exercise_counts]
    })

from django.shortcuts import render

def workout_graphs(request):
    return render(request, "workout_graphs.html")


from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import MealLog, DietGoal, StreakTracker
from datetime import date, timedelta

@login_required
def log_meal(request):
    if request.method == 'POST':
        food_name = request.POST.get('food_name')
        calories = float(request.POST.get('calories', 0))
        protein = float(request.POST.get('protein', 0))
        carbs = float(request.POST.get('carbs', 0))
        fats = float(request.POST.get('fats', 0))

        MealLog.objects.create(
            user=request.user,
            food_name=food_name,
            calories=calories,
            protein=protein,
            carbs=carbs,
            fats=fats
        )
        update_streak(request.user)
        return JsonResponse({'message': 'Meal logged successfully'})
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def get_progress(request):
    meals = MealLog.objects.filter(user=request.user, date=date.today())
    total_calories = sum(meal.calories for meal in meals)
    total_protein = sum(meal.protein for meal in meals)
    total_carbs = sum(meal.carbs for meal in meals)
    total_fats = sum(meal.fats for meal in meals)

    goals = DietGoal.objects.filter(user=request.user).first()
    goal_calories = goals.daily_calories if goals else 0
    goal_protein = goals.protein_goal if goals else 0
    goal_carbs = goals.carbs_goal if goals else 0
    goal_fats = goals.fats_goal if goals else 0

    return JsonResponse({
        'total_calories': total_calories, 'goal_calories': goal_calories,
        'total_protein': total_protein, 'goal_protein': goal_protein,
        'total_carbs': total_carbs, 'goal_carbs': goal_carbs,
        'total_fats': total_fats, 'goal_fats': goal_fats
    })

@login_required
def get_streak(request):
    streak = StreakTracker.objects.filter(user=request.user).first()
    return JsonResponse({'current_streak': streak.streak_count if streak else 0})

def update_streak(user, today=None):
    today = date.today() if today is None else today
    streak, created = StreakTracker.objects.get_or_create(user=user)

    if streak.last_logged_date == today:
        return

    if streak.last_logged_date is None:
        streak.streak_count = 1
    elif (today - streak.last_logged_date).days == 1:
        streak.streak_count += 1
    else:
        streak.streak_count = 1

    streak.last_logged_date = today
    streak.save()

from django.shortcuts import render, redirect
from .models import MealLog
from .forms import MealLogForm

@login_required
def meal_log_view(request):
    if request.method == 'POST':
        form = MealLogForm(request.POST)
        if form.is_valid():
            meal = form.save(commit=False)
            meal.user = request.user
            meal.save()
            return redirect('meal_log')  # Redirect after saving
    else:
        form = MealLogForm()

    meals = MealLog.objects.filter(user=request.user)  # only this user's logs
    return render(request, 'meal_log.html', {'form': form, 'meals': meals})
