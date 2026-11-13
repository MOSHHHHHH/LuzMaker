"""Static station search, exact-stop route choices, and precomputed 300m neighbours."""
import hashlib
import json
import math
from collections import defaultdict

EARTH_METRES=6371008.8
RADIUS_METRES=300
CELL_DEGREES=.005


def point(lat,lon):
    try:
        lat,lon=float(lat),float(lon)
        return (lat,lon) if math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180 else None
    except (ValueError,TypeError):
        return None


def distance(a,b):
    p,q=map(math.radians,(a[0],b[0]))
    dp=math.radians(b[0]-a[0]);dl=math.radians(b[1]-a[1])
    h=math.sin(dp/2)**2+math.cos(p)*math.cos(q)*math.sin(dl/2)**2
    return 2*EARTH_METRES*math.asin(math.sqrt(min(1,max(0,h))))


def neighbours(stations,radius=RADIUS_METRES):
    grid=defaultdict(list)
    def cell(p):return math.floor(p[0]/CELL_DEGREES),math.floor(p[1]/CELL_DEGREES)
    located={code:row['point'] for code,row in stations.items() if row['point']}
    for code,p in located.items():grid[cell(p)].append(code)
    result={code:[] for code in stations}
    for code,p in located.items():
        cy,cx=cell(p)
        # Latitude/longitude buckets are only candidates. The final cutoff is
        # the great-circle distance, never a rounded grid approximation.
        dy=math.ceil(math.degrees(radius/EARTH_METRES)/CELL_DEGREES)+1
        dx=math.ceil(math.degrees(radius/EARTH_METRES)/max(.000001,math.cos(math.radians(p[0])))/CELL_DEGREES)+1
        if dx>100:
            candidates=located.keys()
        else:
            candidates=(other for y in range(cy-dy,cy+dy+1) for x in range(cx-dx,cx+dx+1) for other in grid.get((y,x),()))
        found=[]
        for other in candidates:
            if other==code:continue
            metres=distance(p,located[other])
            if metres<=radius:
                found.append((metres,other))
        result[code]=[[other,stations[other]['name'],round(metres)] for metres,other in sorted(found)]
    return result


def write_directory(data_dir,stops,route_choices,start,updated):
    stations={}
    for code,name,lat,lon in stops.values():
        if code not in stations:stations[code]={'name':name,'point':point(lat,lon)}
        elif stations[code]['point'] is None:stations[code]['point']=point(lat,lon)
    nearby=neighbours(stations)
    directory=data_dir/'stations';directory.mkdir(exist_ok=True)
    for code,row in stations.items():
        choices={}
        for source in route_choices.get(code,[]):
            key=(source[0],source[1])
            if key not in choices:
                value=list(source[:10]);value.extend(['']*(10-len(value)));value.append([])
                choices[key]=value
            if source[5] not in choices[key][10]:choices[key][10].append(source[5])
        for value in choices.values():
            value[10].sort();value[5]=value[10][0]
        payload={'code':code,'name':row['name'],'location':row['point'],'nearby':nearby[code],
                 'radiusMetres':RADIUS_METRES,'start':start,'updated':updated,
                 'routes':sorted(choices.values(),key=lambda x:(x[0],x[1],x[5]))}
        name=hashlib.sha256(code.encode()).hexdigest()[:20]+'.json'
        (directory/name).write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    search={'updated':updated,'stops':[[code,row['name']] for code,row in sorted(stations.items())]}
    (data_dir/'station-search.json').write_text(json.dumps(search,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return len(stations)
