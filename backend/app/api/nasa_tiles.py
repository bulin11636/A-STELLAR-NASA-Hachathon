"""Same-origin delivery for two fixed NASA Mars Trek imagery layers."""
from functools import lru_cache
import re
from app.api.errors import ApiProblem

LAYERS={'Mars_Viking_MDIM21_ClrMosaic_global_232m',
    'NES_JEZ_MID_Visible_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018'}


def resource_url(layer_id,resource):
    if layer_id not in LAYERS:
        raise ApiProblem(404,'NASA_LAYER_NOT_FOUND','Unknown NASA imagery layer.')
    if resource=='WMTSCapabilities.xml':
        return f'https://trek.nasa.gov/tiles/Mars/EQ/{layer_id}/1.0.0/{resource}','application/xml'
    resource=resource.lstrip('/')
    match=re.fullmatch(r'default/(default028mm)/(\d{1,2})/(\d{1,7})/(\d{1,7})\.(jpg|png)',resource)
    if not match:
        raise ApiProblem(400,'INVALID_NASA_TILE','Unsupported NASA tile request.')
    _,level,row,column,extension=match.groups();level,row,column=map(int,(level,row,column))
    if not 0<=level<=20 or row>=2**level or column>=2**(level+1):
        raise ApiProblem(400,'INVALID_NASA_TILE','Tile indices exceed the supported matrix.')
    return f'https://trek.nasa.gov/tiles/Mars/EQ/{layer_id}/1.0.0//{resource}','image/jpeg' if extension=='jpg' else 'image/png'


@lru_cache(maxsize=128)
def fetch_resource(layer_id,resource):
    import httpx
    url,media_type=resource_url(layer_id,resource)
    try:
        with httpx.Client(timeout=15,follow_redirects=False) as client:
            with client.stream('GET',url,headers={'User-Agent':'A-STELLAR-demo/0.1'}) as response:
                if response.status_code==404:
                    raise ApiProblem(404,'NASA_TILE_MISSING','NASA imagery has no tile at this location.')
                response.raise_for_status()
                content=bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content)>2_000_000: raise ValueError('Bounded NASA response exceeded')
        return bytes(content),media_type
    except (httpx.HTTPError,ValueError):
        raise ApiProblem(503,'NASA_IMAGERY_UNAVAILABLE','NASA imagery could not be loaded. Retry the map later.') from None
