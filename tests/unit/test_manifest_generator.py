"""Tests for ManifestGenerator — TC issue conversion to fix manifests."""

from ncdev.quality_gate.manifest import ManifestGenerator


def _make_tc_issue(
    id_: str = "tc_1",
    title: str = "Bug",
    severity: str = "medium",
    type_: str = "functionality",
    url: str = "/page",
    action: str = "Do something",
    expected: str = "Works",
    actual: str = "Broken",
    selector: str = ".el",
) -> dict:
    return {
        "id": id_,
        "title": title,
        "severity": severity,
        "type": type_,
        "status": "open",
        "context": {
            "url": url,
            "action_attempted": action,
            "expected": expected,
            "actual": actual,
            "element_selector": selector,
        },
    }


SCORES = {"core_flow": 40, "resilience": 60, "polish": 80}


class TestManifestGeneratorGenerate:
    """Tests for the generate method."""

    def test_converts_tc_issues_to_fix_manifest_with_correct_count(self):
        gen = ManifestGenerator()
        issues = [
            _make_tc_issue(id_="tc_1", severity="high"),
            _make_tc_issue(id_="tc_2", severity="low"),
            _make_tc_issue(id_="tc_3", severity="critical"),
        ]
        manifest = gen.generate("run-1", "/app", issues, SCORES)

        assert len(manifest.issues) == 3
        assert manifest.run_id == "run-1"
        assert manifest.target_path == "/app"
        assert manifest.scores.core_flow == 40
        assert manifest.scores.resilience == 60
        assert manifest.scores.polish == 80

    def test_issues_sorted_by_priority_p0_first(self):
        gen = ManifestGenerator()
        issues = [
            _make_tc_issue(id_="low", severity="low"),
            _make_tc_issue(id_="crit", severity="critical"),
            _make_tc_issue(id_="med", severity="medium"),
            _make_tc_issue(id_="high", severity="high"),
        ]
        manifest = gen.generate("run-2", "/app", issues, SCORES)

        priorities = [i.priority for i in manifest.issues]
        assert priorities == ["P0", "P1", "P2", "P3"]
        assert manifest.issues[0].id == "crit"
        assert manifest.issues[-1].id == "low"

    def test_persona_mapping(self):
        gen = ManifestGenerator()
        type_persona = {
            "functionality": "user",
            "visual": "inspector",
            "performance": "inspector",
            "network": "user",
            "console": "destroyer",
            "accessibility": "inspector",
            "ux": "inspector",
            "security": "destroyer",
        }
        for type_, expected_persona in type_persona.items():
            issues = [_make_tc_issue(type_=type_)]
            manifest = gen.generate("run-p", "/app", issues, SCORES)
            assert manifest.issues[0].persona == expected_persona, (
                f"type={type_} expected persona={expected_persona}"
            )

    def test_flow_and_reproduction_built_from_context(self):
        gen = ManifestGenerator()
        issues = [
            _make_tc_issue(
                url="/projects",
                action="View project list",
                expected="List renders",
                actual="Empty div",
            )
        ]
        manifest = gen.generate("run-3", "/app", issues, SCORES)
        issue = manifest.issues[0]

        assert issue.flow == "/projects → View project list"
        assert issue.expected == "List renders"
        assert issue.actual == "Empty div"
        assert "Navigate to /projects" in issue.reproduction[0]
        assert "View project list" in issue.reproduction[1]


class TestSeverityToPriority:
    """Tests for _severity_to_priority mapping."""

    def test_all_four_levels(self):
        gen = ManifestGenerator()
        assert gen._severity_to_priority("critical") == "P0"
        assert gen._severity_to_priority("high") == "P1"
        assert gen._severity_to_priority("medium") == "P2"
        assert gen._severity_to_priority("low") == "P3"

    def test_unknown_severity_defaults_to_p3(self):
        gen = ManifestGenerator()
        assert gen._severity_to_priority("unknown") == "P3"


class TestGroupRelated:
    """Tests for _group_related grouping by URL."""

    def test_groups_issues_by_url(self):
        gen = ManifestGenerator()
        issues = [
            _make_tc_issue(id_="a1", url="/projects"),
            _make_tc_issue(id_="a2", url="/projects"),
            _make_tc_issue(id_="b1", url="/settings"),
            _make_tc_issue(id_="c1", url="/dashboard"),
        ]
        groups = gen._group_related(issues)

        assert len(groups) == 3
        # Find the /projects group — it should have 2 issues.
        projects_group = [g for g in groups if g[0]["context"]["url"] == "/projects"]
        assert len(projects_group) == 1
        assert len(projects_group[0]) == 2

    def test_single_issue_per_url(self):
        gen = ManifestGenerator()
        issues = [
            _make_tc_issue(id_="x", url="/a"),
            _make_tc_issue(id_="y", url="/b"),
        ]
        groups = gen._group_related(issues)
        assert len(groups) == 2
        assert all(len(g) == 1 for g in groups)
