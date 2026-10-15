import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import engine, rules, services
from .forms import EntryForm, ProfileForm, TargetsForm
from .gemini_service import GeminiService
from .models import (AICoachConversation, AICoachMessage, Exercise, Food, MealEntry, WaterEntry, WeightEntry,
                     WorkoutPlan, WorkoutPlanExercise, WorkoutSession, WorkoutSessionExercise)


def _parse_day(raw):
    try:
        d = date.fromisoformat(raw) if raw else timezone.localdate()
    except ValueError:
        d = timezone.localdate()
    limit = timezone.localdate() + timedelta(days=1)
    return min(d, limit)


def onboarded_required(view):
    """Login + profile completed. Users without a profile are sent to onboarding."""
    @login_required
    def wrapper(request, *a, **kw):
        request.nt_profile = services.get_profile(request.user)
        if not request.nt_profile.onboarded:
            return redirect('nt_onboarding')
        return view(request, *a, **kw)
    wrapper.__name__ = view.__name__
    return wrapper


NAV = [('Home', 'nt_dashboard', 'home'), ('Food', 'nt_journal', 'utensils'), ('Plan', 'nt_plan', 'calendar'),
       ('Exercise Library', 'nt_exercises', 'dumbbell'), ('AI Coach', 'nt_ai_coach', 'message'), ('Progress', 'nt_progress', 'chart')]


def _ctx(request, active, **extra):
    return {'nav': NAV, 'active': active, 'profile': getattr(request, 'nt_profile', None), **extra}


def _exercise_progress_url(user=None):
    return reverse('nt_progress')


def _exercise_subnav(active='foryou'):
    normalized = 'foryou' if active in {'discover', 'foryou'} else 'explore' if active in {'library', 'explore'} else active
    return [
        {'label': 'For You', 'url': reverse('nt_exercises'), 'key': 'foryou'},
        {'label': 'Explore', 'url': reverse('nt_exercises') + '?view=explore', 'key': 'explore'},
        {'label': 'My Workouts', 'url': reverse('nt_workouts'), 'key': 'workouts'},
        {'label': 'History', 'url': reverse('nt_workout_history'), 'key': 'history'},
        {'label': 'Progress', 'url': _exercise_progress_url(), 'key': 'progress'},
    ]


def _recent_exercises_for_user(user):
    sessions = WorkoutSession.objects.filter(user=user, status=WorkoutSession.Status.COMPLETED).prefetch_related('exercise_entries__exercise')
    exercise_ids = []
    for session in sessions:
        for item in session.exercise_entries.all():
            if item.exercise_id not in exercise_ids:
                exercise_ids.append(item.exercise_id)
    qs = Exercise.objects.filter(is_active=True, pk__in=exercise_ids)
    if not qs.exists():
        qs = Exercise.objects.filter(is_active=True)[:6]
    return list(qs[:6])


def _get_existing_workout_session(user):
    return WorkoutSession.objects.filter(user=user, status=WorkoutSession.Status.ACTIVE).order_by('-updated_at').first()


# ------------------------------------------------------------- onboarding
@login_required
def onboarding(request):
    profile = services.get_profile(request.user)
    form = ProfileForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        profile = form.save()
        try:
            services.apply_computed_targets(profile)
        except ValueError:
            messages.error(request, 'We need your date of birth, height and weight to estimate targets.')
        else:
            profile.onboarded = True
            profile.save(update_fields=['onboarded'])
            WeightEntry.objects.update_or_create(user=request.user, date=timezone.localdate(),
                                                 defaults={'weight_kg': profile.weight_kg})
            return redirect('nt_targets')
    return render(request, 'nt/onboarding.html', {'form': form, 'nav': [], 'active': ''})


@login_required
def targets(request):
    """Review (and optionally edit) the estimated targets, with the reasoning shown."""
    profile = services.get_profile(request.user)
    if not profile.onboarded:
        return redirect('nt_onboarding')
    request.nt_profile = profile
    age = rules.age_from_dob(profile.date_of_birth)
    computed = rules.compute_targets(weight_kg=profile.weight_kg, height_cm=profile.height_cm, age=age,
                                     sex=profile.sex, activity=profile.activity_level, goal=profile.goal)
    form = TargetsForm(request.POST or None, instance=profile)
    if request.method == 'POST':
        if 'reset' in request.POST:
            profile.targets_customised = False
            services.apply_computed_targets(profile)
            messages.success(request, 'Targets reset to the estimated values.')
            return redirect('nt_targets')
        if form.is_valid():
            p = form.save(commit=False)
            p.targets_customised = True
            p.save()
            messages.success(request, 'Your targets were saved.')
            return redirect('nt_dashboard')
    return render(request, 'nt/targets.html', _ctx(request, 'settings', form=form, computed=computed))


