from django.db import models

# Create your models here.

from django.contrib.auth.models import User

class WorkoutLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    exercise_name = models.CharField(max_length=255)
    sets = models.IntegerField()
    reps = models.IntegerField()
    weight = models.FloatField(null=True, blank=True)  # Optional for bodyweight exercises
    duration = models.IntegerField(null=True, blank=True)  # In minutes
    intensity = models.CharField(max_length=50, choices=[("Low", "Low"), ("Medium", "Medium"), ("High", "High")])
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.exercise_name} ({self.date})"



class MealLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    food_name = models.CharField(max_length=255)
    calories = models.IntegerField()
    protein = models.FloatField()
    carbs = models.FloatField()
    fats = models.FloatField()

    def __str__(self):
        return f"{self.food_name} - {self.calories} kcal"

class DietGoal(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    daily_calories = models.IntegerField()
    protein_goal = models.FloatField()
    carbs_goal = models.FloatField()
    fats_goal = models.FloatField()
    weight_goal = models.FloatField()

    def __str__(self):
        return f"{self.user.username} - {self.daily_calories} kcal goal"

class StreakTracker(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    streak_count = models.IntegerField(default=0)
    last_logged_date = models.DateField(null=True, blank=True)

    def update_streak(self, today):
        if self.last_logged_date is None or (today - self.last_logged_date).days > 1:
            self.streak_count = 1
        else:
            self.streak_count += 1
        self.last_logged_date = today
        self.save()

    def __str__(self):
        return f"{self.user.username} - {self.streak_count} day streak"
