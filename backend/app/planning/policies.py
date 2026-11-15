"""Approved P1 engineering policies. No client- or model-selected weights."""
from dataclasses import dataclass, replace
from types import MappingProxyType
from app.contracts.assessment import MissionProfile

AGENTS=('A1','A2','A3','A4','A5','A6')
POLICY_VERSION='jezero-walking-policy-v2'
FORMULA_VERSION='relative-terrain-scenario-v2'

@dataclass(frozen=True)
class Definition:
    profile_id: str
    mode: str
    terrain_multiplier: float
    risk: tuple
    confidence: tuple

DEFINITIONS=MappingProxyType({
    'safest':Definition('safest','safest',1.5,(.75,0,.25,0,0,0),(.55,.10,.25,0,0,.10)),
    'fastest':Definition('fastest','shortest',0,(.90,0,.10,0,0,0),(.60,.10,.10,.05,0,.15)),
    'science_priority':Definition('science_priority','safest',.5,(.80,0,.20,0,0,0),(.35,.10,.10,.30,0,.15)),
    'balanced':Definition('balanced','safest',1,(.85,0,.15,0,0,0),(.45,.10,.20,.15,0,.10)),
})
# Engineering search caps, additionally constrained by the host ingestion profile.
RESOLUTIONS=MappingProxyType({
    'coarse':(2,131072,100000,5.0),
    'standard':(1,262144,200000,10.0),
    'fine':(1,524288,400000,20.0),
})

def definition(profile_id):
    return DEFINITIONS[profile_id]

def mission_profile(profile_id):
    p=definition(profile_id)
    return MissionProfile(profile_id=profile_id,version=profile_id+'-v2',
        risk_weights=dict(zip(AGENTS,p.risk)),confidence_weights=dict(zip(AGENTS,p.confidence)))

def selected_profile(request):
    return request.mission_profile or ('fastest' if request.mode=='shortest' else 'safest')

def configure_grid(base,request):
    from app.contracts.routes import Limits
    from hashlib import sha256
    explicit=request.mission_profile is not None
    policy=definition(selected_profile(request))
    weight=min(100.0,base.profile.terrain_weight*(policy.terrain_multiplier if explicit else 1))
    updates={'terrain_weight':weight}
    if request.resolution_profile is not None or explicit:
        resolution=request.resolution_profile or 'standard'
        minimum,cells,nodes,seconds=RESOLUTIONS[resolution]
        updates.update(min_resolution_factor=minimum,limits=Limits(
            max_grid_cells=min(cells,base.profile.limits.max_grid_cells),
            max_expanded_nodes=min(nodes,base.profile.limits.max_expanded_nodes),
            max_elapsed_seconds=min(seconds,base.profile.limits.max_elapsed_seconds)))
    profile=base.profile.model_copy(update=updates)
    if profile==base.profile: return base
    key=sha256((base.metadata.grid_id+profile.model_dump_json()).encode()).hexdigest()[:24]
    return replace(base,profile=profile,metadata=base.metadata.model_copy(update={'grid_id':'grid-'+key}))

def catalog():
    return dict(schema_version='2',policy_version=POLICY_VERSION,formula_version=FORMULA_VERSION,
        score_scale='0..100',mission_mode='walking',profiles=[dict(
            **mission_profile(p.profile_id).model_dump(mode='json'),mode=p.mode,
            terrain_weight_multiplier=p.terrain_multiplier,default_resolution='standard',
            eta_model='constant_projected_speed_v1',requires_user_speed=True,
            required_risk_factors=['A1','A3'],
            limitations=['Engineering terrain/scenario comparison, not astronaut safety.',
                'Science priority preserves explicit visits; unranked science context cannot create a science cost.'])
            for p in DEFINITIONS.values()],
        resolutions=[dict(profile_id=k,version='resolution-v1',minimum_native_factor=v[0],
            max_grid_cells=v[1],max_expanded_nodes=v[2],max_elapsed_seconds=v[3],
            bounds='Additionally capped by the host; actual cells may be coarser for regional routes.') for k,v in RESOLUTIONS.items()])