@onboarded_required
def plan(request):
    profile = request.nt_profile
    today = timezone.localdate()
    summary = engine.daily_summary(request.user, today)
    suggestions = services.suggest_next(request.user, profile, summary['totals'], limit=3)

    filtered_suggestions = []
    for rec in suggestions:
        name = (rec['food'].name or '').lower()
        if any(keyword in name for keyword in ['biryani', 'fried', 'pizza', 'paratha', 'pulao', 'korma', 'butter']):
            continue
        filtered_suggestions.append(rec)

    def item(label, fallback_name, fallback_kcal, fallback_protein):
        index = {'Breakfast': 0, 'Lunch': 1, 'Dinner': 2}.get(label)
        defaults = {
            'Breakfast': {'food': 'Greek yogurt + oats', 'kcal': 260, 'protein': 22},
            'Lunch': {'food': 'Dal + brown rice + sabzi', 'kcal': 440, 'protein': 24},
            'Dinner': {'food': 'Grilled chicken + veg + roti', 'kcal': 480, 'protein': 32},
        }
        if index is not None and index < len(filtered_suggestions):
            rec = filtered_suggestions[index]
            thresholds = {'Breakfast': (18, 170), 'Lunch': (20, 300), 'Dinner': (25, 300)}
            min_protein, min_kcal = thresholds.get(label, (15, 150))
            if rec['nutrients'].protein_g >= Decimal(str(min_protein)) and rec['nutrients'].kcal >= Decimal(str(min_kcal)):
                return {'food': rec['food'].name, 'kcal': int(rec['nutrients'].kcal), 'protein': int(rec['nutrients'].protein_g)}
        fallback = defaults.get(label, {'food': fallback_name, 'kcal': fallback_kcal, 'protein': fallback_protein})
        return {'food': fallback['food'], 'kcal': fallback['kcal'], 'protein': fallback['protein']}

    plan_cards = [
        {'title': 'Breakfast', 'subhead': 'Protein-first start', 'item': item('Breakfast', 'Greek yogurt + oats', 260, 22)},
        {'title': 'Lunch', 'subhead': 'Balanced midday meal', 'item': item('Lunch', 'Dal + brown rice + sabzi', 440, 24)},
        {'title': 'Dinner', 'subhead': 'Keep it steady', 'item': item('Dinner', 'Grilled chicken + veg + roti', 480, 32)},
    ]
    progress_pct = 0
    if profile.kcal_target:
        progress_pct = min(100, (summary['totals'].kcal / Decimal(profile.kcal_target)) * Decimal('100'))
    return render(request, 'nt/plan.html', _ctx(request, 'calendar', plan=plan_cards, today=today,
                                               total_kcal=summary['totals'].kcal, target_kcal=profile.kcal_target or 0,
                                               progress_pct=progress_pct))


@onboarded_required
def ai_coach(request):
    profile = request.nt_profile
    today = timezone.localdate()
    summary = engine.daily_summary(request.user, today)
    totals = summary['totals']
    target_gap = Decimal(profile.kcal_target or 0) - totals.kcal
    coach_notes = []
    if summary['count'] == 0:
        coach_notes.append('Nothing logged yet today. Start with a protein-rich breakfast to anchor your day.')
    else:
        protein_goal = Decimal(profile.protein_target_g or 0)
        fibre_goal = Decimal(profile.fibre_target_g or 0)
        if totals.protein_g < protein_goal:
            coach_notes.append(f'Protein is {max(protein_goal - totals.protein_g, Decimal(0)):.0f} g below target; add dal, paneer, eggs, or yogurt.')
        if totals.fibre_g < fibre_goal:
            coach_notes.append('Fibre is lagging. Fruit, sabzi, beans and whole grains will help.')
        if target_gap > 0:
            coach_notes.append(f'You still have about {target_gap:.0f} kcal left for the day without overshooting target.')
        elif target_gap < 0:
            coach_notes.append('You are slightly above target today. A lighter dinner or a large water break can help you reset.')
        else:
            coach_notes.append('You are right on target for calories today. Keep it consistent.')

    coach_notes.append('Aim for 2-3 meals with a protein anchor and one produce-heavy side for better satiety.')
    conversations = AICoachConversation.objects.filter(user=request.user).order_by('-last_message_at')[:6]
    suggested_prompts = [
        'What should I eat for dinner today?',
        'How can I increase protein on a vegetarian diet?',
        'Summarize my nutrition today.',
        'Suggest affordable Indian meals.',
        'Help me plan a workout for today.'
    ]
    return render(request, 'nt/ai_coach.html', _ctx(request, 'message', coach_notes=coach_notes, totals=totals,
                                                    target_kcal=profile.kcal_target or 0, goal=profile.goal,
                                                    conversations=conversations,
                                                    suggested_prompts=suggested_prompts,
                                                    gemini_configured=GeminiService.is_configured()))


