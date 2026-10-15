from django.contrib import admin

# Register your models here.

from .models import WorkoutLog
from .models import MealLog, DietGoal, StreakTracker

 


@admin.register(WorkoutLog)  # Better way to register the model
class WorkoutLogAdmin(admin.ModelAdmin):
    list_display = ("date", "exercise_name", "sets", "reps", "weight", "duration", "intensity")  # Columns in admin panel
    list_filter = ("date", "exercise_name", "intensity")  # Filter workouts easily
    search_fields = ("exercise_name",)  # Search workouts by name
    ordering = ["-date"]  # Show latest workouts first


from .models import MealLog, DietGoal, StreakTracker

admin.site.register(MealLog)
admin.site.register(DietGoal)
admin.site.register(StreakTracker)
