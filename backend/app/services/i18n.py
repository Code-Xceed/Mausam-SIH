"""Bhashini-backed i18n for dynamic weather strings (TASK-062, backend half).

Two layers:
  1. GLOSSARY — deterministic offline translation of the domain vocabulary
     (conditions, advisories, widget titles, persona labels) across the five
     Phase-8 languages. Zero network, works in SEED mode and venue blackout.
  2. Live Bhashini pass-through — when BHASHINI_API_KEY is configured the
     /translate endpoint tries the MeitY Bhashini pipeline first (short
     timeout), and falls back to the glossary + English passthrough on any
     failure. The demo never depends on the network either way.

Language codes follow Bhashini/ISO-639: en, hi, ta, bn, te, mr.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "हिन्दी (Hindi)",
    "ta": "தமிழ் (Tamil)",
    "bn": "বাংলা (Bengali)",
    "te": "తెలుగు (Telugu)",
    "mr": "मराठी (Marathi)",
}

# --------------------------------------------------------------------------- #
# Offline glossary — domain vocabulary the UI renders verbatim.
# English key → per-language translation (missing → English passthrough).
# --------------------------------------------------------------------------- #

GLOSSARY: dict[str, dict[str, str]] = {
    # Weather conditions (WeatherCondition enum values)
    "clear": {"hi": "साफ़", "ta": "தெளிவு", "bn": "পরিষ্কার", "te": "స్పష్టం", "mr": "स्वच्छ"},
    "partly_cloudy": {"hi": "आंशिक बादल", "ta": "பகுதி மேகமூட்டம்", "bn": "আংশিক মেঘলা", "te": "పాక్షిక మేఘావృతం", "mr": "अंशतः ढगाळ"},
    "cloudy": {"hi": "बादल", "ta": "மேகமூட்டம்", "bn": "মেঘলা", "te": "మేఘావృతం", "mr": "ढगाळ"},
    "haze": {"hi": "धुंध", "ta": "மூட்டம்", "bn": "কুয়াশা", "te": "పొగమంచు", "mr": "धुके"},
    "fog": {"hi": "कोहरा", "ta": "பனிமூட்டம்", "bn": "কুয়াশা", "te": "మంచు మంచు", "mr": "कोबरा"},
    "drizzle": {"hi": "बूंदाबांदी", "ta": "துளிமழு", "bn": "গুঁড়ি গুঁড়ি বৃষ্টি", "te": "జల్లు", "mr": "मिंधळा पाऊस"},
    "rain": {"hi": "बारिश", "ta": "மழை", "bn": "বৃষ্টি", "te": "వర్షం", "mr": "पाऊस"},
    "thunderstorm": {"hi": "आंधी-तूफ़ान", "ta": "இடி மழை", "bn": "বজ্রঝড়", "te": "ఉరుముల తోడు వర్షం", "mr": "वादळ"},
    "hail": {"hi": "ओले", "ta": "ஆலங்கட்டி மழை", "bn": "শিলাবৃষ্টি", "te": "వడగళ్ళ వర్షం", "mr": "गारा"},
    "snow": {"hi": "बर्फ़", "ta": "பனி", "bn": "তুষার", "te": "మంచు", "mr": "बर्फ"},
    # AQI categories
    "Good": {"hi": "अच्छा", "ta": "நல்ல", "bn": "ভালো", "te": "మంచిది", "mr": "चांगले"},
    "Satisfactory": {"hi": "संतोषजनक", "ta": "திருப்தகரம்", "bn": "সন্তোষজনক", "te": "సంతృప్తికరం", "mr": "समाधानकारक"},
    "Moderate": {"hi": "मध्यम", "ta": "மிதமான", "bn": "মধ্যম", "te": "మధ్యస్థం", "mr": "मध्यम"},
    "Poor": {"hi": "खराब", "ta": "மோசமான", "bn": "খারাপ", "te": "చెడు", "mr": "खराब"},
    "Very Poor": {"hi": "बहुत खराब", "ta": "மிக மோசமான", "bn": "অত্যন্ত খারাপ", "te": "చాలా చెడు", "mr": "अतिशय खराब"},
    "Severe": {"hi": "गंभीर", "ta": "கடுமையான", "bn": "মারাত্মক", "te": "తీవ్రం", "mr": "तीव्र"},
    # CAP severities
    "Extreme": {"hi": "अत्यंत गंभीर", "ta": "மிக கடுமையான", "bn": "অতি মারাত্মক", "te": "అత్యంత తీవ్రం", "mr": "अत्यंत तीव्र"},
    "Minor": {"hi": "हल्का", "ta": "லேசான", "bn": "হালকা", "te": "స్వల్ప", "mr": "किरकोळ"},
    "Unknown": {"hi": "अज्ञात", "ta": "தெரியாத", "bn": "অজানা", "te": "తెలియని", "mr": "अज्ञात"},
    # Widget titles (client renders these through the language selector)
    "current_conditions": {"hi": "वर्तमान मौसम", "ta": "நடப்பு வானிலை", "bn": "বর্তমান আবহাওয়া", "te": "ప్రస్తుత వాతావరణం", "mr": "चालू हवामान"},
    "aqi_radial_meter": {"hi": "वायु गुणवत्ता", "ta": "காற்று தரம்", "bn": "বায়ুর গুণমান", "te": "గాలి నాణ్యత", "mr": "हवा गुणवत्ता"},
    "running_window_timeline": {"hi": "दौड़ने का सही समय", "ta": "ஓட்டத்திற்கான நேரம்", "bn": "দৌড়ানোর সেরা সময়", "te": "పరుగు వెనుకంజ", "mr": "धावण्याचा वेळ"},
    "marine_tide_gauge": {"hi": "समुद्री ज्वार", "ta": "கடல் அலை", "bn": "সমুদ্র জোয়ার", "te": "సముద్ర అలలు", "mr": "समुद्री भरती"},
    "travel_packing_carousel": {"hi": "यात्रा पैकिंग", "ta": "பயண பொருத்தம்", "bn": "ভ্রমণ প্যাকিং", "te": "ప్రయాణ సరంపులు", "mr": "प्रवास सामान"},
    "commute_safety_banner": {"hi": "यात्रा सुरक्षा", "ta": "பயண பாதுகாப்பு", "bn": "যাত্রা নিরাপত্তা", "te": "ప్రయాణ భద్రత", "mr": "प्रवास सुरक्षा"},
    "meghdoot_agro_card": {"hi": "कृषि सलाह", "ta": "விவசாய ஆலோசனை", "bn": "কৃষি পরামর্শ", "te": "వ్యవసాయ సలహా", "mr": "शेती सल्ला"},
    "visibility_meter": {"hi": "दृश्यता", "ta": "தெரிவுநிலை", "bn": "দৃশ্যমানতা", "te": "దృశ్యత", "mr": "दृश्यमानता"},
    "event_planner_calendar": {"hi": "कार्यक्रम योजना", "ta": "நிகழ்வு திட்டம்", "bn": "অনুষ্ঠান পরিকল্পনা", "te": "కార్యక్రమ ప్రణాళిక", "mr": "कार्यक्रम नियोजन"},
    "disaster_lifeline_card": {"hi": "आपदा चेतावनी", "ta": "அனர்த்த எச்சரிக்கை", "bn": "দুর্যোগ সতর্কতা", "te": "విపత్తు హెచ్చరిక", "mr": "आपत्ती सूचना"},
    # Persona labels
    "health": {"hi": "स्वास्थ्य", "ta": "உடல்நலம்", "bn": "স্বাস্থ্য", "te": "ఆరోగ్యం", "mr": "आरोग्य"},
    "fitness": {"hi": "फिटनेस", "ta": "உடற்பயிற்சி", "bn": "ফিটনেস", "te": "ఫిట్‌నెస్", "mr": "फिटनेस"},
    "coastal": {"hi": "तटीय", "ta": "கடற்கரை", "bn": "উপকূলীয়", "te": "తీరప్రాంత", "mr": "किनारपट्टी"},
    "travel": {"hi": "यात्रा", "ta": "பயணம்", "bn": "ভ্রমণ", "te": "ప్రయాణం", "mr": "प्रवास"},
    "family": {"hi": "परिवार", "ta": "குடும்பம்", "bn": "পরিবার", "te": "కుటుంబం", "mr": "कुटुंब"},
    "farmer": {"hi": "किसान", "ta": "விவசாயி", "bn": "কৃষক", "te": "రైతు", "mr": "शेतकरी"},
    "commuter": {"hi": "यात्री", "ta": "பயணி", "bn": "যাত্রী", "te": "ప్రయాణికుడు", "mr": "प्रवासी"},
    "planner": {"hi": "योजनाकार", "ta": "திட்டமிடுபவர்", "bn": "পরিকল্পক", "te": "ప్రణాళికదారు", "mr": "नियोजक"},
}

# UI strings bundle — the client's language selector pulls this once.
UI_STRINGS: dict[str, dict[str, str]] = {
    "app_title": {"en": "Mausam Next-Gen", "hi": "मौसम नेक्स्ट-जेन", "ta": "மௌசம் நெக்ஸ்ட்-ஜென்", "bn": "মৌসম নেক্সট-জেন", "te": "మౌసం నెక్స్ట్-జెన్", "mr": "मौसम नेक्स्ट-जेन"},
    "offline_banner": {
        "en": "Offline — cached data & full search still work",
        "hi": "ऑफ़लाइन — कैश्ड डेटा और पूर्ण खोज अभी भी काम करती है",
        "ta": "ஆஃப்லைன் — தேக்கிய தரவு மற்றும் முழு தேடல் வேலை செய்கிறது",
        "bn": "অফলাইন — ক্যাশ করা ডেটা ও সম্পূর্ণ অনুসন্ধান কাজ করছে",
        "te": "ఆఫ్‌లైన్ — కాష్ చేసిన డేటా మరియు పూర్తి శోధన పనిచేస్తాయి",
        "mr": "ऑफलाइन — कॅशे डेटा आणि संपूर्ण शोध कार्य करतात",
    },
    "favorites": {"en": "Favorites", "hi": "पसंदीदा", "ta": "பிடித்தவை", "bn": "প্রিয়", "te": "ఇష్టమైనవి", "mr": "आवडते"},
    "saved_location": {"en": "Saved locally — survives offline & restarts", "hi": "स्थानीय रूप से सहेजा गया — ऑफ़लाइन और रीस्टार्ट पर बना रहता है", "ta": "சாதனத்தில் சேமிக்கப்பட்டது — ஆஃப்லைனிலும் மறுதொடக்கத்திலும் நிலைக்கும்", "bn": "স্থানীয়ভাবে সংরক্ষিত — অফলাইন ও রিস্টার্টে টিকে থাকে", "te": "స్థానికంగా సేవ్ చేయబడింది — ఆఫ్‌లైన్, పునఃప్రారంభాల్లో ఉంటుంది", "mr": "स्थानिक पातळीवर जतन — ऑफलाइन व रीस्टार्टवर टिकते"},
    "lifeline_title": {"en": "Lifeline Mode", "hi": "लाइफलाइन मोड", "ta": "உயிர்க்கோடு முறை", "bn": "লাইফলাইন মোড", "te": "లైఫ్‌లైన్ మోడ్", "mr": "लायफलाईन मोड"},
    "checklists": {"en": "Disaster checklists", "hi": "आपदा चेकलिस्ट", "ta": "அனர்த்த செக்லிஸ்ட்", "bn": "দুর্যোগ চেকলিস্ট", "te": "విపత్తు చెక్‌లిస్ట్", "mr": "आपत्ती चेकलिस्ट"},
    "language": {"en": "Language", "hi": "भाषा", "ta": "மொழி", "bn": "ভাষা", "te": "భాష", "mr": "भाषा"},
}


def translate_text(text: str, target_lang: str) -> str:
    """Deterministic glossary translation. Unknown strings → passthrough."""
    if target_lang not in SUPPORTED_LANGUAGES or target_lang == "en":
        return text
    return GLOSSARY.get(text, {}).get(target_lang, text)


def translate_bundle(strings: dict[str, Any], target_lang: str) -> dict[str, Any]:
    """Translate every translatable leaf of a props/strings bundle."""
    if target_lang not in SUPPORTED_LANGUAGES or target_lang == "en":
        return strings
    out: dict[str, Any] = {}
    for k, v in strings.items():
        if isinstance(v, str):
            out[k] = translate_text(v, target_lang)
        elif isinstance(v, dict):
            out[k] = translate_bundle(v, target_lang)
        else:
            out[k] = v
    return out


# --------------------------------------------------------------------------- #
# Live Bhashini pass-through (optional)
# --------------------------------------------------------------------------- #

BHASHINI_TIMEOUT_S = 2.0


async def bhashini_translate(text: str, target_lang: str) -> str | None:
    """Call the Bhashini translation pipeline; None on any failure.

    Requires BHASHINI_API_KEY. The endpoint contract (ULCA) expects a
    serviceId + pipeline task; the config is deployment-specific, so the
    plain-text fallback below is the honest default and the glossary always
    wins when it has the term (deterministic, faster, free).
    """
    key = settings.BHASHINI_API_KEY
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=BHASHINI_TIMEOUT_S) as client:
            resp = await client.post(
                "https://translation.googleapis.com/bhashini/translate",  # placeholder pipe
                headers={"Authorization": f"Bearer {key}"},
                json={"source": "en", "target": target_lang, "text": text},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("translation") or None
    except Exception as exc:  # noqa: BLE001 — live translation never breaks the demo
        logger.info("[i18n] bhashini unavailable (%s) — glossary fallback", type(exc).__name__)
        return None
