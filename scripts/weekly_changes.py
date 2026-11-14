"""Passenger-facing comparisons of D with D+7, preserving exact departures."""
from collections import Counter


def difference(before, after):
    """Multisets: simultaneous departures are separate boardable journeys."""
    a, b = Counter(before), Counter(after)
    return sorted((b-a).elements()), sorted((a-b).elements())


def describe(before, after):
    a = before['departures'] if before else []
    b = after['departures'] if after else []
    added, removed = difference(a, b)
    schedule = a != b
    route = bool(before and after and before['routes'] != after['routes'])
    tags = []
    if schedule:
        tags.append('לוח הזמנים השתנה')
    if not a and b:
        tags.append('נוסף שירות ביום זה')
    elif a and not b:
        tags.append('לא יפעל שירות ביום זה')
    elif a and b:
        # Say "added" only when every original departure still exists; otherwise
        # describe the observed boundary without claiming trip identity.
        if not removed and any(t < a[0] for t in added):
            tags.append('נוספו נסיעות מוקדמות יותר ביום זה')
        if not removed and any(t > a[-1] for t in added):
            tags.append('נוספו נסיעות מאוחרות יותר ביום זה')
        for label, idx in [('הראשונה', 0), ('האחרונה', -1)]:
            if a[idx] != b[idx]:
                direction = 'מוקדם' if b[idx] < a[idx] else 'מאוחר'
                tags.append(f'הנסיעה {label} ביום זה תצא {direction} יותר')
        if any(a[0] <= t <= a[-1] for t in added):
            tags.append('נוספו יציאות במהלך היום')
        if any(b[0] <= t <= b[-1] for t in removed):
            tags.append('הוסרו יציאות במהלך היום')
        if len(a) != len(b):
            tags.append('מספר הנסיעות גדל' if len(b) > len(a) else 'מספר הנסיעות קטן')
    if route:
        tags.append('המסלול השתנה')
    return schedule, route, tags


def summary(profile):
    times = profile['departures'] if profile else []
    return dict(count=len(times), first=times[0] if times else None,
                last=times[-1] if times else None,
                meanInterval=round((times[-1]-times[0])/(len(times)-1)) if len(times)>1 else None)
