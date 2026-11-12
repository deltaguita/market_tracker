"""
依標題過濾搜尋結果。

Mercari 搜尋會把只符合品牌的商品混進結果，因此在 urls.json 的追蹤項目可設定
`must_match`：每一組別名中至少要有一個出現在標題，所有組別都要命中才保留。
例如 [["mammut", "マムート"], ["trion", "トリオン"]] 代表品牌與型號都要出現。
"""

import unicodedata
from typing import Dict, List, Optional


def _normalize(text: str) -> str:
    """NFKC（全形轉半形）後 casefold，使比對不分大小寫。"""
    return unicodedata.normalize("NFKC", text or "").casefold()


def matches_title(title: str, must_match: Optional[List[List[str]]]) -> bool:
    """所有別名組都至少有一個別名出現在標題中；未設定則一律通過。"""
    if not must_match:
        return True
    normalized_title = _normalize(title)
    return all(
        any(_normalize(alias) in normalized_title for alias in group if alias)
        for group in must_match
    )


def filter_products(
    products: List[Dict], must_match: Optional[List[List[str]]]
) -> List[Dict]:
    """過濾商品清單，被剔除的標題會印在 log 方便檢查是否誤殺。"""
    if not must_match:
        return products

    kept = []
    for product in products:
        if matches_title(product.get("title", ""), must_match):
            kept.append(product)
        else:
            print(f"  Filtered out (title mismatch): {product.get('title', '')[:60]}")
    print(f"Title filter: kept {len(kept)}/{len(products)}")
    return kept
