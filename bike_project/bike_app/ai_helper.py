"""
ai_helper.py
─────────────────────────────────────────────────────────────────────────────
Unified wrapper for AI generation that defaults to Gemini and automatically
falls back to OpenAI if Gemini is rate limited or fails.
Also includes motorcycle specification lookup referencing 100_popular_bikes_india.csv
with automatic fallback to direct AI inquiry.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)


def generate_content(prompt: str) -> str:
    """
    Attempts to generate content using Google Gemini.
    Tries gemini-3.8-flash first, falling back to gemini-3.5-flash-lite if busy.
    If Gemini fails completely, it automatically falls back to OpenAI.
    """
    try:
        # 1. Try Gemini
        from google import genai  # pyrefly: ignore [missing-import]
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("No Gemini API key found. Set GOOGLE_API_KEY in .env")
        client = genai.Client(api_key=api_key)

        gemini_models = ['gemini-3.8-flash', 'gemini-3.5-flash-lite']
        last_gemini_err = None
        for m in gemini_models:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=prompt
                )
                return response.text
            except Exception as e:
                last_gemini_err = e
                print(f"WARNING: Gemini model '{m}' failed: {e}. Trying next option...")

        raise last_gemini_err or Exception("Gemini generation failed on all models.")

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


def _load_popular_bikes_csv() -> str | None:
    """
    Locates and reads the 100_popular_bikes_india.csv file content.
    Searches workspace root, project directory, and app directory.
    """
    base_paths = [
        Path(__file__).resolve().parent.parent.parent / "100_popular_bikes_india.csv",
        Path(__file__).resolve().parent.parent / "100_popular_bikes_india.csv",
        Path(__file__).resolve().parent / "100_popular_bikes_india.csv",
    ]
    for p in base_paths:
        if p.exists() and p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                print(f"[Bike Specs] Could not read CSV at {p}: {e}")
    return None


def get_bike_specs_from_ai(bikename: str) -> dict:
    """
    Finds fuel tank capacity (liters) and mileage (km/l) for a given motorcycle.
    
    1. First, asks AI to refer to the '100_popular_bikes_india.csv' reference dataset.
       If matched, extracts capacity and calculates the average mileage from ranges (e.g. '60–70' -> 65).
    2. If that fails (bike not found in CSV, CSV missing, or AI parsing failure),
       falls back to directly querying AI for the bike model (the current behaviour).
    3. If all attempts fail, returns safe default specs (capacity: 15.0, mileage: 35.0).
    """
    if not bikename or not bikename.strip():
        return {"capacity": 15.0, "mileage": 35.0, "source": "default"}

    cleaned_name = bikename.strip()

    # ── Step 1: Ask AI to refer to 100_popular_bikes_india CSV ──
    csv_content = _load_popular_bikes_csv()
    if csv_content:
        try:
            csv_prompt = (
                f"You are an expert motorcycle assistant.\n"
                f"Refer to the following reference dataset of popular bikes in India from the CSV file '100_popular_bikes_india':\n\n"
                f"```csv\n{csv_content}\n```\n\n"
                f"Task:\n"
                f"Find the motorcycle model that matches '{cleaned_name}' from the CSV reference data above.\n"
                f"- Fuel tank capacity (in liters) is in the 'Tank Capacity (L)' column.\n"
                f"- Fuel efficiency / mileage (in km/l) is in the 'Approx. Real-World Mileage (kmpl)' column. "
                f"If a range is given (e.g., '60–70', '30–38', '25–32'), calculate and return the average numeric value.\n"
                f"- If '{cleaned_name}' is found in this CSV dataset, return ONLY a valid JSON object in this format:\n"
                f"  {{\"found\": true, \"capacity\": <number>, \"mileage\": <number>, \"matched_bike\": \"<name from CSV>\"}}\n"
                f"- If '{cleaned_name}' is NOT present in this CSV dataset or cannot be confidently matched, return ONLY:\n"
                f"  {{\"found\": false}}\n"
                f"Do not include markdown other than json code block if needed."
            )
            response_text = generate_content(csv_prompt)
            raw = response_text.replace('```json', '').replace('```', '').strip()
            data = json.loads(raw)
            if data.get("found") is True and data.get("capacity") is not None and data.get("mileage") is not None:
                cap = float(data["capacity"])
                mil = float(data["mileage"])
                print(f"[Bike Specs] Successfully matched '{cleaned_name}' to '{data.get('matched_bike')}' in 100_popular_bikes_india.csv -> Capacity: {cap}L, Mileage: {mil} km/l")
                return {
                    "capacity": cap,
                    "mileage": mil,
                    "source": "csv_ai",
                    "matched_bike": data.get("matched_bike")
                }
            else:
                print(f"[Bike Specs] '{cleaned_name}' not found in 100_popular_bikes_india.csv. Falling back to direct AI inquiry...")
        except Exception as e:
            print(f"[Bike Specs] Error during CSV reference lookup for '{cleaned_name}': {e}. Falling back to direct AI inquiry...")
    else:
        print("[Bike Specs] 100_popular_bikes_india.csv not accessible. Falling back to direct AI inquiry...")

    # ── Step 2: Fallback to directly asking AI (current behavior) ──
    try:
        direct_prompt = (
            f"Return the average fuel tank capacity (liters) and average mileage (km/l) "
            f"for the motorcycle model '{cleaned_name}'. "
            f"Return ONLY a JSON object with keys 'capacity' and 'mileage'. "
            f"Example: {{\"capacity\": 15, \"mileage\": 35}}"
        )
        response_text = generate_content(direct_prompt)
        raw = response_text.replace('```json', '').replace('```', '').strip()
        data = json.loads(raw)
        cap = float(data.get("capacity", 15.0))
        mil = float(data.get("mileage", 35.0))
        print(f"[Bike Specs] Looked up '{cleaned_name}' via direct AI inquiry -> Capacity: {cap}L, Mileage: {mil} km/l")
        return {
            "capacity": cap,
            "mileage": mil,
            "source": "direct_ai"
        }
    except Exception as e:
        print(f"[Bike Specs] Direct AI inquiry failed for '{cleaned_name}': {e}. Using default values.")
        return {
            "capacity": 15.0,
            "mileage": 35.0,
            "source": "default"
        }
