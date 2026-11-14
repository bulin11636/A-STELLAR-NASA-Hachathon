"""Local immutable run directories, published by atomic rename after fsync."""
import json
import os
from pathlib import Path
import re
import shutil
import math
import zipfile
from uuid import uuid4
from app.api.errors import ApiProblem
from app.contracts.routes import StoredRouteResponse
from app.planning.grid import digest

ROUTE_ID = re.compile(r'^route-[a-f0-9]{32}$')
FILES = {'grid': 'grid.npz', 'validation': 'validation.json', 'provenance': 'provenance.json'}


def write_json(path, data):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, allow_nan=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class RouteStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()

    def publish(self, route_id, build):
        stage = self.root / ('.staging-'+uuid4().hex)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            stage.mkdir(mode=0o700)
            record = build(stage)
            record = StoredRouteResponse.model_validate(record.model_dump(mode='json'))
            write_json(stage/'record.json', record.model_dump(mode='json'))
            manifest = {name:digest(stage/name) for name in ['record.json',*FILES.values()]}
            write_json(stage/'complete.json', manifest)
            for child in stage.iterdir():
                with child.open('rb') as f:
                    os.fsync(f.fileno())
            sync_dir(stage)
            # Unique server-generated ID, never a client-selected destination.
            os.rename(stage, self.root/route_id)
            sync_dir(self.root)
            return record
        except Exception as exc:
            if stage.exists():
                shutil.rmtree(stage)
            raise ApiProblem(500,'ROUTE_STORAGE_ERROR','The validated route could not be durably stored.') from exc

    def get(self, route_id):
        if not ROUTE_ID.fullmatch(route_id):
            raise ApiProblem(422,'VALIDATION_ERROR','The route identifier is malformed.')
        folder = self.root / route_id
        if not (folder/'complete.json').is_file():
            raise ApiProblem(404,'ROUTE_NOT_FOUND','No complete stored route exists for this identifier.')
        try:
            manifest = json.loads((folder/'complete.json').read_text())
            if set(manifest) != {'record.json',*FILES.values()}:
                raise ValueError('Invalid manifest')
            for name, sha in manifest.items():
                file = folder/name
                if file.is_symlink() or digest(file) != sha:
                    raise ValueError('Artifact integrity failure')
            record = StoredRouteResponse.model_validate_json((folder/'record.json').read_text())
            if record.result.route_id != route_id or set(record.metadata.artifacts) != set(FILES):
                raise ValueError('Record identity/artifact mismatch')
            for role, name in FILES.items():
                artifact = record.metadata.artifacts[role]
                if artifact.sha256 != manifest[name] or artifact.artifact_id != route_id+':'+role:
                    raise ValueError('Artifact reference mismatch')
            self._check_geometry(folder, record)
            return record
        except Exception as exc:
            raise ApiProblem(500,'ROUTE_RECORD_INVALID','The stored route or a required artifact failed validation.') from exc

    @staticmethod
    def _check_geometry(folder, record):
        import numpy as np
        meta = record.metadata.grid
        count = meta.width * meta.height
        with zipfile.ZipFile(folder/'grid.npz') as archive:
            if sum(item.file_size for item in archive.infolist()) > count*64+65536:
                raise ValueError('Oversized grid artifact')
        with np.load(folder/'grid.npz', allow_pickle=False) as grid:
            expected = {'elevation','slope','coverage','unknown','blocked','shortest_cost','safest_cost'}
            if set(grid.files) != expected:
                raise ValueError('Unexpected grid arrays')
            for name in expected:
                a = grid[name]
                if a.shape != (meta.height, meta.width):
                    raise ValueError('Grid shape and metadata disagree')
                if name in {'coverage','unknown','blocked'}:
                    if a.dtype != np.bool_:
                        raise ValueError('Grid masks must be boolean')
                elif not np.isfinite(a).all():
                    raise ValueError('Nonfinite grid array')
                if name.endswith('_cost') and np.any(a < 1):
                    raise ValueError('Invalid grid costs')
        a,b,c,d,e,f = meta.affine
        if b != 0 or d != 0 or a <= 0 or e >= 0 or not all(math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-8) for x,y in zip((a,-e),meta.planning_resolution_m)):
            raise ValueError('Grid affine/resolution disagree')
        provenance = json.loads((folder/'provenance.json').read_text())
        inventory = provenance['inventory']
        if meta.source_crs!=inventory['source_crs'] or meta.planning_crs!=inventory['source_crs']:
            raise ValueError('Source CRS and grid metadata disagree')
        if tuple(meta.source_resolution)!=tuple(inventory['source_resolution']):
            raise ValueError('Source resolution and grid metadata disagree')
        col,row,w,h = inventory['source_window']
        sa,sb,sc,sd,se,sf = inventory['source_transform']
        factor = inventory.get('resolution_factor',1)
        if type(factor) is not int or not 1 <= factor <= 32:
            raise ValueError('Invalid aggregation factor')
        expected_affine = (sa*factor,sb*factor,sc+sa*col+sb*row,sd*factor,se*factor,sf+sd*col+se*row)
        if (math.ceil(w/factor),math.ceil(h/factor)) != (meta.width,meta.height) or not all(math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-7) for x,y in zip(meta.affine,expected_affine)):
            raise ValueError('Source window and grid metadata disagree')
