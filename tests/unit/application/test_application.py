import pytest
import time
import asyncio

from interlock.application import HasLifecycle, ApplicationBuilder, Application


class ComponentA(HasLifecycle):
    def __init__(self):
        self.started_at = None
        self.stopped_at = None

    async def on_startup(self):
        self.started_at = time.monotonic()
        await asyncio.sleep(0.01)

    async def on_shutdown(self):
        self.stopped_at = time.monotonic()
        await asyncio.sleep(0.01)


class ComponentB(ComponentA):
    pass


@pytest.fixture
def base_application_with_lifecycle_components(base_app_builder: ApplicationBuilder):
    return (
        base_app_builder.register_dependency(ComponentA)
        .register_dependency(ComponentB)
        .build()
    )


@pytest.mark.asyncio
async def test_boots_components_in_order(
    base_application_with_lifecycle_components: Application,
):
    async with base_application_with_lifecycle_components:
        pass

    component_a = base_application_with_lifecycle_components.resolve(ComponentA)
    component_b = base_application_with_lifecycle_components.resolve(ComponentB)

    assert component_a.started_at < component_b.started_at


@pytest.mark.asyncio
async def test_shuts_down_components_in_reverse_order(
    base_application_with_lifecycle_components: Application,
):
    async with base_application_with_lifecycle_components:
        pass

    component_a = base_application_with_lifecycle_components.resolve(ComponentA)
    component_b = base_application_with_lifecycle_components.resolve(ComponentB)

    assert component_a.stopped_at > component_b.stopped_at
