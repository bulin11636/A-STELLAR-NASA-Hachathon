import { useEffect,useState } from 'react';
import type { useRoutePlanner } from '../services/useRoutePlanner.ts';
import { getPlanningPolicies,type PolicyCatalog } from '../services/planningPolicies.ts';
const analyses = [
  ['A2', 'Thermal Environment and Exposure Context'],
  ['A3', 'Radiation Exposure and Mission Dose Assessment'],
  ['A4', 'Geological Context and Science Opportunity'],
  ['A6', 'Rover Traverse and Observation Evidence'],
] as const;
const labels={safest:'Safest',fastest:'Fastest',science_priority:'Science priority',balanced:'Balanced'};
export default function MissionSettings({ planner }: { planner: ReturnType<typeof useRoutePlanner> }) {
  const [catalog,setCatalog]=useState<PolicyCatalog|null>(null);
  const [policyError,setPolicyError]=useState<string|null>(null);
  useEffect(()=>{
    const controller=new AbortController();
    getPlanningPolicies(controller.signal).then(value=>{if(!controller.signal.aborted)setCatalog(value);}).catch(()=>{if(!controller.signal.aborted)setPolicyError('Planning policies are unavailable. Reload before selecting a mission profile.');});
    return ()=>controller.abort();
  },[]);
  return <fieldset aria-label="Walking mission assumptions"><legend>Walking mission assumptions</legend>
    <label>Mission profile
      <select aria-label="Mission profile" disabled={!catalog} value={planner.missionProfile ?? ''} onChange={event=>{
        const profile=catalog?.profiles.find(item=>item.profile_id===event.target.value);
        planner.setMissionProfile(profile?.profile_id ?? null,profile?.mode);
      }}>
        <option value="">Use route preference</option>
        {catalog?.profiles.map(profile=><option key={profile.profile_id} value={profile.profile_id}>{labels[profile.profile_id]}</option>)}
      </select>
    </label>
    <label>Planning resolution
      <select aria-label="Planning resolution" disabled={!catalog} value={planner.resolutionProfile ?? ''} onChange={event=>planner.setResolutionProfile((event.target.value || null) as typeof planner.resolutionProfile)}>
        <option value="">Automatic</option>
        {catalog?.resolutions.map(option=><option key={option.profile_id} value={option.profile_id}>{option.profile_id[0].toUpperCase()+option.profile_id.slice(1)}</option>)}
      </select>
    </label>
    {policyError && <p role="status">{policyError}</p>}
    <p>Uses backend-approved weights and limits. Actual cells may be coarser for regional routes; a profile never bypasses a blocked or unassessed mission gate.</p>
    <p>Walking only. Enter your assumed speed to estimate time. A0 selects relevant available specialists; required analyses cannot be skipped.</p>
    <label>Walking speed (m/s)<input type="number" min="0.001" max="20" step="any" value={planner.walkingSpeed} onChange={e => planner.setWalkingSpeed(e.target.value)} placeholder="Required for time estimate" /></label>
    <label>Dwell per intermediate visit (min)<input type="number" min="0" max="1440" step="any" value={planner.waypointDwell} onChange={e => planner.setWaypointDwell(e.target.value)} /></label>
    <label>Explicit exposure duration (min, optional)<input type="number" min="0" max="10080" step="any" value={planner.exposureDuration} onChange={e => planner.setExposureDuration(e.target.value)} /></label>
    <label>Scenario radiation budget (µSv, optional)<input type="number" min="0" step="any" value={planner.radiationBudget} onChange={e => planner.setRadiationBudget(e.target.value)} /></label>
    <p>Without an explicit exposure duration, a configured radiation scenario uses the walking estimate. Historical scenarios do not certify Jezero EVA safety.</p>
    <fieldset><legend>Required analyses</legend>{analyses.map(([id,name]) => <label key={id}><input type="checkbox" checked={planner.requiredAnalyses.includes(id)} onChange={() => planner.setRequiredAnalyses(planner.requiredAnalyses.includes(id) ? planner.requiredAnalyses.filter(a => a !== id) : [...planner.requiredAnalyses,id])} /> {name}</label>)}</fieldset>
  </fieldset>;
}
