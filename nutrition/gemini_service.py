from __future__ import annotations

import json
import re
import time
from typing import Iterable, List, Optional

from django.conf import settings
from django.utils import timezone
from google import genai
from google.genai import types

from . import engine, services
from .models import MealEntry

SYSTEM_PROMPT = """You are NutriTrack AI, a friendly nutrition coach for Indian and global eating habits.

Rules:
- Answer the current user request first. Do not repeat previous assistant answers unless the user explicitly asks for them.
- Use only the user data provided in the context. Never invent meals, weight history, nutrient totals, workout records, allergies or user preferences.
- If the user asks for a food recommendation, respect the hard constraints: allergies, excluded ingredients, diet pattern, budget, and cooking time.
- Nutrition calculations are driven by the app's deterministic engine. Use the provided totals and meal summaries as the source of truth for calories, protein, carbs, fats and fibre.
- Be encouraging, practical and simple. Suggest familiar Indian foods and common household portions.
- Do not claim to be a doctor or registered dietitian. Do not diagnose diseases or prescribe medication.
- When the required data is missing, ask a concise clarifying question instead of guessing.
- Keep answers concise but useful, ideally 3-8 sentences unless the user explicitly asks for longer guidance.
- If the Gemini provider is unavailable or the API key is missing, say so plainly and offer the user a fallback from the app data.
- When the user asks for a meal suggestion, prefer the current day’s remaining calories and protein gap, not stale meal history from earlier messages.
- Ignore earlier assistant replies that conflict with the current question; the current request is the priority.
"""