@login_required
@require_POST
def ai_chat_clear(request):
    conversation_id = request.POST.get('conversation_id')
    if conversation_id:
        AICoachConversation.objects.filter(user=request.user, pk=conversation_id).delete()
    else:
        AICoachConversation.objects.filter(user=request.user).delete()
    return JsonResponse({'ok': True, 'message': 'Conversation cleared.'})


@login_required
@require_POST
def ai_chat_api(request):
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else request.POST
    except (TypeError, ValueError):
        payload = request.POST

    if isinstance(payload, dict):
        raw_message = payload.get('message', '')
        conversation_id = payload.get('conversation_id')
    else:
        raw_message = request.POST.get('message', '')
        conversation_id = request.POST.get('conversation_id')

    try:
        message = GeminiService.validate_user_message(raw_message)
    except ValueError as exc:
        return JsonResponse({'ok': False, 'error': str(exc), 'provider_status': 'validation_error'}, status=400)

    if conversation_id:
        conversation = AICoachConversation.objects.filter(user=request.user, pk=conversation_id).first()
    else:
        conversation = None
    if conversation is None:
        conversation = AICoachConversation.objects.create(user=request.user, title=message[:60])

    AICoachMessage.objects.create(
        conversation=conversation,
        role=AICoachMessage.Role.USER,
        content=message,
        provider_status='queued',
    )
    conversation.title = (conversation.title or 'Nutrition chat') if len(conversation.title or '') > 0 else message[:60]
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=['title', 'last_message_at'])

    history = list(conversation.messages.order_by('created_at').all())[-8:]
    if history and history[-1].content.strip() == message.strip():
        history = history[:-1]
    try:
        if GeminiService.is_configured():
            reply = GeminiService.generate_reply(user=request.user, message=message, history=history)
            provider_status = 'configured'
        else:
            reply = GeminiService.fallback_reply(request.user, message)
            provider_status = 'unconfigured'
    except Exception as exc:
        safe_error = 'The AI coach is temporarily unavailable. Please try again in a moment.'
        reply = GeminiService.fallback_reply(request.user, message)
        provider_status = 'fallback_after_error'
        if reply is None:
            reply = safe_error
        AICoachMessage.objects.create(
            conversation=conversation,
            role=AICoachMessage.Role.ASSISTANT,
            content=reply,
            provider_status=provider_status,
        )
        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=['last_message_at'])
        return JsonResponse({
            'ok': True,
            'assistant_message': reply,
            'conversation_id': str(conversation.pk),
            'provider_status': provider_status,
            'message_id': str(AICoachMessage.objects.filter(conversation=conversation).order_by('-created_at').first().pk),
            'suggested_actions': [
                'What should I eat for dinner today?',
                'How can I increase protein on a vegetarian diet?',
                'Summarize my nutrition today.',
                'Suggest affordable Indian meals.',
                'Help me plan a workout for today.'
            ],
        })

    assistant_message = AICoachMessage.objects.create(
        conversation=conversation,
        role=AICoachMessage.Role.ASSISTANT,
        content=reply,
        provider_status=provider_status,
    )
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=['last_message_at'])
    return JsonResponse({
        'ok': True,
        'assistant_message': reply,
        'conversation_id': str(conversation.pk),
        'provider_status': provider_status,
        'message_id': str(assistant_message.pk),
        'suggested_actions': [
            'What should I eat for dinner today?',
            'How can I increase protein on a vegetarian diet?',
            'Summarize my nutrition today.',
            'Suggest affordable Indian meals.',
            'Help me plan a workout for today.'
        ],
    })


