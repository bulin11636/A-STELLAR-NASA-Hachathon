"""Explicitly synthetic P1 acceptance inputs; never production registration evidence."""
import hashlib
import json
from pathlib import Path


def inputs(folder):
    import numpy as np
    import rasterio
    from affine import Affine
    from pyproj import CRS
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    z=np.tile(np.arange(120,dtype='float32')*.2,(100,1))
    crs=CRS.from_user_input('+proj=eqc +lat_ts=18.4663 +lon_0=0 +R=3396190 +units=m +no_defs +type=crs').to_wkt().replace('"unknown"','"Mars_Synthetic"')
    with rasterio.open(folder/'dem.tif','w',driver='GTiff',height=100,width=120,count=1,dtype='float32',
        crs=crs,transform=Affine(20,0,4354000,0,-20,1094000),nodata=-9999) as target: target.write(z,1)
    profile=folder/'profile.json'
    profile.write_text(json.dumps(dict(dem='dem.tif',dataset_id='synthetic-p1-plane',roi_id='synthetic-p1-roi',
        window=[1,1,118,98],vertical_units='m',vertical_units_evidence='Synthetic metric plane; no real terrain data.',
        terrain_weight=4,limits=dict(max_grid_cells=262144,max_expanded_nodes=200000,max_elapsed_seconds=10))))
    return profile


def controls(grid,folder):
    from affine import Affine
    from app.planning.grid import transform_point
    from app.planning.registration import NASA_LAYER,NASA_CRS,planetographic
    folder=Path(folder);native=Affine(*grid.inventory['source_transform'])
    h,w=grid.inventory['source_shape']
    observations=[]
    for i,(c,r) in enumerate([(2.5,2.5),(w-2.5,2.5),(w-2.5,h-2.5),(2.5,h-2.5)]):
        wire=grid.wire(*transform_point(native,(c,r)))
        observations.append(dict(control_id='synthetic-'+str(i),wire=wire.model_dump(),dem_pixel=[c,r],
            wmts_coordinate=[wire.longitude,planetographic(wire.latitude)],wire_uncertainty_m=1.0,
            feature_uncertainty_m=1.0,wmts_resolution_m=1.0,wmts_matrix_id='synthetic-fine'))
    xml=f'''<Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:o="http://www.opengis.net/ows/1.1"><Contents>
<Layer><o:Identifier>{NASA_LAYER}</o:Identifier><TileMatrixSetLink><TileMatrixSet>synthetic</TileMatrixSet></TileMatrixSetLink></Layer>
<TileMatrixSet><o:Identifier>synthetic</o:Identifier><o:SupportedCRS>{NASA_CRS}</o:SupportedCRS><TileMatrix>
<o:Identifier>synthetic-fine</o:Identifier><TopLeftCorner>-180 90</TopLeftCorner><TileWidth>256</TileWidth><TileHeight>256</TileHeight><MatrixWidth>65536</MatrixWidth><MatrixHeight>32768</MatrixHeight>
</TileMatrix></TileMatrixSet></Contents></Capabilities>'''.encode()
    measurement=json.dumps(dict(data_kind='synthetic',warning='Generated test observations; no NASA feature measurements.',observations=observations)).encode()
    (folder/'synthetic-capabilities.xml').write_bytes(xml);(folder/'synthetic-measurements.json').write_bytes(measurement)
    body=dict(schema_version='1',data_kind='synthetic',measurement_method='synthetic_fixture',source_sha256=grid.source_hash,
        wmts_layer=NASA_LAYER,wmts_matrix_set='synthetic',wmts_crs=NASA_CRS,latitude_type='planetographic',
        semi_major_m=3396190.0,inverse_flattening=169.894447223612,capabilities_file='synthetic-capabilities.xml',
        capabilities_sha256=hashlib.sha256(xml).hexdigest(),measurement_file='synthetic-measurements.json',
        measurement_sha256=hashlib.sha256(measurement).hexdigest(),observations=observations)
    path=folder/'controls.json';path.write_text(json.dumps(body,indent=2)+'\n')
    return path
