"""Distinguish ordinary pacing advice from material itinerary risks."""

def serious(issue):
    if issue.get('level')=='error':return True
    code=issue.get('code','')
    if code=='unbalanced_estimate':return False
    if code=='late_arrival':return bool(issue.get('material'))
    if code=='model_timeline':return issue.get('impact')=='major'
    over=issue.get('overrun_minutes')
    available=issue.get('available_minutes')
    if isinstance(over,(int,float)):
        return over>max(60,(available or 0)*.2)
    # Legacy explicit draft warnings have no numeric metadata: keep their consent boundary.
    return code in ('estimated_capacity','estimated_period_capacity','revision_day_end') or issue.get('phase')=='route'
