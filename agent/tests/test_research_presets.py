"""Validation tests for research engine YAML presets."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PRESETS_DIR = Path(__file__).resolve().parent.parent / "src" / "swarm" / "presets"
RESEARCH_PRESETS = [
    "scan_trends",
    "research_trends",
    "scan_industries",
    "research_industries",
    "scan_stocks",
    "research_stocks",
]


@pytest.fixture(params=RESEARCH_PRESETS)
def preset_data(request):
    path = PRESETS_DIR / f"{request.param}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestPresetStructure:
    def test_all_presets_exist(self):
        for name in RESEARCH_PRESETS:
            path = PRESETS_DIR / f"{name}.yaml"
            assert path.exists(), f"Preset {name}.yaml not found"

    def test_has_required_fields(self, preset_data):
        assert "name" in preset_data
        assert "agents" in preset_data
        assert "tasks" in preset_data
        assert isinstance(preset_data["agents"], list)
        assert isinstance(preset_data["tasks"], list)

    def test_agents_have_required_fields(self, preset_data):
        for agent in preset_data["agents"]:
            assert "id" in agent, f"Agent missing id: {agent}"
            assert "role" in agent
            assert "system_prompt" in agent
            assert "tools" in agent
            assert isinstance(agent["tools"], list)

    def test_tasks_have_required_fields(self, preset_data):
        for task in preset_data["tasks"]:
            assert "id" in task
            assert "agent_id" in task
            assert "prompt_template" in task
            assert "depends_on" in task

    def test_task_agents_exist(self, preset_data):
        agent_ids = {a["id"] for a in preset_data["agents"]}
        for task in preset_data["tasks"]:
            assert task["agent_id"] in agent_ids, \
                f"Task {task['id']} uses unknown agent {task['agent_id']}"

    def test_task_deps_exist(self, preset_data):
        task_ids = {t["id"] for t in preset_data["tasks"]}
        for task in preset_data["tasks"]:
            for dep in task.get("depends_on", []):
                assert dep in task_ids, \
                    f"Task {task['id']} depends on unknown task {dep}"

    def test_no_dag_cycles(self, preset_data):
        tasks = preset_data["tasks"]
        task_map = {t["id"]: t for t in tasks}

        visited = set()
        temp = set()

        def visit(tid):
            if tid in temp:
                return True
            if tid in visited:
                return False
            temp.add(tid)
            for dep in task_map[tid].get("depends_on", []):
                if visit(dep):
                    return True
            temp.remove(tid)
            visited.add(tid)
            return False

        for tid in task_map:
            assert not visit(tid), f"Cycle detected in DAG at task {tid}"

    def test_system_prompt_has_upstream_context(self, preset_data):
        for agent in preset_data["agents"]:
            if agent.get("max_iterations", 0) > 1:
                assert "{upstream_context}" in agent.get("system_prompt", ""), \
                    f"Agent {agent['id']} missing {{upstream_context}} placeholder"

    def test_input_from_refs_valid(self, preset_data):
        task_ids = {t["id"] for t in preset_data["tasks"]}
        for task in preset_data["tasks"]:
            for key, src in task.get("input_from", {}).items():
                assert src in task_ids, \
                    f"Task {task['id']} input_from key '{key}' refs unknown task {src}"


class TestScanPresets:
    @pytest.mark.parametrize("name", ["scan_trends", "scan_industries", "scan_stocks"])
    def test_scan_has_single_task(self, name):
        path = PRESETS_DIR / f"{name}.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert len(data["agents"]) == 1
        assert len(data["tasks"]) == 1
        assert len(data["tasks"][0]["depends_on"]) == 0

    @pytest.mark.parametrize("name", ["scan_trends", "scan_industries", "scan_stocks"])
    def test_scan_agent_has_manage_candidates(self, name):
        path = PRESETS_DIR / f"{name}.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "manage_candidates" in data["agents"][0]["tools"]


class TestResearchPresets:
    @pytest.mark.parametrize("name", ["research_trends", "research_industries"])
    def test_research_has_4_agents(self, name):
        path = PRESETS_DIR / f"{name}.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert len(data["agents"]) == 4
        assert len(data["tasks"]) == 4

    def test_research_stocks_has_9_agents(self):
        path = PRESETS_DIR / "research_stocks.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert len(data["agents"]) == 9
        assert len(data["tasks"]) == 9

    @pytest.mark.parametrize("name", ["research_trends", "research_industries", "research_stocks"])
    def test_final_decider_has_manage_proposals(self, name):
        path = PRESETS_DIR / f"{name}.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        # Find agents with manage_proposals in their tools
        deciders = [a for a in data["agents"] if "manage_proposals" in a.get("tools", [])]
        assert len(deciders) >= 1, f"No agent has manage_proposals tool in {name}"
        # Verify they have manage_candidates too
        for d in deciders:
            assert "manage_candidates" in d["tools"], \
                f"Decider {d['id']} has manage_proposals but missing manage_candidates"
