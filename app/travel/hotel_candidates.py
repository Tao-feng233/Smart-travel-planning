"""One factual hotel card shape for nightly, whole-trip and keyword quotes."""

from app.core.errors import DataError
from app.integrations.responses import unwrap


def add_children(params, requirements, *, detail=False):
    if requirements.get("children"):
        if len(requirements.get("child_ages", [])) != int(requirements["children"]):
            label = "酒店详情查询" if detail else "酒店查询"
            raise DataError(label + "需要每位儿童的年龄。")
        params.update(
            childNum=int(requirements["children"]),
            childAges=requirements["child_ages"],
        )


def records(result):
    data = unwrap(result["data"])
    return data.get("hotels", []) if isinstance(data, dict) else []


def candidate(hotel, source, params, price_basis, *, suffix="", quote_fields=None):
    """Keep dated IDs and query conditions distinct; availability is not confirmed."""
    return {
        "id": "tuniu:hotel:" + str(hotel["hotelId"]) + suffix,
        "provider_id": hotel["hotelId"],
        "kind": "hotel",
        "name": hotel["hotelName"],
        "address": hotel.get("address"),
        "rating": hotel.get("commentScore"),
        "price": hotel.get("lowestPrice"),
        "price_basis": price_basis,
        "review_summary": hotel.get("commentDigest"),
        "area": hotel.get("business"),
        "room": hotel.get("roomName"),
        "window": hotel.get("roomWindow"),
        "meal": hotel.get("meal"),
        "refund": hotel.get("refund"),
        "photos": [hotel["firstPic"]] if hotel.get("firstPic") else [],
        "source": source,
        "query_conditions": params,
        **(quote_fields or {}),
        "location": None,
        "match_status": "待核对地图位置",
    }
