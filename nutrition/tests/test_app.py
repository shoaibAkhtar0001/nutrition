import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from nutrition import services
from nutrition.models import (Exercise, Food, MealEntry, UserProfile, WaterEntry, WeightEntry, WorkoutPlan,
                              WorkoutSession, WorkoutSessionExercise)

PW = 'Sturdy-pass-4821'


def make_user(name, **profile):
    u = User.objects.create_user(name, f'{name}@example.com', PW)
    p = services.get_profile(u)
    defaults = dict(date_of_birth=date(1995, 5, 5), height_cm=Decimal('170'), weight_kg=Decimal('70'),
                    sex='male', goal='maintain', diet_pattern='veg', onboarded=True)
    defaults.update(profile)
    for k, v in defaults.items():
        setattr(p, k, v)
    p.save()
    services.apply_computed_targets(p)
    return u


class BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_foods', verbosity=0)
        call_command('seed_exercises', verbosity=0)
        cls.roti = Food.objects.get(slug='roti-chapati-plain')
        cls.a, cls.b = make_user('asha'), make_user('bala')

    def post_entry(self, client, food=None, qty='2', day=None, token=None, meal='lunch', unit=True):
        food = food or self.roti
        data = {'food_id': str(food.id), 'meal_type': meal, 'quantity': qty, 'date': (day or timezone.localdate()).isoformat(),
                'token': token or uuid.uuid4().hex}
        if unit:
            data['unit_id'] = food.serving_units.get(is_default=True).id
        return client.post(reverse('nt_entry_add'), data)


