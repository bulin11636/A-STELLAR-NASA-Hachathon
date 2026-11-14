from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes import router
from app.api.frontend import mount_frontend
from app.planning.service import PlanningService
from app.coordinator.dispatcher import AgentDispatcher
from app.coordinator.mission import MissionCoordinator, default_registry
from app.coordinator.settings import AgentSettings, environment
from app.coordinator.route_agent import RouteAgent
from app.coordinator.chat import RouteChat


def create_app(coordinator: MissionCoordinator | None = None, *, planning: PlanningService | None = None, route_agent=None, static_dir=None) -> FastAPI:
    application = FastAPI(title="A-STELLAR API", version="0.1.0")
    application.state.coordinator = coordinator or MissionCoordinator(AgentDispatcher(default_registry()))
    if planning is None:
        env=environment()
        planning=PlanningService(env.get('A_STELLAR_ROUTING_MODE','mock'),env.get('A_STELLAR_PLANNING_PROFILE'),
            env.get('A_STELLAR_ROUTE_STORE'),dataset_root=env.get('A_STELLAR_DATASET_DIR'))
        settings=AgentSettings.read(env)
        if static_dir is None:
            static_dir = env.get('A_STELLAR_STATIC_DIR')
    else:
        settings=AgentSettings()  # explicit injection keeps ordinary tests offline
    application.state.planning = planning
    application.state.route_agent = route_agent or RouteAgent(settings,planning)
    application.state.chat = RouteChat(application.state.route_agent)
    register_error_handlers(application)
    application.include_router(router)
    if static_dir:
        mount_frontend(application, static_dir)
    return application


app = create_app()
