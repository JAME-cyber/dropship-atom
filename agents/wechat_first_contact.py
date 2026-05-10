#!/usr/bin/env python3
"""
DropAtom — Contact Initial Fournisseurs WeChat
================================================
Génère les messages de 1er contact pour chaque fournisseur.
Tu copies-colles sur WeChat après les avoir ajoutés.

Usage:
  python3 wechat_first_contact.py                # Tous les fournisseurs
  python3 wechat_first_contact.py --niche beauty  # Un seul niche
  python3 wechat_first_contact.py --id echo-zhang-massage  # Un seul fournisseur
  python3 wechat_first_contact.py --product "neck massager"  # Message ciblé produit
"""

import argparse
import json
import os
import urllib.request
from pathlib import Path
from suppliers import SUPPLIERS, find_supplier

BASE_DIR = Path(__file__).parent

def generate_first_contact(supplier: dict, product_name: str = None, sell_price: float = None) -> dict:
    """Génère le message de 1er contact pour un fournisseur."""
    
    name = supplier["name"].split("/")[0].strip()
    company = supplier["company"]
    phone = supplier["phone"]
    categories = supplier["categories"]
    niche = supplier["niche"]
    
    # Message en anglais (langue internationale du business)
    if product_name:
        en_msg = f"""Hi {name},

I'm a dropshipping seller based in France, targeting the European market. I found your company {company} on Alibaba/1688.

I'm interested in your {product_name} products for my online store. Could you share:

1. Your current price list (per unit, and volume discounts for 50+ / 100+ units)
2. Sample order price and shipping cost to France
3. Production lead time
4. Do you offer custom branding / packaging?

I'm looking for a long-term partnership. My target selling price in Europe is around €{sell_price or '29.99'}.

Looking forward to your reply!

Best regards,
[Ton prénom]
DropAtom — France"""
    else:
        en_msg = f"""Hi {name},

I'm a dropshipping seller based in France, targeting the European market. I'm interested in your {categories[0] if categories else niche} products from {company}.

Could you share:
1. Your product catalog and price list
2. Sample order price + shipping to France
3. MOQ and volume discounts
4. Custom branding options

Looking for a reliable long-term supplier. 

Best regards,
[Ton prénom]
DropAtom — France"""
    
    # Version chinoise (certains fournisseurs préfèrent)
    zh_msg = f"""你好 {name}，

我是法国的跨境电商卖家，主要面向欧洲市场。我对贵公司（{company}）的产品很感兴趣。

请问能否提供：
1. 产品目录和价格表
2. 样品价格 + 寄到法国的运费
3. 起订量和批发折扣
4. 是否支持定制包装/贴牌

希望能建立长期合作关系。期待您的回复！

谢谢，
[Ton prénom]
DropAtom — 法国"""
    
    # Négociation prix (2ème message, après leur réponse)
    negotiate_msg = f"""Thanks for the quick reply {name}!

I appreciate the pricing. I'd like to discuss a few points:

1. **Price**: Could you do ${"{:.2f}".format(sell_price * 0.25 if sell_price else 8.99)} per unit for an initial order of 50 units? I plan to scale to 200+/month quickly.

2. **Samples**: Can you send 1 sample unit? I'll pay for it + shipping. I need to verify quality before placing a larger order.

3. **Shipping**: What's your fastest shipping option to France? Can you do 7-10 days?

4. **Branding**: I'd like custom packaging with my logo. What's the setup cost?

If we agree on pricing, I'm ready to place my first order this week.

Best,
[Ton prénom]"""
    
    return {
        "supplier_id": supplier["id"],
        "supplier_name": name,
        "company": company,
        "phone": phone,
        "wechat_id_hint": f"Search phone number {phone} in WeChat",
        "message_english": en_msg.strip(),
        "message_chinese": zh_msg.strip(),
        "negotiation_followup": negotiate_msg.strip(),
        "niche": niche,
    }


def main():
    parser = argparse.ArgumentParser(description="DropAtom WeChat First Contact Generator")
    parser.add_argument("--niche", help="Filter by niche (beauty, health, baby, home)")
    parser.add_argument("--id", help="Specific supplier ID")
    parser.add_argument("--product", help="Product name to mention in message")
    parser.add_argument("--price", type=float, help="Target selling price in EUR")
    parser.add_argument("--output", default=str(BASE_DIR / "output" / "wechat-contacts"))
    args = parser.parse_args()
    
    suppliers = SUPPLIERS
    
    if args.niche:
        suppliers = [s for s in suppliers if s["niche"] == args.niche.lower()]
    elif args.id:
        suppliers = [s for s in suppliers if s["id"] == args.id]
    elif args.product:
        matches = find_supplier(args.product.split())
        if matches:
            suppliers = matches[:3]  # Top 3 matches
    
    if not suppliers:
        print("❌ No suppliers found matching criteria.")
        return
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print()
    print("═" * 65)
    print(f"  📱 WECHAT FIRST CONTACT — {len(suppliers)} fournisseurs")
    print("═" * 65)
    print()
    
    contacts = []
    for s in suppliers:
        contact = generate_first_contact(s, args.product, args.price)
        contacts.append(contact)
        
        dream = " ⭐ DREAM MATCH" if s.get("dream_match") else ""
        print(f"  🏭 {contact['supplier_name']} — {contact['company']}{dream}")
        print(f"     📞 Phone/WeChat: {contact['phone']}")
        print(f"     📦 Niche: {contact['niche']}")
        print()
        print(f"     ── MESSAGE (ENGLISH) ──")
        for line in contact["message_english"].split("\n"):
            print(f"     {line}")
        print()
        print(f"     ── MESSAGE (CHINESE) ──")
        for line in contact["message_chinese"].split("\n"):
            print(f"     {line}")
        print()
        print(f"     ── NÉGOCIATION (après leur réponse) ──")
        for line in contact["negotiation_followup"].split("\n")[:5]:
            print(f"     {line}")
        print()
        print("  " + "─" * 60)
        print()
    
    # Save all contacts
    all_path = output_dir / "all-contacts.json"
    all_path.write_text(json.dumps(contacts, indent=2, ensure_ascii=False))
    
    # Save individual messages as text files (easy to copy-paste)
    for c in contacts:
        slug = c["supplier_id"]
        txt_path = output_dir / f"{slug}.txt"
        txt_path.write_text(
            f"FOURNISSEUR: {c['supplier_name']} — {c['company']}\n"
            f"PHONE/WECHAT: {c['phone']}\n"
            f"NICHE: {c['niche']}\n"
            f"\n{'='*50}\n"
            f"MESSAGE ANGLAIS (copier-coller):\n{'='*50}\n\n"
            f"{c['message_english']}\n\n"
            f"{'='*50}\n"
            f"MESSAGE CHINOIS (si l'anglais ne marche pas):\n{'='*50}\n\n"
            f"{c['message_chinese']}\n\n"
            f"{'='*50}\n"
            f"NÉGOCIATION (2ème message après leur réponse):\n{'='*50}\n\n"
            f"{c['negotiation_followup']}\n"
        )
    
    print(f"  📁 Messages sauvegardés: {output_dir}/")
    print(f"     → Copie-colle le contenu de chaque fichier .txt sur WeChat")
    print()
    print(f"  📱 Pour ajouter sur WeChat:")
    print(f"     1. Ouvre WeChat")
    print(f"     2. + → Add Contacts → Search par numéro de téléphone")
    print(f"     3. Entre le numéro +86... du fournisseur")
    print(f"     4. Envoie le message anglais")


if __name__ == "__main__":
    main()