@onboarded_required
def progress(request):
    user = request.user
    today = timezone.localdate()
    history = []
    for offset in range(6, -1, -1):
        d = today - timedelta(days=offset)
        entries = MealEntry.objects.filter(user=user, date=d)
        kcal = sum((Decimal(str(e.kcal)) for e in entries), Decimal('0'))
        protein = sum((Decimal(str(e.protein_g)) for e in entries), Decimal('0'))
        water = sum(WaterEntry.objects.filter(user=user, date=d).values_list('ml', flat=True), 0)
        weight = WeightEntry.objects.filter(user=user, date=d).order_by('-created_at').first()
        history.append({'date': d, 'kcal': kcal, 'protein': protein, 'water': water, 'weight': weight.weight_kg if weight else None})
    max_kcal = max((item['kcal'] for item in history), default=Decimal('1'))
    for item in history:
        item['pct'] = 0 if max_kcal == 0 else min(100, (item['kcal'] / max_kcal) * Decimal('100'))

    muscle_totals = {}
    muscle_sessions = {}
    for entry in WorkoutSessionExercise.objects.filter(session__user=user, session__status=WorkoutSession.Status.COMPLETED).select_related('exercise', 'session'):
        completed_sets = [s for s in entry.set_data if s.get('completed')]
        if not completed_sets:
            continue
        base_value = len(completed_sets)
        for muscle_key in [entry.exercise.primary_muscle] + (entry.exercise.secondary_muscles or []):
            muscle_totals[muscle_key] = muscle_totals.get(muscle_key, 0) + base_value
            muscle_sessions.setdefault(muscle_key, set()).add(entry.session_id)

    muscle_balance = []
    if muscle_totals:
        max_muscle = max(muscle_totals.values())
        label_map = dict(Exercise.MuscleGroup.choices)
        for muscle_key, total in sorted(muscle_totals.items(), key=lambda x: (-x[1], x[0])):
            muscle_balance.append({
                'name': label_map.get(muscle_key, muscle_key.replace('_', ' ').title()),
                'sets': total,
                'sessions': len(muscle_sessions.get(muscle_key, set())),
                'pct': int((total / max_muscle) * 100) if max_muscle else 0,
            })

    most_trained = muscle_balance[0] if muscle_balance else None
    least_trained = muscle_balance[-1] if muscle_balance else None

    current_weight = WeightEntry.objects.filter(user=user).order_by('-date').first()
    return render(request, 'nt/progress.html', _ctx(request, 'chart', history=history, max_kcal=max_kcal,
                                                   current_weight=current_weight, total_days=len(history),
                                                   muscle_balance=muscle_balance, most_trained=most_trained,
                                                   least_trained=least_trained))


# ---------------------------------------------------------------- dashboard
@onboarded_required
def dashboard(request):
    profile, user, today = request.nt_profile, request.user, timezone.localdate()
    s = engine.daily_summary(user, today)
    totals = s['totals']
    water = sum(WaterEntry.objects.filter(user=user, date=today).values_list('ml', flat=True))
    latest_weight = WeightEntry.objects.filter(user=user).order_by('-date').first()
    first_weight = WeightEntry.objects.filter(user=user).order_by('date').first()
    week = services.week_consistency(user, today)

    def pct(used, target):
        return int(min(100, (Decimal(used) / Decimal(target) * 100))) if target else 0

    macros = [('Protein', totals.protein_g, profile.protein_target_g, 'g'), ('Carbs', totals.carbs_g, profile.carbs_target_g, 'g'),
              ('Fat', totals.fat_g, profile.fat_target_g, 'g'), ('Fibre', totals.fibre_g, profile.fibre_target_g, 'g')]
    ctx = _ctx(request, 'home', today=today, totals=totals, summary=s, water=water,
               kcal_pct=pct(totals.kcal, profile.kcal_target),
               ring_offset=round(326.7 * (1 - pct(totals.kcal, profile.kcal_target) / 100), 1),
               kcal_left=None if not profile.kcal_target else Decimal(profile.kcal_target) - totals.kcal,
               macros=[{'name': n, 'used': u, 'target': t, 'unit': un, 'pct': pct(u, t)} for n, u, t, un in macros],
               water_pct=pct(water, profile.water_target_ml), week=week, week_logged=sum(d['logged'] for d in week),
               suggestions=services.suggest_next(user, profile, totals),
               workout_plan=services.suggest_workout_plan(profile, totals),
               insight=services.insight(profile, totals, s['count']),
               latest_weight=latest_weight, first_weight=first_weight,
               meal_labels=MealEntry.MealType.choices, water_options=(150, 250, 500))
    return render(request, 'nt/dashboard.html', ctx)


