"""Mission-level constant-rate sensitivity scenarios; no medical limit defaults."""
from decimal import Decimal
import math
from typing import Annotated, Literal

from pydantic import Field

from app.contracts.api import ContractModel, NonEmptyString, NonNegative
from app.contracts.workers import RadiationResult, SourceReference, WorkerContext

RATE_FACTORS = {'uSv/hour': (Decimal(1), Decimal(1)), 'uSv/day': (Decimal(1), Decimal(24)),
                'mSv/day': (Decimal(1000), Decimal(24))}


class RadiationScenario(ContractModel):
    format_version: Literal['a3-constant-rate-v1'] = 'a3-constant-rate-v1'
    scenario_id: NonEmptyString
    region_id: Literal['jezero'] = 'jezero'
    roi_id: NonEmptyString
    dataset_version: NonEmptyString
    source: SourceReference
    source_locator: NonEmptyString
    source_observation_period: NonEmptyString
    quantity: Literal['dose_equivalent'] = 'dose_equivalent'
    rate: NonNegative
    rate_uncertainty: NonNegative | None
    rate_unit: Literal['uSv/hour', 'uSv/day', 'mSv/day']
    uncertainty_description: NonEmptyString
    assumptions: Annotated[list[NonEmptyString], Field(min_length=1)]
    limitations: Annotated[list[NonEmptyString], Field(min_length=1)]
    max_duration_min: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
    budget_policy: Literal['scenario_band_v1'] = 'scenario_band_v1'


class ScenarioRadiationWorker:
    agent_id = 'A3'

    def __init__(self, scenario: RadiationScenario | None = None, provenance_ref: str | None = None):
        self.scenario = scenario
        self.provenance_ref = provenance_ref

    async def run(self, context: WorkerContext) -> RadiationResult:
        duration = context.parameters.eva_duration_min
        budget = context.parameters.radiation_budget_usv
        scenario = self.scenario
        def unavailable(reason):
            return RadiationResult(status='unavailable', data_kind='unavailable', duration_min=duration, budget_usv=budget,
                                   warnings=[reason, 'A3 dose and constraint remain unknown; no spatial radiation model is supplied.'])
        if scenario is None or not self.provenance_ref:
            return unavailable('No documented radiation scenario/provenance is configured.')
        if (context.region_id,context.roi_id,context.dataset_version) != (scenario.region_id,scenario.roi_id,scenario.dataset_version):
            return unavailable('Radiation scenario does not match the requested region, ROI or dataset version.')
        if duration is None:
            return unavailable('EVA duration is missing; no default mission duration is assumed.')
        if duration > scenario.max_duration_min:
            return unavailable('EVA duration exceeds the explicitly configured scenario duration scope.')
        numerator, denominator = RATE_FACTORS[scenario.rate_unit]
        raw_rate = Decimal(str(scenario.rate)) * numerator
        rate = raw_rate / denominator
        hours = Decimal(str(duration))/60
        dose = raw_rate * hours / denominator
        spread = (Decimal(str(scenario.rate_uncertainty))*numerator*hours/denominator
                  if scenario.rate_uncertainty is not None else (Decimal(0) if hours == 0 else None))
        if not all(math.isfinite(float(v)) and (v == 0 or float(v) != 0)
                   for v in (rate,dose) + ((spread,) if spread is not None else ())):
            return unavailable('Scenario arithmetic exceeds finite output range.')
        constraint = 'unknown'
        warnings = ['SCENARIO ONLY: constant historical dose-equivalent rate replay, not an observed or validated Jezero EVA prediction.',
                    'Budget outcomes apply only to the configured sensitivity band, not astronaut safety or a NASA exposure limit.',
                    'Uncertainty scales linearly with duration as a shared rate uncertainty; it is not divided by the square root of time.',
                    *scenario.assumptions, *scenario.limitations, scenario.uncertainty_description]
        if budget is None:
            warnings.append('No mission dose budget supplied; budget constraint is unknown.')
        elif spread is None:
            warnings.append('Rate uncertainty is unspecified; budget constraint is unknown.')
        else:
            limit = Decimal(str(budget))
            lower, upper = max(Decimal(0),dose-spread), dose+spread
            constraint = 'pass' if upper <= limit else ('fail' if lower > limit else 'unknown')
            if constraint == 'unknown':
                warnings.append('The scenario sensitivity band crosses the supplied budget; outcome is unknown.')
        return RadiationResult(status='partial',data_kind='scenario',dose_rate_usv_per_hour=float(rate),duration_min=duration,
                               dose_estimate_usv=float(dose),dose_uncertainty_usv=float(spread) if spread is not None else None,
                               budget_usv=budget,constraint_status=constraint,model_reference=self.provenance_ref,
                               provenance_ref=self.provenance_ref,artifacts={'radiation_scenario':self.provenance_ref},
                               dataset_ids=[scenario.source.dataset_id],warnings=list(dict.fromkeys(warnings)))
