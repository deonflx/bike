"""
ai_helper.py
─────────────────────────────────────────────────────────────────────────────
Unified wrapper for AI generation that defaults to Gemini and automatically
falls back to OpenAI if Gemini is rate limited or fails.
"""
import os
import json
from dotenv import load_dotenv

load_dotenv(override=True)


def generate_content(prompt: str) -> str:
    """
    Attempts to generate content using Google Gemini.
    If it fails (e.g. rate limit), it automatically falls back to OpenAI.
    """
    try:
        # 1. Try Gemini
        from google import genai  # pyrefly: ignore [missing-import]
        client = genai.Client()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text
    except Exception as gemini_err:
        print(f"WARNING: Gemini failed: {gemini_err}. Falling back to OpenAI...")
        
        # 2. Fallback to OpenAI
        try:
            from openai import OpenAI  # pyrefly: ignore [missing-import]
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content or ""
        except Exception as openai_err:
            print(f"ERROR: OpenAI also failed: {openai_err}")
            raise Exception(f"All AI providers failed. Gemini: {gemini_err} | OpenAI: {openai_err}")