# ------------------------------------------------------------------ journal
@onboarded_required
def journal(request):
    user, day = request.user, _parse_day(request.GET.get('date'))
    s = engine.daily_summary(user, day)
    ctx = _ctx(request, 'food', day=day, prev_day=day - timedelta(days=1),
               next_day=day + timedelta(days=1) if day < timezone.localdate() + timedelta(days=1) else None,
               is_today=day == timezone.localdate(), summary=s, sections=[
                   {'key': k, 'label': lbl, 'entries': s['entries'][k], 'total': s['meal_totals'][k]}
                   for k, lbl in MealEntry.MealType.choices],
               recent=services.recent_foods(user), meal_types=MealEntry.MealType.choices)
    return render(request, 'nt/journal.html', ctx)


@onboarded_required
@require_POST
def entry_add(request):
    form = EntryForm(request.POST, user=request.user)
    day = _parse_day(request.POST.get('date'))
    if form.is_valid():
        d = form.cleaned_data
        try:
            _, created = services.log_food(request.user, day=d['date'], meal_type=d['meal_type'], food=d['food'],
                                           quantity=d['quantity'], serving_unit=d['unit'], client_token=d['token'])
        except engine.QuantityError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Added {d["food"].name}.' if created else 'That entry was already added.')
        return redirect(f'/food/?date={d["date"].isoformat()}')
    for errs in form.errors.values():
        messages.error(request, ' '.join(errs))
    return redirect(f'/food/?date={day.isoformat()}')


@onboarded_required
@require_POST
def entry_edit(request, pk):
    entry = get_object_or_404(MealEntry, pk=pk, user=request.user)  # 404 for other users' ids
    form = EntryForm({**request.POST.dict(), 'food_id': entry.food_id, 'date': entry.date}, user=request.user) \
        if entry.food_id else None
    if form is None:
        messages.error(request, 'This food is no longer available; delete the entry instead.')
    elif form.is_valid():
        d = form.cleaned_data
        try:
            services.update_entry(entry, meal_type=d['meal_type'], quantity=d['quantity'], serving_unit=d['unit'])
            messages.success(request, 'Entry updated.')
        except engine.QuantityError as exc:
            messages.error(request, str(exc))
    else:
        for errs in form.errors.values():
            messages.error(request, ' '.join(errs))
    return redirect(f'/food/?date={entry.date.isoformat()}')


@onboarded_required
@require_POST
def entry_delete(request, pk):
    entry = get_object_or_404(MealEntry, pk=pk, user=request.user)
    day = entry.date
    entry.delete()
    messages.success(request, 'Entry deleted.')
    return redirect(f'/food/?date={day.isoformat()}')


@onboarded_required
@require_POST
def entry_copy(request):
    valid = {k for k, _ in MealEntry.MealType.choices}
    meal_type = request.POST.get('meal_type')
    if meal_type not in valid:
        messages.error(request, 'Unknown meal.')
        return redirect('nt_journal')
    to_day = _parse_day(request.POST.get('date'))
    from_day = to_day - timedelta(days=1)
    made = services.copy_meal(request.user, from_day=from_day, to_day=to_day, meal_type=meal_type)
    messages.success(request, f'Copied {len(made)} item(s) from yesterday.' if made else 'Nothing logged for that meal yesterday.')
    return redirect(f'/food/?date={to_day.isoformat()}')


# ---------------------------------------------------------------- food search
def _food_json(food, violations):
    return {'id': str(food.id), 'name': food.name, 'category': food.get_category_display(),
            'diet': food.diet_type, 'unit': food.base_unit, 'kcal_100': float(food.kcal), 'estimate': food.confidence != 'measured',
            'blocked': violations,
            'units': [{'id': u.id, 'label': u.label, 'grams': float(u.grams), 'default': u.is_default}
                      for u in food.serving_units.all()]}


@onboarded_required
@require_GET
def food_api_search(request):
    results = engine.search_foods(request.GET.get('q', ''), user=request.user, limit=12, profile=request.nt_profile)
    return JsonResponse({'results': [_food_json(f, bad) for f, bad in results]})


@onboarded_required
def food_search_page(request):
    q, cat = request.GET.get('q', '').strip(), request.GET.get('category', '')
    from .models import Food as F
    category = cat if cat in F.Category.values else None
    results = engine.search_foods(q, user=request.user, limit=40, category=category, profile=request.nt_profile)
    return render(request, 'nt/search.html', _ctx(request, 'food', q=q, category=category, results=results,
                                                  categories=F.Category.choices))


@onboarded_required
def food_detail(request, pk):
    food = get_object_or_404(services.accessible_foods(request.user).prefetch_related('serving_units', 'aliases'), pk=pk)
    return render(request, 'nt/food_detail.html', _ctx(request, 'food', food=food,
                                                       violations=engine.food_violations(food, request.nt_profile),
                                                       meal_types=MealEntry.MealType.choices, today=timezone.localdate()))


