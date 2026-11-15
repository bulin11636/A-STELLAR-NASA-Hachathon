"""Explicit walking estimates. These are assumptions, not physiological models."""
import math
from app.contracts.assessment import RouteAssessment, TimeEstimate


def walking_assessment(request,distance_m):
    mission=request.mission
    result=RouteAssessment(limitations=['Combined thermal/radiation risk is not calibrated; risk_score remains unknown.'])
    if mission is None: return result
    required=set(mission.required_analyses)
    if mission.radiation_budget_usv is not None: required.add('A3')
    result=result.model_copy(update={'required_unassessed':sorted(required)})
    if mission.speed_m_s is not None:
        travel=distance_m/mission.speed_m_s/60
        stop=len(request.waypoints)*mission.stop_minutes_per_waypoint
        total=travel+stop
        if all(math.isfinite(x) for x in (travel,stop,total)):
            estimate=TimeEstimate(speed_m_s=mission.speed_m_s,travel_min=travel,stop_min=stop,total_min=total,
                assumptions=['User-supplied constant projected walking speed.',
                    'Dwell applies once per required intermediate visit, including repeated visits.',
                    'No start/goal dwell, slope-dependent speed, rest, suit/load or physiological model is included.'])
            result=result.model_copy(update={'time':estimate})
        else:
            result=result.model_copy(update={'limitations':[*result.limitations,'Walking estimate exceeds finite numeric range.']})
    if mission.exposure_duration_min is not None:
        result=result.model_copy(update={'radiation_duration_min':mission.exposure_duration_min,'radiation_duration_basis':'user_supplied'})
    elif result.time is not None:
        result=result.model_copy(update={'radiation_duration_min':result.time.total_min,'radiation_duration_basis':'route_estimate'})
    return result
