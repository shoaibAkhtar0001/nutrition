from django import forms
from .models import WorkoutLog

class WorkoutLogForm(forms.ModelForm):
    class Meta:
        model = WorkoutLog
        fields = ['exercise_name', 'sets', 'reps', 'weight', 'duration', 'intensity', 'notes']
        widgets = {
            'exercise_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Exercise Name'}),
            'sets': forms.NumberInput(attrs={'class': 'form-control'}),
            'reps': forms.NumberInput(attrs={'class': 'form-control'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Duration (minutes)'}),
            'intensity': forms.Select(attrs={'class': 'form-control'}, choices=[("Low", "Low"), ("Medium", "Medium"), ("High", "High")]),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes'}),
        }


from .models import MealLog

class MealLogForm(forms.ModelForm):
    class Meta:
        model = MealLog
        fields = ['food_name', 'calories', 'protein', 'carbs', 'fats']
