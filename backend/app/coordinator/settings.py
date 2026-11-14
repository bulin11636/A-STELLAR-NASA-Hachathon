"""Backend-only configuration. Reading an env file never executes shell text."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[3]


def environment():
    values = {}
    path = Path(os.environ.get('A_STELLAR_ENV_FILE', str(REPO/'.env'))).expanduser()
    if path.is_file():
        for raw in path.read_text(encoding='utf-8-sig').splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            match = re.fullmatch(r'(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)', line)
            if not match:
                raise ValueError('Invalid env-file assignment; values were not logged.')
            key, value = match.groups()
            if value[:1] in ('"', "'") and value[-1:] == value[:1]:
                value = value[1:-1]
            else:
                value = value.split(' #', 1)[0].strip()
            values[key] = value
    elif 'A_STELLAR_ENV_FILE' in os.environ:
        raise ValueError('The explicitly configured env file is unavailable.')
    return {**values, **os.environ}


@dataclass
class AgentSettings:
    enabled: bool = False
    api_key: str | None = field(default=None, repr=False)
    model: str = 'gpt-6.1-sol'
    reasoning_effort: str = 'medium'
    max_calls: int = 20
    budget_usd: float = 2.0
    max_input_bytes: int = 6000  # conservative UTF-8 budget; protocol allowance is additional
    max_output_tokens: int = 4096
    evidence_profile: Path | None = None
    usage_root: Path = REPO/'data/processed/a0-model-usage'

    @classmethod
    def read(cls, env):
        mode = env.get('A_STELLAR_A0_MODE', 'agentic' if env.get('OPENAI_API_KEY') else 'deterministic')
        if mode not in ('agentic','deterministic'):
            raise ValueError('A_STELLAR_A0_MODE must be agentic or deterministic.')
        settings = cls(enabled=mode=='agentic', api_key=env.get('OPENAI_API_KEY'),
            model=env.get('A_STELLAR_A0_MODEL','gpt-6.1-sol'),
            max_calls=int(env.get('A_STELLAR_A0_MAX_REQUESTS','20')),
            budget_usd=float(env.get('A_STELLAR_A0_BUDGET_USD','2')),
            usage_root=Path(env.get('A_STELLAR_A0_USAGE_STORE',str(REPO/'data/processed/a0-model-usage'))).expanduser().resolve(),
            evidence_profile=Path(env['A_STELLAR_EVIDENCE_PROFILE']).expanduser().resolve() if env.get('A_STELLAR_EVIDENCE_PROFILE') else None)
        if settings.model != 'gpt-6.1-sol':
            raise ValueError('This metered provider currently supports gpt-6.1-sol pricing only.')
        if not 1 <= settings.max_calls <= 100000 or not 0 < settings.budget_usd <= 10000:
            raise ValueError('Invalid model usage budget.')
        return settings
