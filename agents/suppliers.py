#!/usr/bin/env python3
"""
SUPPLIER DATABASE — Fournisseurs DropAtom

Données réelles de fournisseurs Chinois contactés pour le dropshipping.
Utilisé par HUNTER (match produits→fournisseurs) et BUILDER (génération store).
"""

# Chaque fournisseur = catégorie de produits + contact direct
SUPPLIERS = [
    {
        "id": "backy-zhang-jike",
        "name": "Backy Zhang",
        "company": "Zhejiang JIKE Industry & Trade",
        "phone": "+86 189 6600 8270",
        "categories": ["baby safety", "sécurité bébé", "childproofing", "baby gates", "corner guards", "cabinet locks"],
        "niche": "baby",
        "notes": "Sécurité bébé / baby safety products",
        "moq": 1,
        "ship_from": "Zhejiang, China",
        "quality": "verified",
    },
    {
        "id": "carol-wang-kulax",
        "name": "Carol Wang",
        "company": "Anhui Aerospace / PMA Health Technology / Kulax",
        "phone": "+86 551 6563 3848",
        "phone2": "+86 136 5569 7032",
        "categories": ["health", "santé", "graphene", "wellness", "therapeutic", "pain relief", "massage", "heating"],
        "niche": "health",
        "notes": "Produits santé / health technology / graphene",
        "moq": 1,
        "ship_from": "Anhui, China",
        "quality": "verified",
    },
    {
        "id": "cindy-he-waxkiss",
        "name": "Cindy He",
        "company": "Waxkiss / Guangzhou Fourto Sanitary Products",
        "phone": "+86 139 2237 0854",
        "categories": ["épilation", "wax", "waxing", "hair removal", "sanitary", "beauty", "skincare"],
        "niche": "beauty",
        "notes": "Épilation / wax / sanitary products",
        "moq": 1,
        "ship_from": "Guangzhou, China",
        "quality": "verified",
    },
    {
        "id": "daniel-elov",
        "name": "Daniel",
        "company": "ELOV Cosmetics / Song Beauty Technology",
        "phone": "+86 133 6000 7144",
        "categories": ["cosmetics", "skincare", "face care", "sérum", "cream", "beauty", "anti-aging", "moisturizer"],
        "niche": "beauty",
        "notes": "Cosmétiques / skincare / face care",
        "moq": 1,
        "ship_from": "Guangdong, China",
        "quality": "verified",
    },
    {
        "id": "echo-zhang-massage",
        "name": "Echo Zhang",
        "company": "Master Home Products / Master Massage / Hisooth / MT Chiropractic",
        "phone": "+86 135 6477 3032",
        "categories": ["massage", "massager", "chiropractic", "neck massager", "back massager", "foot massager", "massage gun", "wellness", "pain relief", "electric massager", "scalp", "eye massager", "vibroacoustic", "hisooth", "meditation", "hair regrowth", "led therapy"],
        "niche": "health",
        "notes": "Équipements massage / Hisooth wellness / MT Chiropractic — Bureaux US/UK/DE/CA",
        "moq": 1,
        "ship_from": "Zhejiang, China",
        "quality": "verified",
        "dream_match": True,  # Direct match with dream products
    },
    {
        "id": "jamie-chen-jike",
        "name": "Jamie Chen",
        "company": "Zhejiang JIKE Industry & Trade",
        "phone": "+86 189 6600 8260",
        "categories": ["baby safety", "sécurité bébé", "childproofing", "baby gates", "corner guards", "cabinet locks"],
        "niche": "baby",
        "notes": "Sécurité bébé / baby safety products",
        "moq": 1,
        "ship_from": "Zhejiang, China",
        "quality": "verified",
    },
    {
        "id": "jasmin-behealthy",
        "name": "Jasmin",
        "company": "Ningbo Behealthy Technology Group",
        "phone": "+86 155 5709 2130",
        "categories": ["breast pump", "tire-lait", "maternity", "mom-baby", "baby bottle", "nursing", "baby products"],
        "niche": "baby",
        "notes": "Tire-lait / produits maman-bébé",
        "moq": 1,
        "ship_from": "Ningbo, China",
        "quality": "verified",
    },
    {
        "id": "leo-ounai",
        "name": "Leo / HuiFeng Luo",
        "company": "Yiwu Ounai Daily Necessities",
        "phone": "+86 131 8516 0092",
        "categories": ["bathroom", "scrubber", "bath puff", "brush", "peigne", "comb", "shower cap", "sauna towel", "salle de bain", "cleaning"],
        "niche": "home",
        "notes": "Accessoires salle de bain : scrubber, bath puff, brosses, peigne, bonnet douche, serviettes sauna",
        "moq": 1,
        "ship_from": "Yiwu, China",
        "quality": "verified",
    },
    {
        "id": "lexie-baichang",
        "name": "Lexie",
        "company": "Baichang Keji",
        "phone": "+86 188 2529 2898",
        "phone2": "+86 199 5054 1174",
        "categories": ["beauty device", "skincare device", "led mask", "face device", "beauty equipment", "design", "skin care"],
        "niche": "beauty",
        "notes": "Design appareils beauté / skincare devices",
        "moq": 1,
        "ship_from": "Shenzhen, China",
        "quality": "verified",
        "dream_match": True,  # Direct match with dream products (LED face mask etc)
    },
    {
        "id": "lily-mondial",
        "name": "Lily / Lili Yanyan",
        "company": "Shenzhen Mondial Technology / Medior",
        "phone": "+86 134 2420 6656",
        "phone2": "+86 0755 8465 9336",
        "phone3": "+86 0755 2821 1481",
        "categories": ["beauty device", "esthetic", "beauty equipment", "facial", "skin care", "led therapy", "microcurrent"],
        "niche": "beauty",
        "notes": "Appareils beauté esthétiques",
        "moq": 1,
        "ship_from": "Shenzhen, China",
        "quality": "verified",
        "dream_match": True,
    },
    {
        "id": "rylie-medile",
        "name": "Rylie",
        "company": "Medile / Henan Mother & Infant",
        "phone": "+86 182 0682 8022",
        "categories": ["breast pump", "tire-lait", "maternity", "mom-baby", "baby bottle", "nursing"],
        "niche": "baby",
        "notes": "Tire-lait / produits maman-bébé",
        "moq": 1,
        "ship_from": "Henan, China",
        "quality": "verified",
    },
    {
        "id": "walker-shuge",
        "name": "Walker",
        "company": "Shenzhen Shuge Beauty / Yeahone",
        "phone": "+86 186 0163 1580",
        "phone2": "+86 159 1538 7331",
        "categories": ["beauty device", "esthetic", "beauty equipment", "facial", "skin care", "hair removal", "ipl"],
        "niche": "beauty",
        "notes": "Appareils beauté esthétiques",
        "moq": 1,
        "ship_from": "Shenzhen, China",
        "quality": "verified",
        "dream_match": True,
    },
    {
        "id": "watson-wang-cixi",
        "name": "Watson Wang",
        "company": "Ningbo Cixi Import & Export Holdings",
        "phone": "+86 139 6827 9898",
        "categories": ["trading", "import-export", "general", "all categories"],
        "niche": "general",
        "notes": "Import-export / trading général — peut sourcer n'importe quoi",
        "moq": 1,
        "ship_from": "Ningbo, China",
        "quality": "verified",
    },
    {
        "id": "zita-chen-qiancai",
        "name": "Zita Chen",
        "company": "Guangzhou Qiancai Cosmetic",
        "phone": "+86 135 7039 1635",
        "categories": ["hair care", "cosmetics", "cheveux", "shampoo", "conditioner", "hair treatment", "hair serum", "hair mask"],
        "niche": "beauty",
        "notes": "Hair care / cosmétiques cheveux",
        "moq": 1,
        "ship_from": "Guangzhou, China",
        "quality": "verified",
    },
]


