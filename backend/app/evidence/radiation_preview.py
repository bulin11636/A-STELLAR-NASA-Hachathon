"""Explicit offline A3 scenario demonstration and optional raw RAD inspection."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from app.agents.a3 import RadiationScenario, ScenarioRadiationWorker
from app.contracts.workers import MissionParameters, WorkerContext
from app.agents.a3.inspection import inspect_cached


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, help='Explicit documented dose-equivalent scenario JSON; none means unavailable')
    parser.add_argument('--rad-cache', type=Path, help='Optional downloaded MSL RAD root with source receipts; independent of scenario rate')
    parser.add_argument('--duration-min', type=float)
    parser.add_argument('--budget-usv', type=float, help='User-selected demonstration budget, never a default NASA/medical limit')
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[3]/'data/processed/a3')
    args = parser.parse_args()
    try:
        parameters = MissionParameters(eva_duration_min=args.duration_min, radiation_budget_usv=args.budget_usv)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        inspection_ref = None
        inspection = inspect_cached(args.rad_cache) if args.rad_cache else None
        if inspection:
            content = inspection.model_dump_json(indent=2)
            inspection_ref = args.output_dir.resolve()/f'rad-inspection-{hashlib.sha256(content.encode()).hexdigest()[:16]}.json'
            inspection_ref.write_text(content,encoding='utf-8')
        scenario = None
        scenario_ref = None
        if args.scenario:
            scenario = RadiationScenario.model_validate_json(args.scenario.read_bytes())
            content = scenario.model_dump_json(indent=2)
            scenario_ref = args.output_dir.resolve()/f'scenario-{hashlib.sha256(content.encode()).hexdigest()[:16]}.json'
            scenario_ref.write_text(content,encoding='utf-8')
        context = WorkerContext(mission_id='a3-offline-preview',region_id='jezero',
                                roi_id=scenario.roi_id if scenario else 'jezero-evidence-preview-v1',
                                dataset_version=scenario.dataset_version if scenario else 'unconfigured',parameters=parameters)
        result = asyncio.run(ScenarioRadiationWorker(scenario, str(scenario_ref) if scenario_ref else None).run(context))
        report = {'context':context.model_dump(mode='json'),'result':result.model_dump(mode='json'),
                  'inspection_ref':str(inspection_ref) if inspection_ref else None,
                  'inspection_summary':{'observations':len(inspection.observations),
                                        'baseline_eligible':sum(o.baseline_eligible for o in inspection.observations),
                                        'warnings':inspection.warnings} if inspection else None}
        content = json.dumps(report,indent=2)
        output = args.output_dir.resolve()/f'a3-result-{hashlib.sha256(content.encode()).hexdigest()[:16]}.json'
        output.write_text(content,encoding='utf-8')
        print(json.dumps({**report,'report_ref':str(output)},indent=2))
    except (OSError,ValueError,KeyError) as error:
        parser.exit(1,f'A3 preview failed: {error}\n')


if __name__ == '__main__':
    main()