class AuthAndOnboarding(BaseCase):
    def test_private_pages_require_login(self):
        for name in ('nt_dashboard', 'nt_journal', 'nt_food_search', 'nt_targets', 'nt_api'.replace('nt_api', 'nt_food_api')):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn('/login/', r['Location'])

    def test_non_onboarded_user_is_sent_to_onboarding(self):
        User.objects.create_user('newbie', password=PW)
        self.client.login(username='newbie', password=PW)
        r = self.client.get(reverse('nt_dashboard'))
        self.assertRedirects(r, reverse('nt_onboarding'))

    def test_onboarding_saves_profile_targets_and_weight(self):
        User.objects.create_user('nina', password=PW)
        self.client.login(username='nina', password=PW)
        r = self.client.post(reverse('nt_onboarding'), {
            'display_name': 'Nina', 'date_of_birth': '1992-03-04', 'sex': 'female', 'height_cm': '160', 'weight_kg': '58',
            'goal': 'lose', 'activity_level': 'light', 'diet_pattern': 'veg', 'meals_per_day': '4',
            'allergies_text': 'Peanut, Milk ', 'excluded_text': 'mushroom'})
        self.assertRedirects(r, reverse('nt_targets'))
        p = UserProfile.objects.get(user__username='nina')
        self.assertTrue(p.onboarded)
        self.assertEqual(p.allergies, ['peanut', 'milk'])
        self.assertTrue(1200 <= p.kcal_target <= 2500)
        self.assertEqual(WeightEntry.objects.filter(user=p.user).count(), 1)

    def test_onboarding_rejects_unrealistic_height(self):
        User.objects.create_user('tall', password=PW)
        self.client.login(username='tall', password=PW)
        r = self.client.post(reverse('nt_onboarding'), {'date_of_birth': '1992-03-04', 'height_cm': '20', 'weight_kg': '60',
                                                         'goal': 'lose', 'activity_level': 'light', 'diet_pattern': 'veg', 'meals_per_day': '4'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'between 90 and 230')

    def test_signup_rejects_weak_and_duplicate(self):
        r = self.client.post('/signup/', {'username': 'x1', 'email': 'a@b.co', 'password1': '123', 'password2': '123'})
        self.assertContains(r, 'too short')
        r = self.client.post('/signup/', {'username': 'ASHA', 'email': 'a@b.co', 'password1': PW, 'password2': PW})
        self.assertContains(r, 'already taken')

    def test_signup_logs_in_and_goes_to_onboarding(self):
        r = self.client.post('/signup/', {'username': 'fresh', 'email': 'f@x.co', 'password1': PW, 'password2': PW})
        self.assertRedirects(r, reverse('nt_onboarding'))


class FeaturePages(BaseCase):
    def setUp(self):
        self.client.login(username='asha', password=PW)

    def test_plan_page_loads(self):
        r = self.client.get(reverse('nt_plan'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Meal plan')

    def test_ai_coach_page_loads(self):
        r = self.client.get(reverse('nt_ai_coach'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'AI coach')

    def test_plan_page_shows_balanced_meal_anchors(self):
        r = self.client.get(reverse('nt_plan'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Greek yogurt + oats')
        self.assertContains(r, 'Dal + brown rice + sabzi')
        self.assertContains(r, 'Grilled chicken + veg + roti')

    def test_progress_page_loads(self):
        r = self.client.get(reverse('nt_progress'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Progress')
        self.assertContains(r, 'Muscle balance')

    def test_workout_plan_respects_registered_training_frequency(self):
        from nutrition import services
        profile = services.get_profile(self.a)

        profile.activity_level = 'light'
        plan = services.suggest_workout_plan(profile)
        self.assertEqual(len(plan), 3)
        self.assertTrue(any('strength' in item['focus'].lower() for item in plan))

        profile.activity_level = 'moderate'
        plan = services.suggest_workout_plan(profile)
        self.assertEqual(len(plan), 4)

        profile.activity_level = 'high'
        plan = services.suggest_workout_plan(profile)
        self.assertEqual(len(plan), 5)

    def test_exercise_library_loads_and_filters(self):
        r = self.client.get(reverse('nt_exercises'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'For You')
        self.assertContains(r, 'Explore')
        self.assertContains(r, 'My Workouts')
        self.assertContains(r, 'Push-ups')

        filtered = self.client.get(reverse('nt_exercises') + '?body_part=legs&difficulty=beginner&exercise_type=strength')
        self.assertContains(filtered, 'Squats')
        self.assertContains(filtered, 'Calf Raises')
        self.assertNotContains(filtered, 'Bench Press')

    def test_workout_plan_save_inserts_exercise(self):
        exercise = Exercise.objects.get(slug='squats')
        r = self.client.post(reverse('nt_save_workout_exercise', args=[exercise.slug]), {'sets': '4', 'reps': '8-10', 'rest_seconds': '60'})
        self.assertRedirects(r, reverse('nt_exercise_detail', args=[exercise.slug]))
        self.assertTrue(self.a.workout_plans.exists())
        self.assertEqual(self.a.workout_plans.get().exercises.count(), 1)


class LoggingTests(BaseCase):
    def setUp(self):
        self.client.login(username='asha', password=PW)

    def test_log_recalculates_dashboard_totals(self):
        self.post_entry(self.client, qty='2')
        e = MealEntry.objects.get()
        self.assertEqual(e.amount_base, Decimal('80.00'))
        self.assertEqual(e.kcal, Decimal('237.60'))
        r = self.client.get(reverse('nt_dashboard'))
        self.assertEqual(r.context['totals'].kcal, Decimal('237.60'))

    def test_double_submit_with_same_token_creates_one_entry(self):
        tok = 'abc123'
        self.post_entry(self.client, token=tok)
        self.post_entry(self.client, token=tok)
        self.assertEqual(MealEntry.objects.count(), 1)

    def test_invalid_quantity_is_rejected(self):
        for q in ('0', '-3', 'abc', '99999'):
            self.post_entry(self.client, qty=q)
        self.assertEqual(MealEntry.objects.count(), 0)

    def test_unit_from_another_food_rejected(self):
        rice = Food.objects.get(slug='steamed-rice-white-cooked')
        r = self.client.post(reverse('nt_entry_add'), {
            'food_id': str(self.roti.id), 'meal_type': 'lunch', 'quantity': '1', 'date': timezone.localdate().isoformat(),
            'unit_id': rice.serving_units.first().id, 'token': 'z'})
        self.assertEqual(MealEntry.objects.count(), 0)

    def test_edit_recalculates_and_delete_removes(self):
        self.post_entry(self.client, qty='1')
        e = MealEntry.objects.get()
        self.client.post(reverse('nt_entry_edit', args=[e.pk]), {'meal_type': 'dinner', 'quantity': '3',
                                                                 'unit_id': self.roti.serving_units.get(is_default=True).id})
        e.refresh_from_db()
        self.assertEqual((e.meal_type, e.kcal), ('dinner', Decimal('356.40')))
        self.client.post(reverse('nt_entry_delete', args=[e.pk]))
        self.assertEqual(MealEntry.objects.count(), 0)

    def test_history_is_a_snapshot_and_survives_food_deletion(self):
        self.post_entry(self.client)
        Food.objects.filter(pk=self.roti.pk).delete()
        e = MealEntry.objects.get()
        self.assertIsNone(e.food)
        self.assertEqual(e.food_name, 'Roti / Chapati (plain)')
        self.assertEqual(self.client.get(reverse('nt_journal')).status_code, 200)

    def test_copy_yesterday(self):
        y = timezone.localdate() - timedelta(days=1)
        self.post_entry(self.client, day=y)
        self.client.post(reverse('nt_entry_copy'), {'meal_type': 'lunch', 'date': timezone.localdate().isoformat()})
        self.assertEqual(MealEntry.objects.filter(date=timezone.localdate()).count(), 1)

    def test_date_boundary_entries_stay_on_their_own_day(self):
        d = date(2026, 3, 31)
        self.post_entry(self.client, day=d)
        self.post_entry(self.client, day=d + timedelta(days=1))
        r = self.client.get(reverse('nt_journal') + '?date=2026-03-31')
        self.assertEqual(r.context['summary']['count'], 1)

    def test_garbage_date_param_falls_back_to_today(self):
        r = self.client.get(reverse('nt_journal') + '?date=not-a-date')
        self.assertEqual(r.context['day'], timezone.localdate())

    def test_water_and_weight(self):
        self.client.post(reverse('nt_water_add'), {'ml': '250'})
        self.client.post(reverse('nt_water_add'), {'ml': '-5'})
        self.client.post(reverse('nt_weight_add'), {'kg': '69.4'})
        self.client.post(reverse('nt_weight_add'), {'kg': '69.0'})  # same day: update, not duplicate
        self.assertEqual(WaterEntry.objects.filter(user__username='asha').count(), 1)
        self.assertEqual(WeightEntry.objects.filter(user__username='asha', date=timezone.localdate()).get().weight_kg, Decimal('69.0'))


class IsolationTests(BaseCase):
    def test_user_cannot_edit_delete_or_see_other_users_entries(self):
        self.client.login(username='asha', password=PW)
        self.post_entry(self.client)
        entry = MealEntry.objects.get()
        self.client.logout()
        self.client.login(username='bala', password=PW)
        self.assertEqual(self.client.post(reverse('nt_entry_delete', args=[entry.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('nt_entry_edit', args=[entry.pk]), {'meal_type': 'lunch', 'quantity': '9'}).status_code, 404)
        r = self.client.get(reverse('nt_journal'))
        self.assertEqual(r.context['summary']['count'], 0)
        self.assertEqual(MealEntry.objects.count(), 1)

    def test_custom_food_is_private_to_owner(self):
        mine = Food.objects.create(name='Secret ladoo', slug='secret-ladoo', category='sweet', kcal=400, protein_g=5, carbs_g=60,
                                   fat_g=15, source='user entered', owner=self.a)
        self.client.login(username='bala', password=PW)
        self.assertEqual(self.client.get(reverse('nt_food_detail', args=[mine.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('nt_food_api') + '?q=secret').json()['results'], [])
        self.post_entry(self.client, food=mine, unit=False)
        self.assertEqual(MealEntry.objects.count(), 0)

    def test_search_api_flags_foods_that_violate_the_users_rules(self):
        p = services.get_profile(self.a); p.allergies = ['peanut']; p.save()
        self.client.login(username='asha', password=PW)
        res = self.client.get(reverse('nt_food_api') + '?q=poha').json()['results']
        self.assertTrue(res and res[0]['blocked'])

    def test_suggestions_respect_hard_constraints(self):
        p = services.get_profile(self.a); p.allergies = ['milk']; p.diet_pattern = 'vegan'; p.save()
        from nutrition import engine
        totals = engine.daily_summary(self.a, timezone.localdate())['totals']
        for s in services.suggest_next(self.a, p, totals, limit=50):
            self.assertFalse(engine.food_violations(s['food'], p), s['food'].name)


class GeminiCoachTests(BaseCase):
    def setUp(self):
        self.client.login(username='asha', password=PW)

    def test_gemini_service_reports_missing_key_configuration(self):
        from django.test import override_settings
        from nutrition.gemini_service import GeminiService

        self.assertTrue(GeminiService.is_configured())
        with override_settings(GEMINI_API_KEY='', GEMINI_MODEL=''):
            self.assertFalse(GeminiService.is_configured())

    def test_ai_chat_api_rejects_blank_messages(self):
        with self.assertRaises(ValueError):
            from nutrition.gemini_service import GeminiService
            GeminiService.validate_user_message('   ')

        response = self.client.post(reverse('nt_ai_chat_api'), data={'message': '   '}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_fallback_replies_are_specific_to_the_question(self):
        from nutrition.gemini_service import GeminiService

        dinner_reply = GeminiService.fallback_reply(self.a, 'What should I eat for dinner today?')
        gut_reply = GeminiService.fallback_reply(self.a, 'What can I eat for gut health?')

        self.assertNotEqual(dinner_reply, gut_reply)
        self.assertIn('dinner', dinner_reply.lower())
        self.assertIn('gut', gut_reply.lower())

    def test_build_prompt_drops_the_current_question_from_history(self):
        from nutrition.gemini_service import GeminiService

        prompt = GeminiService._build_prompt(
            'What should I eat for dinner today?',
            self.a,
            [
                type('Item', (), {'role': 'USER', 'content': 'What should I eat for dinner today?'})(),
                type('Item', (), {'role': 'ASSISTANT', 'content': 'Have dinner earlier'})(),
            ],
        )

        self.assertNotIn('What should I eat for dinner today?\n\nConversation history:\nUSER: What should I eat for dinner today?', prompt)
        self.assertIn('ASSISTANT: Have dinner earlier', prompt)

    def test_ai_chat_api_hides_provider_503_details_and_uses_fallback(self):
        with mock.patch('nutrition.views.GeminiService.generate_reply', side_effect=RuntimeError("{'error': {'code': 503, 'message': 'This model is currently experiencing high demand.'}}")):
            response = self.client.post(reverse('nt_ai_chat_api'), data={'message': 'How can I increase protein on a vegetarian diet?'}, content_type='application/json')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertIn('protein', payload['assistant_message'].lower())
        self.assertNotIn('high demand', payload['assistant_message'].lower())
        self.assertNotIn('code', payload['assistant_message'].lower())


class ExerciseFlowTests(BaseCase):
    def setUp(self):
        self.client.login(username='asha', password=PW)

    def test_exercise_detail_keeps_library_filters(self):
        exercise = Exercise.objects.get(slug='squats')
        response = self.client.get(reverse('nt_exercise_detail', args=[exercise.slug]) + '?back=%2Fexercises%2F%3Fbody_part%3Dlegs%26difficulty%3Dbeginner')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Back to library')
        self.assertContains(response, 'body_part=legs')
        self.assertContains(response, 'difficulty=beginner')

    def test_creating_and_resuming_workout_session(self):
        exercise = Exercise.objects.get(slug='squats')
        session = WorkoutSession.objects.create(user=self.a, name='Leg day', status=WorkoutSession.Status.ACTIVE)
        WorkoutSessionExercise.objects.create(session=session, exercise=exercise, order=1, sets_target=4, reps='8-10', rest_seconds=60)

        response = self.client.get(reverse('nt_workout_session', args=[session.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Leg day')

        self.client.post(reverse('nt_workout_session', args=[session.pk]), {
            'exercise_index': '0',
            'set_1_reps': '10',
            'set_1_done': '1',
            'complete': '1',
        })
        session.refresh_from_db()
        self.assertEqual(session.status, WorkoutSession.Status.COMPLETED)

    def test_exercise_progress_and_history_load(self):
        exercise = Exercise.objects.get(slug='squats')
        session = WorkoutSession.objects.create(user=self.a, name='Leg day', status=WorkoutSession.Status.COMPLETED, completed_at=timezone.now())
        WorkoutSessionExercise.objects.create(session=session, exercise=exercise, order=1, sets_target=3, reps='8-10', rest_seconds=60,
                                            status=WorkoutSessionExercise.ExecutionStatus.COMPLETED, completed_sets=2,
                                            set_data=[{'set_number': 1, 'reps': '10', 'weight': '60', 'completed': True},
                                                      {'set_number': 2, 'reps': '10', 'weight': '60', 'completed': True}])

        history = self.client.get(reverse('nt_workout_history'))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, 'Leg day')

        progress = self.client.get(reverse('nt_exercise_progress', args=[exercise.slug]))
        self.assertEqual(progress.status_code, 200)
        self.assertContains(progress, exercise.name)

    def test_legacy_history_route_redirects_to_nutrition_history(self):
        session = WorkoutSession.objects.create(user=self.a, name='Leg day', status=WorkoutSession.Status.COMPLETED, completed_at=timezone.now())
        response = self.client.get('/history/')
        self.assertRedirects(response, reverse('nt_workout_history'))
        self.assertTrue(session.pk)

    def test_user_cannot_access_other_users_workout_session(self):
        other_user = User.objects.get(username='bala')
        session = WorkoutSession.objects.create(user=other_user, name='Secret workout', status=WorkoutSession.Status.ACTIVE)
        response = self.client.get(reverse('nt_workout_session', args=[session.pk]))
        self.assertEqual(response.status_code, 404)

    def test_workout_plan_and_session_flow_stay_connected(self):
        exercise = Exercise.objects.get(slug='bench-press')
        plan = WorkoutPlan.objects.create(user=self.a, name='Upper body')
        plan.exercises.create(exercise=exercise, order=1, sets=3, reps='8-12', rest_seconds=60)
        response = self.client.get(reverse('nt_workouts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upper body')


class LegacyFixTests(BaseCase):
    def test_legacy_meal_log_requires_login_and_is_per_user(self):
        from proapp.models import MealLog
        self.assertEqual(self.client.get('/meal-log/').status_code, 302)
        MealLog.objects.create(user=self.b, food_name='BalaSecretMeal', calories=1, protein=1, carbs=1, fats=1)
        self.client.login(username='asha', password=PW)
        self.assertNotContains(self.client.get('/meal-log/'), 'BalaSecretMeal')
        self.client.post('/meal-log/', {'food_name': 'AshaMeal', 'calories': 100, 'protein': 5, 'carbs': 10, 'fats': 2})
        self.assertTrue(MealLog.objects.filter(user=self.a, food_name='AshaMeal').exists())

    def test_legacy_streak_logic_handles_first_of_month(self):
        from proapp import views
        from proapp.models import StreakTracker
        st = StreakTracker.objects.create(user=self.a, streak_count=3, last_logged_date=date(2026, 1, 31))
        views.update_streak(self.a, today=date(2026, 2, 1))
        st.refresh_from_db()
        self.assertEqual(st.streak_count, 4)

    def test_legacy_streak_logic_handles_same_day_without_double_count(self):
        from proapp import views
        from proapp.models import StreakTracker
        today = date(2026, 2, 1)
        st = StreakTracker.objects.create(user=self.a, streak_count=3, last_logged_date=today)
        views.update_streak(self.a, today=today)
        st.refresh_from_db()
        self.assertEqual(st.streak_count, 3)
