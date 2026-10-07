"""Additive provider DTOs. Business repositories and schedules live elsewhere."""
import math
from datetime import date,timedelta
from .storage import now

SCHEMA_VERSION = 1


def coordinate(value, normalize=True):
    if not isinstance(value, str):
        return None
    try:
        lon, lat = map(float, value.split(','))
        if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -85 <= lat <= 85):
            return None
        if lon == 0 and lat == 0:
            return None
        return f'{lon:.6f},{lat:.6f}' if normalize else value.strip()
    except (ValueError, TypeError):
        return None


def scalar(value):
    return value if isinstance(value, (str, int, float)) and not isinstance(value, bool) and value != '' else None


def items_snapshot(items, conditions):
    return {'items': items, 'status': 'available' if items else 'empty',
            'schema_version': SCHEMA_VERSION, 'query_conditions': conditions,
            'checked_at': now(), 'items_count': len(items)}


def place_quality(row, provenance):
    return {'schema_version': SCHEMA_VERSION, 'coordinate_system': 'GCJ-02',
            'location_status': 'available' if row.get('location') else 'unknown',
            'unknown_fields': [key for key in ('location', 'address', 'opening', 'cost', 'telephone') if row.get(key) is None],
            'queried_at': provenance.get('queried_at'), 'date_applicability': 'visit_date_unverified'}

def guide_conditions(city,query,requirements):
    result={'city':city,'query':query}
    start=requirements.get('start_date')
    if start:
        result['visit_date']=start
        if requirements.get('days'):
            result['end_date']=(date.fromisoformat(start)+timedelta(days=int(requirements['days'])-1)).isoformat()
    return result
