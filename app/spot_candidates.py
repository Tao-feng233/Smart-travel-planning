"""Four-item MCP batches drawn from covered places and resolved to real map POIs."""
import asyncio

from . import providers
from .data_coverage import covered_places, place_key, require_city
from .data_contracts import items_snapshot
from .locations import coordinate

BATCH_SIZE = 4


def _matches_topic(city, name, words):
    key = place_key(city, name)
    for word in words:
        topic = place_key(city, word)
        if word in name or (topic and topic in key):
            return True
    return False


async def get_batch(city, keywords=None, offset=0, exclude_ids=None, exclude_names=None):
    """Resolve up to four covered places and advance through the finite source list."""
    from .discovery import main_pois

    require_city(city)
    if not isinstance(offset, int) or offset < 0 or offset > 200:
        raise providers.DataError('景点批次位置无效。')
    excluded = set(exclude_ids or [])
    excluded_names = {place_key(city, name) for name in exclude_names or []}
    names = [name for name in covered_places(city) if place_key(city, name) not in excluded_names]
    # Topics order known records; they are never sent as vague names such as “休闲”.
    words = [str(word) for word in keywords or [] if str(word).strip()]
    if words:
        names.sort(key=lambda name: not _matches_topic(city, name, words))

    items = []
    seen = set()
    cursor = min(offset, len(names))
    failures = excluded_locations = attempts = 0

    async def resolve(name):
        rows = await providers.search_poi(city, name, 'spot', page=1, page_size=BATCH_SIZE)
        rows = [p for p in main_pois(rows) if place_key(city, p['name']) == place_key(city, name)]
        valid = [p for p in rows if coordinate(p.get('location'))]
        return name, valid, not valid and bool(rows)

    while cursor < len(names) and len(items) < BATCH_SIZE:
        # Query only enough records to fill the current batch; partial batches keep a real cursor.
        group = names[cursor:cursor + BATCH_SIZE - len(items)]
        results = await asyncio.gather(*(resolve(name) for name in group), return_exceptions=True)
        cursor += len(group)
        attempts += len(group)
        for resolved in results:
            if isinstance(resolved, Exception):
                failures += 1
                continue
            name, rows, unlocated = resolved
            excluded_locations += bool(unlocated)
            found = next((p for p in rows if p['id'] not in excluded
                          and p.get('parent_id') not in excluded and p['id'] not in seen), None)
            if found:
                seen.add(found['id'])
                items.append({**found, 'coverage_name': name})

    conditions = {'city': city, 'keywords': words, 'offset': offset}
    result = {
        **items_snapshot(items, conditions),
        'batch_size': BATCH_SIZE,
        'next_offset': cursor,
        'exhausted': cursor >= len(names),
        'covered_count': len(names),
        'query_failures': failures,
        'excluded_locations': excluded_locations,
        'conditions': conditions,
        'note': '只从已有资料的地点中查找地图坐标，每批最多4个；不足不虚构地点。',
    }
    if attempts and failures == attempts:
        result.update(status='query_failed', reason='地图地点查询暂未成功，请稍后重试；已有选择保留。')
    return result
