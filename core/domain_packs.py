"""Optional domain packs: extra grounding appended to the system prompt.

Packs are plain text, local, and free to use. They add vocabulary, formulas and
few-shot examples for a niche; they never override safety or user instructions.
"""

from __future__ import annotations

REAL_ESTATE_PACK_AR = """حزمة معرفة العقارات (مرجع داخلي للمساعد):
- المصطلحات: ARV = After Repair Value (قيمة العقار بعد الترميم). MAO = Maximum Allowable Offer = ARV × 0.70 − تكلفة الترميم. comps = عقارات مقارِنة مباعة مؤخرًا. wholesale fee = فارق السعر بين عقد الشراء وسعر البيع للمستثمر. assignment = نقل عقد الشراء لمستثمر آخر مقابل رسوم.
- قواعد التسعير: لا تذكر أرقامًا كحقائق دون بيانات المقارِنات؛ اذكر الافتراضات صراحة عند حساب ARV/MAO.
- نماذج أولية:
  1) طلب سعر من بائع: "أهلاً أستاذ X، بالنسبة للعقار في [المنطقة]... عايز أرتب معاينة اليوم أو بكرة، والسعر اللي حضرتك بتفكر فيه كام؟"
  2) تحليل صفقة: احسب MAO = ARV×0.70 − الترميم، قارن بالسعر المعروض، واذكر هامش الربح المتوقع ورسوم الجدوى.
  3) متابعة مشتر: "أهلاً أستاذ X، شد انتباهي [العقار/السعر] ده. لو حابب نحدد معاينة الأسبوع ده..."
- إن لم تتوفر بيانات مقارِنة، قل ذلك واقترح الخطوات (طلب 3 comps حديثة، تقدير الترميم لكل بند، حساب MAO) بدل اختلاق أرقام."""

REAL_ESTATE_PACK_EN = """Real-estate domain pack (internal grounding for the assistant):
- Terms: ARV = After Repair Value. MAO = Maximum Allowable Offer = ARV x 0.70 - repair cost. comps = recently sold comparable properties. wholesale fee = spread between contract price and investor resale price. assignment = transferring the purchase contract to an investor for a fee.
- Pricing rules: never state figures as facts without comps data; show assumptions explicitly when computing ARV/MAO.
- Few-shot patterns:
  1) Seller price check: ask for the asking price, compare to MAO, propose a walk-through.
  2) Deal analysis: compute MAO = ARV x 0.70 - repairs, compare to the offer, state expected margin and viability.
  3) Buyer follow-up: remind of the specific property/price and propose a concrete viewing time.
- If comps are missing, say so and propose the steps (pull 3 recent comps, itemize repairs, compute MAO) instead of inventing numbers."""

DOMAIN_PACKS = {
    "real_estate": {
        "label_ar": "العقارات (ARV / MAO / Comps)",
        "label_en": "Real estate (ARV / MAO / Comps)",
        "prompt_ar": REAL_ESTATE_PACK_AR,
        "prompt_en": REAL_ESTATE_PACK_EN,
    },
}


def domain_pack_text(pack_name: str, language: str = "ar") -> str:
    pack = DOMAIN_PACKS.get(pack_name)
    if not pack:
        return ""
    return pack["prompt_ar"] if language == "ar" else pack["prompt_en"]
