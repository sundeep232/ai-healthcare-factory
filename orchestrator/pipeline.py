"""Pipeline: orchestrates M1..M4 for a Demo and owns its state transitions.

Stages are separate calls on purpose: a human reviews the blueprint and the
Terraform plan before anything that costs money (deploy) is started.

    create   (M1+M2)  -> PLANNED
    generate (M3)     -> GENERATED
    plan     (M4 dry) -> GENERATED, plan summary stored
    deploy   (M4)     -> DEPLOYING -> DEPLOYED | FAILED      (background)
    seed     (M3b)    -> SEEDING   -> DEPLOYED | FAILED      (background)
    destroy  (M4)     -> DESTROYING -> DESTROYED | FAILED    (background)
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.agents.composer import ComposeError
from orchestrator.agents.data_agents import build_context, generate_dataset
from orchestrator.agents.seeder import SeedError
from orchestrator.schemas.demo import Demo, DemoStatus
from orchestrator.storage import DemoStore, InvalidTransitionError, update

logger = logging.getLogger(__name__)

# States from which a stage may be (re)started.
_CAN_GENERATE = (DemoStatus.PLANNED, DemoStatus.GENERATED, DemoStatus.FAILED)
_CAN_PLAN = (DemoStatus.GENERATED, DemoStatus.FAILED)
_CAN_DEPLOY = (DemoStatus.GENERATED, DemoStatus.FAILED)
_CAN_SEED = (DemoStatus.DEPLOYED, DemoStatus.FAILED)
_CAN_DESTROY = (DemoStatus.DEPLOYED, DemoStatus.FAILED)


def default_seed(demo_id: str) -> int:
    """Stable per-demo seed, so preview and seed agree unless the caller overrides it."""
    return int(demo_id.replace("-", "")[:8], 16)


def _seed_for(demo_id: str, override: int | None) -> int:
    return default_seed(demo_id) if override is None else override


class Pipeline:
    """Coordinates the agents and persists progress in the store."""

    def __init__(
        self,
        store: DemoStore,
        *,
        interpreter: Any,
        planner: Any,
        generator: Any,
        composer: Any,
        seeder: Any = None,
    ) -> None:
        self.store = store
        self._interpreter = interpreter
        self._planner = planner
        self._generator = generator
        self._composer = composer
        self._seeder = seeder

    # -- M1 + M2 -----------------------------------------------------------

    def create(self, intent: str) -> Demo:
        """Interpret the intent and plan a blueprint. Persists only on success."""
        requirements = self._interpreter.interpret(intent).data
        blueprint = self._planner.plan(requirements).data
        demo = Demo(intent=intent, requirements=requirements, blueprint=blueprint)
        demo.log("plan", f"blueprint v{blueprint.version} '{blueprint.instance_slug}' with "
                         f"{len(blueprint.resources)} resources")
        return self.store.create(demo)

    # -- M3 ----------------------------------------------------------------

    def generate(self, demo_id: str) -> Demo:
        """Generate and validate Terraform for the demo's blueprint."""
        demo = self._require_state(demo_id, _CAN_GENERATE, need_blueprint=True)
        assert demo.blueprint is not None
        generated = self._generator.generate(demo.blueprint)

        def done(d: Demo) -> None:
            d.status = DemoStatus.GENERATED
            d.instance_dir = generated.directory.name
            d.plan = None  # any earlier plan belongs to the previous code
            d.error = d.failed_stage = None
            d.log("generate", f"terraform written to {generated.directory.name} "
                              f"(attempts: {generated.attempts})")

        return update(self.store, demo_id, done)

    # -- M4 ----------------------------------------------------------------

    def plan(self, demo_id: str) -> Demo:
        """Run `terraform plan` only: shows what deploy would create, changes nothing."""
        demo = self._require_state(demo_id, _CAN_PLAN, need_instance=True)
        assert demo.instance_dir
        summary = self._composer.plan(demo.instance_dir)

        def done(d: Demo) -> None:
            d.plan = summary
            d.log("plan", f"terraform plan: +{summary.add} ~{summary.change} -{summary.destroy}")

        return update(self.store, demo_id, done)

    def start_deploy(self, demo_id: str) -> Demo:
        """Atomically claim the demo for deployment (raises InvalidTransitionError if busy)."""
        self._require_state(demo_id, _CAN_DEPLOY, need_instance=True)
        self.store.begin(demo_id, _CAN_DEPLOY, DemoStatus.DEPLOYING)
        return update(self.store, demo_id, lambda d: d.log("deploy", "deployment started"))

    def run_deploy(self, demo_id: str) -> None:
        """Background worker: apply Terraform. Never raises; failures land on the demo."""
        demo = self.store.get(demo_id)
        assert demo.instance_dir
        try:
            summary, outputs = self._composer.deploy(demo.instance_dir)
        except ComposeError as exc:
            self._fail(demo_id, exc.stage, exc.detail)
            return
        except Exception as exc:  # noqa: BLE001 - a worker must always record the outcome
            logger.exception("deploy crashed for %s", demo_id)
            self._fail(demo_id, "deploy", f"unexpected error: {exc}")
            return

        def done(d: Demo) -> None:
            d.status = DemoStatus.DEPLOYED
            d.plan = summary
            d.outputs = outputs
            d.log("deploy", f"deployed: +{summary.add} resources")

        update(self.store, demo_id, done)

    # -- M3b ---------------------------------------------------------------

    def preview_data(
        self, demo_id: str, *, seed: int | None = None, sample: int = 5
    ) -> dict[str, Any]:
        """Generate the dataset in memory (no Azure) and return counts + sample rows."""
        demo = self.store.get(demo_id)
        if demo.blueprint is None:
            raise InvalidTransitionError("demo has no blueprint yet")
        ctx = build_context(demo.blueprint, seed=_seed_for(demo_id, seed))
        dataset = generate_dataset(ctx)
        return {
            "seed": ctx.seed,
            "as_of": ctx.today,
            "targets": {e.domain.value: e.target_resource_id for e in demo.blueprint.data_plan},
            "counts": dataset.counts(),
            "samples": {name: rows[:sample] for name, rows in dataset.tables.items()},
        }

    def start_seed(self, demo_id: str) -> Demo:
        """Atomically claim a deployed demo for data loading."""
        demo = self._require_state(demo_id, _CAN_SEED, need_blueprint=True)
        if not demo.outputs:
            raise InvalidTransitionError("demo is not deployed yet; deploy it before seeding")
        self.store.begin(demo_id, _CAN_SEED, DemoStatus.SEEDING)
        return update(self.store, demo_id, lambda d: d.log("seed", "data load started"))

    def run_seed(self, demo_id: str, seed: int | None = None) -> None:
        """Background worker: generate and load synthetic data. Never raises."""
        demo = self.store.get(demo_id)
        assert demo.blueprint is not None
        try:
            if self._seeder is None:
                raise SeedError("config", "no seeder configured")
            summary = self._seeder.seed(
                demo.blueprint, demo.outputs, seed=_seed_for(demo_id, seed)
            )
        except SeedError as exc:
            self._fail(demo_id, "data", f"{exc.stage}: {exc.detail}")
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("seed crashed for %s", demo_id)
            self._fail(demo_id, "data", f"unexpected error: {type(exc).__name__}: {exc}")
            return

        def done(d: Demo) -> None:
            d.status = DemoStatus.DEPLOYED
            d.data = summary
            d.error = d.failed_stage = None
            d.log("seed", f"loaded {summary.total_rows} rows (seed {summary.seed})")
            for warning in summary.warnings:
                d.log("seed", f"warning: {warning}")

        update(self.store, demo_id, done)

    def start_destroy(self, demo_id: str) -> Demo:
        self._require_state(demo_id, _CAN_DESTROY, need_instance=True)
        self.store.begin(demo_id, _CAN_DESTROY, DemoStatus.DESTROYING)
        return update(self.store, demo_id, lambda d: d.log("destroy", "teardown started"))

    def run_destroy(self, demo_id: str) -> None:
        demo = self.store.get(demo_id)
        assert demo.instance_dir
        try:
            self._composer.destroy(demo.instance_dir)
        except ComposeError as exc:
            self._fail(demo_id, exc.stage, exc.detail)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("destroy crashed for %s", demo_id)
            self._fail(demo_id, "destroy", f"unexpected error: {exc}")
            return

        def done(d: Demo) -> None:
            d.status = DemoStatus.DESTROYED
            d.outputs = {}
            d.data = None  # the databases are gone
            d.log("destroy", "all resources destroyed")

        update(self.store, demo_id, done)

    def logs(self, demo_id: str, tail: int = 200) -> str:
        demo = self.store.get(demo_id)
        return self._composer.read_log(demo.instance_dir, tail) if demo.instance_dir else ""

    # -- internals ---------------------------------------------------------

    def _fail(self, demo_id: str, stage: str, message: str) -> None:
        def mark(d: Demo) -> None:
            d.status = DemoStatus.FAILED
            d.failed_stage = stage
            d.error = message
            d.log(stage, "failed (see error / logs)")

        update(self.store, demo_id, mark)

    def _require_state(
        self,
        demo_id: str,
        allowed: tuple[DemoStatus, ...],
        *,
        need_blueprint: bool = False,
        need_instance: bool = False,
    ) -> Demo:
        demo = self.store.get(demo_id)
        if demo.status not in allowed:
            wanted = ", ".join(s.value for s in allowed)
            raise InvalidTransitionError(f"demo is '{demo.status.value}'; this needs one of: {wanted}")
        if need_blueprint and demo.blueprint is None:
            raise InvalidTransitionError("demo has no blueprint yet")
        if need_instance and not demo.instance_dir:
            raise InvalidTransitionError("no Terraform generated yet; call generate first")
        return demo