class GeminiService:
    @staticmethod
    def validate_user_message(message: str) -> str:
        cleaned = (message or '').strip()
        if not cleaned:
            raise ValueError('Please enter a message before sending.')
        if len(cleaned) > 1200:
            raise ValueError('Your message is too long. Please keep it under 1200 characters.')
        return cleaned

    @staticmethod
    def model_name() -> str:
        configured = (getattr(settings, 'GEMINI_MODEL', '') or '').strip()
        if not configured:
            return 'gemini-3.8-flash'
        if configured.startswith('models/'):
            configured = configured.replace('models/', '', 1)
        if configured in {'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash'}:
            return 'gemini-3.8-flash'
        return configured

    @classmethod
    def is_configured(cls) -> bool:
        return bool((getattr(settings, 'GEMINI_API_KEY', '') or '').strip() and cls.model_name().strip())

    @classmethod
    def build_context_for_user(cls, user) -> dict:
        profile = services.get_profile(user)
        today = timezone.localdate()
        summary = engine.daily_summary(user, today)
        totals = summary['totals']
        meal_entries = MealEntry.objects.filter(user=user, date=today).select_related('food').order_by('meal_type', '-created_at')[:15]
        meals = []
        for entry in meal_entries:
            food_name = entry.food_name or (entry.food.name if entry.food else 'Removed item')
            meals.append({
                'meal_type': entry.meal_type,
                'food': food_name,
                'quantity': str(entry.quantity),
                'kcal': float(entry.kcal),
                'protein_g': float(entry.protein_g),
                'carbs_g': float(entry.carbs_g),
                'fat_g': float(entry.fat_g),
            })

        return {
            'user': {
                'username': user.get_username(),
                'goal': profile.goal,
                'diet_pattern': profile.diet_pattern,
                'allergies': profile.allergies,
                'excluded_ingredients': profile.excluded_ingredients,
                'protein_target_g': float(profile.protein_target_g or 0),
                'kcal_target': float(profile.kcal_target or 0),
                'fibre_target_g': float(profile.fibre_target_g or 0),
                'cooking_minutes': profile.cooking_minutes,
                'daily_budget_inr': profile.daily_budget_inr,
            },
            'totals': {
                'kcal': float(totals.kcal),
                'protein_g': float(totals.protein_g),
                'carbs_g': float(totals.carbs_g),
                'fat_g': float(totals.fat_g),
                'fibre_g': float(totals.fibre_g),
            },
            'day_summary': {
                'meal_count': summary['count'],
                'logged_meals': meals,
            },
        }

    @classmethod
    def _build_prompt(cls, user_message: str, user: object, history: Optional[Iterable[object]] = None) -> str:
        context = cls.build_context_for_user(user)
        recent = []
        if history:
            for item in list(history)[-5:]:
                content = (getattr(item, 'content', '') or '').strip()
                if not content or content == user_message.strip():
                    continue
                recent.append(f"{getattr(item, 'role', 'UNKNOWN')}: {content}")
        payload = json.dumps(context, ensure_ascii=False, sort_keys=True)
        return f"""{SYSTEM_PROMPT}

User request:
{user_message}

Conversation history:
{chr(10).join(recent) if recent else 'No previous messages in this conversation.'}

User data (deterministic app data, not guesses):
{payload}

Important: The current user request is the priority. Treat the message above as the only task to answer. Use the app data to answer directly and do not restate earlier responses or stale assumptions.

Respond in plain text. If the user asks for a plan, be specific and practical with food suggestions using the user's constraints. If data is missing, ask one direct question.
"""

    @classmethod
    def _extract_text(cls, response):
        if not response:
            return ''
        text = getattr(response, 'text', None)
        if text:
            return str(text).strip()
        candidates = getattr(response, 'candidates', None) or []
        for candidate in candidates:
            parts = getattr(candidate, 'content', None)
            if not parts:
                continue
            if isinstance(parts, list):
                for part in parts:
                    if hasattr(part, 'text'):
                        result = str(part.text).strip()
                        if result:
                            return result
            if hasattr(parts, 'parts'):
                for part in parts.parts:
                    if hasattr(part, 'text'):
                        result = str(part.text).strip()
                        if result:
                            return result
        if isinstance(response, dict):
            text = response.get('text') or response.get('content')
            if text:
                return str(text).strip()
        return ''

    @staticmethod
    def _should_retry_gemini_error(exc) -> bool:
        msg = str(exc).lower()
        return any(token in msg for token in [
            '503', 'unavailable', 'high demand', 'rate limit', '429',
            'resource_exhausted', 'temporarily unavailable', 'too many requests',
            'overloaded', 'busy'
        ])

    @classmethod
    def generate_reply(cls, *, user, message: str, history=None):
        cleaned = cls.validate_user_message(message)
        if not cls.is_configured():
            raise RuntimeError('Gemini is not configured. Add GEMINI_API_KEY and GEMINI_MODEL in your environment.')

        last_error = None
        for attempt in range(3):
            try:
                model_name = cls.model_name()
                client = genai.Client(api_key=getattr(settings, 'GEMINI_API_KEY'))
                prompt = cls._build_prompt(cleaned, user, history)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.4,
                        max_output_tokens=500,
                    ),
                )
                text = cls._extract_text(response)
                if not text:
                    raise ValueError('The Gemini API returned an empty response.')
                return text.strip()
            except Exception as exc:  # pragma: no cover - surfaced to caller for graceful UI handling
                last_error = exc
                if attempt < 2 and cls._should_retry_gemini_error(exc):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(str(exc) or 'The AI coach could not generate a response right now.') from exc

        if last_error is not None:
            raise RuntimeError(str(last_error) or 'The AI coach could not generate a response right now.') from last_error
        raise RuntimeError('The AI coach could not generate a response right now.')

    @staticmethod
    def fallback_reply(user, message: str) -> str:
        profile = services.get_profile(user)
        today = timezone.localdate()
        summary = engine.daily_summary(user, today)
        totals = summary['totals']
        text = (message or '').lower()

        if 'gut' in text or 'digest' in text or 'fibre' in text or 'fiber' in text:
            fibre_gap = max(float((profile.fibre_target_g or 0) - totals.fibre_g), 0)
            if fibre_gap > 0:
                return f'For gut health, aim to add about {fibre_gap:.0f} g more fibre today. Good choices from your plan include sabzi, fruit, dal, beans, oats, and whole grains.'
            return 'For gut health, your fibre intake looks solid. Keep the focus on vegetables, fruit, beans, dal, and high-fibre grains to stay consistent.'

        if 'dinner' in text or 'lunch' in text or 'breakfast' in text or 'eat' in text or 'meal' in text:
            protein_gap = max(float((profile.protein_target_g or 0) - totals.protein_g), 0)
            kcal_gap = max(float((profile.kcal_target or 0) - totals.kcal), 0)
            if summary['count'] == 0:
                return 'You have not logged any meals yet today. A simple protein-first dinner could be dal + rice + sabzi, paneer bhurji with roti, or yogurt with fruit.'
            if protein_gap > 0:
                return f'Based on today’s data, you are at {float(totals.protein_g):.0f} g protein and still need about {protein_gap:.0f} g more. A dal or paneer meal, yogurt, eggs, or tofu would fit well for your next meal.'
            if kcal_gap > 0:
                return f'You still have about {kcal_gap:.0f} kcal left before target. A balanced {"dinner" if "dinner" in text else "meal"} with dal, sabzi, and a carb like roti or rice would work well without overshooting.'
            return 'Your intake is tracking well right now. Keep the next meal protein-focused and add a fruit or vegetable side to stay balanced without overdoing calories.'

        if 'protein' in text:
            protein_gap = max(float((profile.protein_target_g or 0) - totals.protein_g), 0)
            if protein_gap > 0:
                return f'You are currently at {float(totals.protein_g):.0f} g protein today. You need about {protein_gap:.0f} g more to hit your target. Add dal, paneer, eggs, yogurt, or tofu at your next meal.'
            return 'Your protein intake is already on track for today. Keep building meals around dal, paneer, yogurt, eggs or tofu to stay consistent.'

        if summary['count'] == 0:
            return 'I do not see any meals logged for today yet. Add a protein-rich breakfast or lunch, and I can suggest a more precise next meal.'

        protein_gap = max(float((profile.protein_target_g or 0) - totals.protein_g), 0)
        kcal_gap = max(float((profile.kcal_target or 0) - totals.kcal), 0)
        if protein_gap > 0:
            return f'You still need about {protein_gap:.0f} g more protein today. A dal or paneer meal, yogurt, or tofu dish would help you close the gap.'
        if kcal_gap > 0:
            return f'You have about {kcal_gap:.0f} kcal remaining before target. A balanced meal with vegetables, dal, paneer, or roti would fit well.'
        return 'Your nutrition data looks steady so far. Keep the focus on protein, fibre, and consistent meals rather than a very large single meal.'