@onboarded_required
def exercises(request):
    qs = Exercise.objects.filter(is_active=True)
    q = request.GET.get('q', '').strip()
    body_part = request.GET.get('body_part', '').strip()
    equipment = request.GET.get('equipment', '').strip()
    difficulty = request.GET.get('difficulty', '').strip()
    exercise_type = request.GET.get('exercise_type', '').strip()
    sort = request.GET.get('sort', 'name')
    view = request.GET.get('view', 'foryou').strip().lower()
    if view not in {'foryou', 'explore'}:
        view = 'foryou'

    if q:
        qs = qs.filter(name__icontains=q) | qs.filter(description__icontains=q)
    if body_part:
        qs = qs.filter(primary_muscle=body_part)
    if equipment:
        qs = qs.filter(equipment=equipment)
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    if exercise_type:
        qs = qs.filter(exercise_type=exercise_type)

    if sort == 'difficulty':
        order = ['-difficulty', 'name']
    elif sort == 'type':
        order = ['exercise_type', 'name']
    else:
        order = ['name']
    qs = qs.order_by(*order).distinct()

    active_workout = _get_existing_workout_session(request.user)
    recommended = [] if view == 'explore' else qs[:4]
    saved_plans = WorkoutPlan.objects.filter(user=request.user).prefetch_related('exercises__exercise')[:3]
    recent_exercises = [exercise for exercise in _recent_exercises_for_user(request.user) if exercise.pk in qs.values_list('pk', flat=True)]

    return render(request, 'nt/exercises.html', _ctx(request, 'dumbbell', exercises=qs,
                                                     q=q, body_part=body_part, equipment=equipment,
                                                     difficulty=difficulty, exercise_type=exercise_type,
                                                     sort=sort, active_workout=active_workout, view=view,
                                                     recommended=recommended, recent_exercises=recent_exercises,
                                                     saved_plans=saved_plans,
                                                     exercise_nav=_exercise_subnav(view),
                                                     body_parts=Exercise.MuscleGroup.choices,
                                                     equipment_options=Exercise.Equipment.choices,
                                                     difficulty_options=Exercise.Difficulty.choices,
                                                     exercise_types=Exercise.ExerciseType.choices))


@onboarded_required
def exercise_detail(request, slug):
    exercise = get_object_or_404(Exercise, slug=slug, is_active=True)
    return_to = request.GET.get('back') or request.META.get('HTTP_REFERER') or reverse('nt_exercises')
    return render(request, 'nt/exercise_detail.html', _ctx(request, 'dumbbell', exercise=exercise,
                                                           youtube_search='https://www.youtube.com/results?search_query=' + exercise.name.replace(' ', '+'),
                                                           exercise_nav=_exercise_subnav('explore'),
                                                           return_to=return_to))


@onboarded_required
def exercise_progress(request, slug):
    exercise = get_object_or_404(Exercise, slug=slug, is_active=True)
    entries = WorkoutSessionExercise.objects.filter(exercise=exercise, session__user=request.user, session__status=WorkoutSession.Status.COMPLETED).select_related('session')
    points = []
    total_volume = Decimal('0')
    best_weight = Decimal('0')
    for item in entries:
        completed = [s for s in item.set_data if s.get('completed')]
        if not completed:
            continue
        max_weight = max((Decimal(str(s.get('weight', '0'))) for s in completed if str(s.get('weight', '0')).strip()), default=Decimal('0'))
        reps = sum(int(str(s.get('reps', '0')).split('-')[0]) if str(s.get('reps', '0')).strip() else 0 for s in completed)
        volume = (max_weight * Decimal(reps)) if max_weight else Decimal(reps)
        total_volume += volume
        best_weight = max(best_weight, max_weight)
        points.append({'date': item.session.completed_at.date() if item.session.completed_at else item.session.started_at.date(),
                       'weight': float(max_weight), 'reps': reps, 'volume': float(volume),
                       'session_id': item.session.pk, 'session_name': item.session.name})
    points = sorted(points, key=lambda p: p['date'])
    return render(request, 'nt/exercise_progress.html', _ctx(request, 'dumbbell', exercise=exercise, points=points,
                                                             best_weight=best_weight, total_volume=total_volume,
                                                             exercise_nav=_exercise_subnav('progress')))


@onboarded_required
def workout_history(request):
    sessions = WorkoutSession.objects.filter(user=request.user).prefetch_related('exercise_entries__exercise')
    return render(request, 'nt/workout_history.html', _ctx(request, 'dumbbell', sessions=sessions,
                                                          exercise_nav=_exercise_subnav('history')))


