# -*- coding: utf-8 -*-
"""YAML 用例加载与 Pydantic 校验。"""
from pathlib import Path

from engine.models import CaseFile, CaseSpec
from utils.yaml_utils import load_yaml


def load_cases(path: Path | str) -> list[CaseSpec]:
    raw = load_yaml(path)
    return CaseFile.model_validate(raw).cases
