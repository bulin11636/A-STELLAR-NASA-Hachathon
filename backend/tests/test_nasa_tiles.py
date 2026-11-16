import httpx
import pytest
from app.api.errors import ApiProblem
from app.api.nasa_tiles import resource_url,fetch_resource

LAYER='Mars_Viking_MDIM21_ClrMosaic_global_232m'


def test_proxy_only_accepts_fixed_layers_and_valid_tile_indices():
    url,kind=resource_url(LAYER,'default/default028mm/1/0/2.jpg')
    assert '/1.0.0//default/' in url and kind=='image/jpeg'
    for layer,resource in [('https://private.example','WMTSCapabilities.xml'),
        (LAYER,'../../private'),(LAYER,'default/default028mm/1/5/0.jpg'),
        (LAYER,'default/default028mm/21/0/0.png')]:
        with pytest.raises(ApiProblem):resource_url(layer,resource)


def test_proxy_caches_success_without_forwarding_credentials(monkeypatch):
    calls=[]
    original=httpx.Client
    def handler(request):
        calls.append(request)
        assert 'authorization' not in request.headers
        return httpx.Response(200,content=b'NASA fixture image')
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    fetch_resource.cache_clear()
    try:
        assert fetch_resource(LAYER,'default/default028mm/0/0/0.jpg')==(b'NASA fixture image','image/jpeg')
        fetch_resource(LAYER,'default/default028mm/0/0/0.jpg')
        assert len(calls)==1
    finally:fetch_resource.cache_clear()