@onboarded_required
def workouts(request):
    plans = WorkoutPlan.objects.filter(user=request.user).prefetch_related('exercises__exercise')
    for plan in plans:
        for item in plan.exercises.all():
            planned = max(item.sets or 1, 1)
            base = min(100, max(25, int((planned / max(item.exercise.default_sets or planned, 1)) * 100)))
            item.progress_pct = min(100, base + (item.order * 7) % 20)
            item.target_label = f'{item.sets} sets • {item.reps} • {item.rest_seconds}s rest'
    active_workout = _get_existing_workout_session(request.user)
    return render(request, 'nt/workouts.html', _ctx(request, 'dumbbell', plans=plans, active_workout=active_workout,
                                                     exercise_nav=_exercise_subnav('workouts')))


@onboarded_required
@require_POST
def create_workout_plan(request):
    name = (request.POST.get('name') or 'My workout plan').strip() or 'My workout plan'
    plan = WorkoutPlan.objects.create(user=request.user, name=name)
    messages.success(request, f'Created {plan.name}.')
    return redirect('nt_workouts')


@onboarded_required
@require_POST
def save_workout_exercise(request, slug):
    exercise = get_object_or_404(Exercise, slug=slug, is_active=True)
    plan, _ = WorkoutPlan.objects.get_or_create(user=request.user, name='My workout plan')
    sets = request.POST.get('sets', str(exercise.default_sets))
    reps = request.POST.get('reps', exercise.default_reps)
    rest = request.POST.get('rest_seconds', str(exercise.rest_seconds or 60))
    duration = request.POST.get('duration_seconds', '') or None
    try:
        sets_value = int(sets)
        rest_value = int(rest)
    except (TypeError, ValueError):
        sets_value = exercise.default_sets
        rest_value = exercise.rest_seconds or 60
    WorkoutPlanExercise.objects.create(
        plan=plan,
        exercise=exercise,
        order=(WorkoutPlanExercise.objects.filter(plan=plan).count() + 1),
        sets=sets_value,
        reps=reps,
        duration_seconds=int(duration) if duration else None,
        rest_seconds=rest_value,
    )
    messages.success(request, f'Added {exercise.name} to your workout plan.')
    return redirect('nt_exercise_detail', slug=exercise.slug)


@onboarded_required
@require_POST
def delete_workout_exercise(request, plan_pk, item_pk):
    item = get_object_or_404(WorkoutPlanExercise, pk=item_pk, plan__user=request.user, plan__pk=plan_pk)
    item.delete()
    messages.success(request, 'Exercise removed from your workout plan.')
    return redirect('nt_workouts')


@onboarded_required
def start_exercise_session(request, slug):
    exercise = get_object_or_404(Exercise, slug=slug, is_active=True)
    session = WorkoutSession.objects.create(user=request.user, name=f'{exercise.name} session', status=WorkoutSession.Status.ACTIVE)
    WorkoutSessionExercise.objects.create(
        session=session,
        exercise=exercise,
        order=1,
        sets_target=max(1, exercise.default_sets),
        reps=exercise.default_reps,
        rest_seconds=exercise.rest_seconds or 60,
        status=WorkoutSessionExercise.ExecutionStatus.ACTIVE,
        completed_sets=0,
        set_data=[],
    )
    return redirect('nt_workout_session', session_id=session.pk)


