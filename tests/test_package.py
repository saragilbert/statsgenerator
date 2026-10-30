import importlib

import pytest

STEPS = ["ingest", "classify", "register", "extract", "validate", "export"]


@pytest.mark.parametrize("step", STEPS)
def test_pipeline_step_importable(step: str) -> None:
    importlib.import_module(f"statsreader.{step}")
