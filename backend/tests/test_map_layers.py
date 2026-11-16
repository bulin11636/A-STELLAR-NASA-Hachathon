import numpy as np
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile

from app.main import create_app
from app.planning.service import PlanningService
from test_planning import fixture_profile


def test_preview_uses_real_dem_and_missing_rasters_are_explicit(tmp_path):
    planning=PlanningService('computed',fixture_profile(tmp_path,np.arange(224).reshape(14,16)*.01),tmp_path/'routes')
    with TestClient(create_app(planning=planning)) as client:
        layers=client.get('/api/v1/map/layers').json()['layers']
        dem=next(layer for layer in layers if layer['id']=='dem_surface')
        assert dem['available'] and dem['extent'][0]<dem['extent'][2]
        assert all(not layer['available'] for layer in layers if layer['id']!='dem_surface')
        response=client.get(dem['image_url'])
        assert response.status_code==200,response.text
        assert response.headers['content-type']=='image/png'
        with MemoryFile(response.content) as mem:
            with mem.open() as src:
                assert (src.width,src.height,src.count)==(512,512,2)
                assert src.read(2).max()==255
        assert client.get('/api/v1/map/layers/thermal.png').status_code==404
        assert client.get('/api/v1/map/layers/unknown.png').status_code==404


def test_no_dem_catalog_does_not_claim_spatial_layers(tmp_path):
    with TestClient(create_app(planning=PlanningService('mock',output_root=tmp_path))) as client:
        assert all(not layer['available'] for layer in client.get('/api/v1/map/layers').json()['layers'])