@onboarded_required
def workout_session(request, session_id):
    session = get_object_or_404(WorkoutSession, pk=session_id, user=request.user)
    entries = list(session.exercise_entries.select_related('exercise').order_by('order'))
    current_index = int(request.GET.get('exercise_index', '0')) if entries else 0
    current_index = min(max(current_index, 0), max(len(entries) - 1, 0))
    current_entry = entries[current_index] if entries else None
    set_slots = list(range(1, 13))

    if request.method == 'POST':
        current_value = request.POST.get('exercise_index')
        if current_value and current_value.isdigit():
            current_index = int(current_value)
            current_entry = entries[current_index] if entries else None
        if 'skip' in request.POST and current_entry:
            current_entry.status = WorkoutSessionExercise.ExecutionStatus.SKIPPED
            current_entry.completed_sets = 0
            current_entry.save(update_fields=['status', 'completed_sets', 'updated_at'])
            if current_index + 1 < len(entries):
                next_idx = current_index + 1
                entries[next_idx].status = WorkoutSessionExercise.ExecutionStatus.ACTIVE
                entries[next_idx].save(update_fields=['status', 'updated_at'])
                return redirect(f'{reverse("nt_workout_session", args=[session.pk])}?exercise_index={next_idx}')
            return redirect('nt_workout_summary', session_id=session.pk)
        if 'next' in request.POST or 'previous' in request.POST or 'save' in request.POST or 'complete' in request.POST:
            if current_entry:
                set_data = []
                for idx in range(1, 13):
                    reps = request.POST.get(f'set_{idx}_reps')
                    weight = request.POST.get(f'set_{idx}_weight')
                    completed = request.POST.get(f'set_{idx}_done') == 'on' or request.POST.get(f'set_{idx}_done') == '1'
                    if reps or weight or completed:
                        set_data.append({'set_number': idx, 'reps': reps or '', 'weight': weight or '', 'completed': completed})
                current_entry.set_data = set_data
                current_entry.completed_sets = sum(1 for item in set_data if item.get('completed'))
                current_entry.status = WorkoutSessionExercise.ExecutionStatus.COMPLETED if current_entry.completed_sets else WorkoutSessionExercise.ExecutionStatus.ACTIVE
                current_entry.save(update_fields=['set_data', 'completed_sets', 'status', 'updated_at'])
            if 'next' in request.POST and current_index + 1 < len(entries):
                next_idx = current_index + 1
                return redirect(f'{reverse("nt_workout_session", args=[session.pk])}?exercise_index={next_idx}')
            if 'previous' in request.POST and current_index > 0:
                prev_idx = current_index - 1
                return redirect(f'{reverse("nt_workout_session", args=[session.pk])}?exercise_index={prev_idx}')
            if 'complete' in request.POST:
                session.status = WorkoutSession.Status.COMPLETED
                session.completed_at = timezone.now()
                session.elapsed_seconds = int((session.completed_at - session.started_at).total_seconds())
                session.save(update_fields=['status', 'completed_at', 'elapsed_seconds', 'updated_at'])
                return redirect('nt_workout_summary', session_id=session.pk)
            return redirect(f'{reverse("nt_workout_session", args=[session.pk])}?exercise_index={current_index}')

    if not entries and request.method == 'GET':
        session.status = WorkoutSession.Status.COMPLETED
        session.completed_at = timezone.now()
        session.save(update_fields=['status', 'completed_at', 'updated_at'])
        return redirect('nt_workout_summary', session_id=session.pk)

    return render(request, 'nt/workout_session.html', _ctx(request, 'dumbbell', session=session, entries=entries,
                                                          current_index=current_index, current_entry=current_entry,
                                                          set_slots=set_slots, exercise_nav=_exercise_subnav('workouts')))


@onboarded_required
def workout_summary(request, session_id):
    session = get_object_or_404(WorkoutSession, pk=session_id, user=request.user)
    exercises = list(session.exercise_entries.select_related('exercise').order_by('order'))
    completed_exercises = sum(1 for item in exercises if item.status == WorkoutSessionExercise.ExecutionStatus.COMPLETED)
    total_reps = sum(int(str(item.reps).split('-')[0]) if str(item.reps).strip() and str(item.reps).replace('-', '').isdigit() else 0 for item in exercises)
    total_sets = sum(item.completed_sets for item in exercises)
    return render(request, 'nt/workout_summary.html', _ctx(request, 'dumbbell', session=session, exercises=exercises,
                                                            completed_exercises=completed_exercises, total_reps=total_reps,
                                                            total_sets=total_sets, exercise_nav=_exercise_subnav('workouts')))


# ----------------------------------------------------------- water & weight
@onboarded_required
@require_POST
def water_add(request):
    try:
        ml = int(request.POST.get('ml', ''))
    except ValueError:
        ml = 0
    if not 1 <= ml <= 2000:
        messages.error(request, 'Enter between 1 and 2000 ml.')
    else:
        WaterEntry.objects.create(user=request.user, date=timezone.localdate(), ml=ml)
        messages.success(request, f'Added {ml} ml of water.')
    return redirect('nt_dashboard')


@onboarded_required
@require_POST
def weight_add(request):
    try:
        kg = Decimal(request.POST.get('kg', ''))
    except Exception:
        kg = Decimal(0)
    if not Decimal(25) <= kg <= Decimal(300):
        messages.error(request, 'Enter a weight between 25 and 300 kg.')
    else:
        WeightEntry.objects.update_or_create(user=request.user, date=timezone.localdate(),
                                             defaults={'weight_kg': kg.quantize(Decimal('0.1'))})
        messages.success(request, 'Weight saved.')
    return redirect('nt_dashboard')
