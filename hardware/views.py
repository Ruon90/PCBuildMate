from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET
from .models import CPU, GPU, Motherboard, RAM, Storage, PSU, CPUCooler, Case
import os
import requests


MODEL_BY_TYPE = {
    'cpu': CPU,
    'gpu': GPU,
    'motherboard': Motherboard,
    'ram': RAM,
    'storage': Storage,
    'psu': PSU,
    'cooler': CPUCooler,
    'case': Case,
}


ACRONYM_MAP = {
    'cpu': 'CPU', 'gpu': 'GPU', 'psu': 'PSU', 'nvme': 'NVMe', 'ddr': 'DDR',
    'tdp': 'TDP', 'rpm': 'RPM', 'kb': 'KB', 'mb': 'MB', 'gb': 'GB',
    'l1': 'L1', 'l2': 'L2', 'url': 'URL', 'id': 'ID',
}


def prettify_label(field_name: str) -> str:
    parts = field_name.split('_')
    pretty_parts = []
    for p in parts:
        key = p.lower() if p else p
        if key in ACRONYM_MAP:
            pretty_parts.append(ACRONYM_MAP[key])
        else:
            pretty_parts.append(p.capitalize())
    return ' '.join(pretty_parts)


def format_value(val):
    if val is None or val == "":
        return "-"
    if isinstance(val, bool):
        return "Yes" if val else "No"
    # Dates, Decimals, ints, strings will stringify nicely
    return str(val)


def display_name_for(obj):
    for attr in ("name", "gpu_name", "model"):
        v = getattr(obj, attr, None)
        if v:
            return str(v)
    return f"{obj.__class__.__name__} #{getattr(obj, 'pk', '')}"


@require_GET
def component_details(request):
    ctype = (request.GET.get('type') or '').lower()
    cid = request.GET.get('id')
    if not ctype or not cid:
        return HttpResponseBadRequest('Missing type or id')
    Model = MODEL_BY_TYPE.get(ctype)
    if not Model:
        return HttpResponseBadRequest('Unknown component type')
    try:
        obj = Model.objects.get(pk=cid)
    except Model.DoesNotExist:
        return HttpResponseBadRequest('Component not found')

    rows = []
    exclude = {"slug", "price"}
    # Consider excluding implicit id from details; keep table cleaner
    exclude.add("id")
    for field in Model._meta.fields:
        fname = field.name
        if fname in exclude:
            continue
        try:
            value = getattr(obj, fname)
        except Exception:
            value = None
        rows.append({
            "label": prettify_label(fname),
            "value": format_value(value),
        })

    data = {
        "title": display_name_for(obj),
        "type": ctype,
        "rows": rows,
    }
    return JsonResponse(data)


@require_GET
def youtube_reviews(request):
    """Search YouTube for 3 review videos matching the provided query.
    Expects ?q=<search terms>. Returns { videos: [{title, url, thumb}] }.
    """
    q = (request.GET.get('q') or '').strip()
    if not q:
        return HttpResponseBadRequest('Missing query')
    api_key = os.environ.get('YOUTUBE_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        return JsonResponse({
            'error': 'YouTube API key not configured',
            'videos': []
        }, status=500)
    try:
        params = {
            'part': 'snippet',
            'q': q,
            'type': 'video',
            'maxResults': 6,
            'key': api_key,
            'safeSearch': 'moderate'
        }
        resp = requests.get('https://www.googleapis.com/youtube/v3/search', params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        videos = []
        for item in data.get('items', [])[:6]:
            vid = item.get('id', {}).get('videoId')
            sn = item.get('snippet', {})
            if not vid:
                continue
            videos.append({
                'title': sn.get('title') or 'Untitled',
                'url': f'https://www.youtube.com/watch?v={vid}',
                'thumb': (sn.get('thumbnails', {}).get('medium', {}) or sn.get('thumbnails', {}).get('default', {})).get('url')
            })
        return JsonResponse({ 'videos': videos })
    except Exception as e:
        return JsonResponse({ 'error': 'YouTube search failed', 'videos': [] }, status=500)