def find_supplier(product_keywords: list[str] = None, niche: str = None) -> list[dict]:
    """Trouve les fournisseurs qui matchent un produit ou un niche.
    
    Args:
        product_keywords: mots-clés du produit (ex: ["neck", "massager", "electric"])
        niche: niche cible (ex: "health", "beauty", "baby")
    
    Returns:
        Liste de fournisseurs triés par pertinence (meilleur match d'abord)
    """
    if not product_keywords:
        product_keywords = []
    
    search = ' '.join(product_keywords).lower()
    if niche:
        search += f" {niche.lower()}"
    
    scored = []
    for s in SUPPLIERS:
        score = 0
        # Match par catégorie
        for cat in s["categories"]:
            if cat.lower() in search:
                score += 10
            # Partial match
            for kw in product_keywords:
                if kw.lower() in cat.lower() or cat.lower() in kw.lower():
                    score += 3
        
        # Match par niche
        if niche and s["niche"] == niche.lower():
            score += 15
        
        # Bonus dream_match
        if s.get("dream_match"):
            score += 5
        
        if score > 0:
            scored.append((score, s))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored]


def get_supplier_by_id(supplier_id: str) -> dict:
    """Trouve un fournisseur par son ID."""
    for s in SUPPLIERS:
        if s["id"] == supplier_id:
            return s
    return None


def get_suppliers_by_niche(niche: str) -> list[dict]:
    """Tous les fournisseurs d'un niche."""
    return [s for s in SUPPLIERS if s["niche"] == niche.lower()]


def print_supplier_card(s: dict):
    """Affiche une fiche fournisseur."""
    print(f"\n  🏭 {s['name']} — {s['company']}")
    print(f"     📞 {s['phone']}", end="")
    if s.get("phone2"):
        print(f" / {s['phone2']}", end="")
    print()
    print(f"     📦 {', '.join(s['categories'][:5])}")
    print(f"     📝 {s['notes']}")
    print(f"     🚢 Ships from: {s['ship_from']} | MOQ: {s['moq']}")


if __name__ == '__main__':
    print("═" * 65)
    print("  📋 DROPATOM SUPPLIER DATABASE")
    print(f"  {len(SUPPLIERS)} fournisseurs vérifiés")
    print("═" * 65)
    
    # Group by niche
    by_niche = {}
    for s in SUPPLIERS:
        by_niche.setdefault(s["niche"], []).append(s)
    
    for niche, suppliers in sorted(by_niche.items()):
        print(f"\n  [{niche.upper()}] ({len(suppliers)} fournisseurs)")
        for s in suppliers:
            dream = " ⭐" if s.get("dream_match") else ""
            print(f"    • {s['name']:20s} — {s['company'][:40]}{dream}")
            print(f"      📞 {s['phone']}")
    
    # Demo: match a dream product
    print("\n" + "═" * 65)
    print("  🔗 DREAM PRODUCT → SUPPLIER MATCHING")
    print("═" * 65)
    
    test_products = [
        (["neck massager", "electric", "pain relief"], "health"),
        (["led face mask", "acne", "skin"], "beauty"),
        (["hair growth serum", "biotin"], "beauty"),
        (["posture corrector", "back pain"], "health"),
    ]
    
    for keywords, niche in test_products:
        matches = find_supplier(keywords, niche)
        if matches:
            print(f"\n  Produit: {' '.join(keywords[:3])}")
            print(f"  → Fournisseur: {matches[0]['name']} ({matches[0]['company']})")
            print(f"    📞 {matches[0]['phone']}")
