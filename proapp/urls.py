from django.urls import path
from . import views


urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('dashboard/<str:username>/', views.dashboard_view, name='dashboard'),
    path('calorie-calculator/', views.calorie_calculator, name='calorie_calculator'),# New route
    path('result/',views.calorie_result, name='calorie_result'),

    path('diet_form/',views.diet_plan_view,name='diet_form'),
    path('diet_plan/',views.diet_plan_view,name='diet_plan'),
    path('workout_form/',views.workout_form_view,name='workout_form'),
    path('workout_plan/',views.workout_plan_view,name='workout_plan'),
    path("food_search/", views.food_search, name="food_search"),
    path("workout/", views.get_workout, name="workout"),
     path('log/', views.log_workout, name='log_workout'),
    path('history/', views.workout_history, name='workout_history'),
    path('streak-data/', views.streak_data, name='streak_data'),
    path('progress-data/', views.progress_data, name='progress_data'),
    path('workout-graphs/',views.workout_graphs, name='workout_graphs'),
    path('meal-log/', views.meal_log_view, name='meal_log'),

   
]

urlpatterns += [
    path('logout/', views.logout_view, name='logout'),
]
