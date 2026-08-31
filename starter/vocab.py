"""Apparel-domain vocabularies and conversational cue lexicons.

Deliberately broader than the evaluator's own visible material/color lists so
that private-set paraphrasing still classifies correctly (overfitting guard).
"""

from __future__ import annotations

ALLOWED_ATTRIBUTES = {
    "category", "material", "color", "size", "style", "brand",
    "budget", "feature", "use_case", "other",
}

MATERIALS = {
    "cotton", "polyester", "nylon", "leather", "wool", "spandex", "elastane",
    "lycra", "silk", "rayon", "viscose", "denim", "linen", "fleece", "mesh",
    "canvas", "suede", "cashmere", "velvet", "corduroy", "acrylic", "satin",
    "chiffon", "lace", "rubber", "latex", "synthetic", "microfiber", "bamboo",
    "modal", "tweed", "flannel", "jersey", "neoprene", "sherpa", "faux",
    "stainless", "steel", "sterling", "silver", "gold", "brass", "copper",
    "titanium", "alloy", "resin", "plastic", "rhinestone", "crystal", "pearl",
    "gemstone", "cubic", "zirconia", "beaded", "fabric",
}

COLORS = {
    "black", "white", "blue", "red", "pink", "green", "yellow", "orange",
    "purple", "brown", "grey", "gray", "navy", "beige", "tan", "maroon",
    "teal", "khaki", "ivory", "charcoal", "burgundy", "olive", "cream",
    "turquoise", "lavender", "coral", "mint", "mustard", "rose", "camel",
    "multicolor", "multicolored", "rainbow", "metallic", "silver", "gold",
    "color", "colour",
}

SIZE_TERMS = {
    "size", "sizing", "width", "wide", "narrow", "petite", "tall", "plus",
    "regular", "small", "medium", "large", "xl", "xxl", "xs", "inseam",
    "length", "waist", "oversized", "fitted", "loose", "snug", "adjustable",
}

STYLE_TERMS = {
    "style", "fit", "department", "sleeve", "neck", "slim", "relaxed",
    "athletic", "skinny", "straight", "bootcut", "crew", "v-neck", "vneck",
    "collar", "zip", "zipper", "button", "hooded", "hoodie", "high-waisted",
    "waisted", "cropped", "vintage", "classic", "modern", "casual", "formal",
    "elegant", "cut", "silhouette", "pattern", "striped", "plaid", "floral",
}

USE_CASE_TERMS = {
    "hiking", "running", "gym", "workout", "yoga", "training", "sports",
    "winter", "summer", "outdoor", "work", "office", "travel", "beach",
    "wedding", "party", "everyday", "walking", "cycling", "swimming",
    "camping", "fishing", "hunting", "skiing", "snowboarding", "climbing",
    "dance", "school", "commute", "lounging", "sleep",
}

BUDGET_WORDS = {"budget", "price", "cost", "cheap", "affordable", "under", "spend", "dollar"}

# Cues that mean "I have no preference for what you just asked" (boundary sessions).
BOUNDARY_CUES = [
    "no preference", "don't have a preference", "do not have a preference",
    "not particular", "doesn't matter", "does not matter", "don't mind",
    "do not mind", "up to you", "your judgment", "your judgement",
    "your discretion", "you decide", "you pick", "whatever works",
    "whatever you think", "either is fine", "either works", "any is fine",
    "no strong feelings", "not fussy", "not picky", "open to anything",
]

# Cues that mean "the attribute you asked about has nothing more to give".
EXHAUSTED_CUES = [
    "no additional preference", "nothing else", "nothing more",
    "not quite right yet", "ask me about", "that's everything", "thats everything",
    "already told you",
]

# Strong override cues fire alone; weak ones need a colon-delimited payload too.
OVERRIDE_STRONG_CUES = [
    "ignore my", "ignore what", "ignore the", "scratch that", "disregard",
    "changed my mind", "change of plans", "forget what i", "forget my",
    "no longer", "on second thought", "instead of what", "never mind the",
    "nevermind the",
]
OVERRIDE_WEAK_CUES = ["actually", "instead", "rather", "what i need is", "what i really need"]

# Synonym expansion for user_profile.preference_tags -> catalog text hits (Stage E).
TAG_SYNONYMS = {
    "fit": ["fit", "fitted", "true to size", "tailored", "flattering"],
    "comfort": ["comfort", "comfortable", "soft", "breathable", "cozy", "cushioned"],
    "durability": ["durable", "sturdy", "heavy duty", "long lasting", "rugged", "well made"],
    "style": ["stylish", "trendy", "fashion", "fashionable", "classic", "chic"],
    "quality": ["quality", "premium", "well made", "craftsmanship"],
    "material": ["material", "fabric", "cotton", "leather"],
    "warmth": ["warm", "insulated", "thermal", "fleece", "lined"],
    "weather": ["waterproof", "weatherproof", "windproof", "water resistant"],
    "value": ["value", "affordable", "great price", "inexpensive"],
    "appearance": ["beautiful", "elegant", "looks great", "gorgeous", "cute"],
}
