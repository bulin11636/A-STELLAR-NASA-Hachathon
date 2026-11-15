import type { useRoutePlanner } from "../services/useRoutePlanner.ts";
const analyses = [
  ["A2", "Thermal Environment and Exposure Context"],
  ["A3", "Radiation Exposure and Mission Dose Assessment"],
  ["A4", "Geological Context and Science Opportunity"],
  ["A6", "Rover Traverse and Observation Evidence"],
] as const;
export default function MissionSettings({ planner }: { planner: ReturnType<typeof useRoutePlanner> }) {
  return <fieldset aria-label="Walking mission assumptions"><legend>Walking mission assumptions</legend>
    <label>Mission profile
      <select value={planner.missionProfile} onChange={event => planner.setMissionProfile(event.target.value as typeof planner.missionProfile)}>
        <option value="balanced">Balanced</option>
        <option value="safest">Safest</option>
        <option value="fastest">Fastest</option>
        <option value="science_priority">Science priority</option>
      </select>
    </label>
    <p>Selects the documented weighting profile for this request. It does not override a failed or unassessed hard safety gate.</p>
    <p>Walking only. Enter your assumed speed to estimate time. A0 selects relevant available specialists; required analyses cannot be skipped.</p>
    <label>Walking speed (m/s)<input type="number" min="0.001" max="20" step="any" value={planner.walkingSpeed} onChange={e => planner.setWalkingSpeed(e.target.value)} placeholder="Required for time estimate" /></label>
    <label>Dwell per intermediate visit (min)<input type="number" min="0" max="1440" step="any" value={planner.waypointDwell} onChange={e => planner.setWaypointDwell(e.target.value)} /></label>
    <label>Explicit exposure duration (min, optional)<input type="number" min="0" max="10080" step="any" value={planner.exposureDuration} onChange={e => planner.setExposureDuration(e.target.value)} /></label>
    <label>Scenario radiation budget (µSv, optional)<input type="number" min="0" step="any" value={planner.radiationBudget} onChange={e => planner.setRadiationBudget(e.target.value)} /></label>
    <p>Without an explicit exposure duration, a configured radiation scenario uses the walking estimate. Historical scenarios do not certify Jezero EVA safety.</p>
    <fieldset><legend>Required analyses</legend>{analyses.map(([id,name]) => <label key={id}><input type="checkbox" checked={planner.requiredAnalyses.includes(id)} onChange={() => planner.setRequiredAnalyses(planner.requiredAnalyses.includes(id) ? planner.requiredAnalyses.filter(a => a !== id) : [...planner.requiredAnalyses,id])} /> {name}</label>)}</fieldset>
  </fieldset>;
}
