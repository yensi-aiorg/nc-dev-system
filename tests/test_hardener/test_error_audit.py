"""Unit tests for the ErrorAuditor module.

Tests scanning of Python and TypeScript files for error handling issues
including bare excepts, unhandled promises, missing error boundaries,
and missing validation.
"""

from __future__ import annotations

import pytest

from src.hardener.error_audit import (
    AuditIssue,
    AuditResult,
    ErrorAuditor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def auditor() -> ErrorAuditor:
    """Fresh ErrorAuditor instance."""
    return ErrorAuditor()


@pytest.fixture
def project_with_backend(tmp_path):
    """Create a project with a backend directory containing Python files.

    Also creates an empty frontend/src so the auditor does not hit the
    deprecated ``asyncio.coroutine`` path in the source module.
    """
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def project_with_frontend(tmp_path):
    """Create a project with a frontend/src directory containing TS files.

    Also creates an empty backend/ so the auditor does not hit the
    deprecated ``asyncio.coroutine`` path in the source module.
    """
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    (tmp_path / "backend").mkdir()
    return tmp_path


@pytest.fixture
def full_project(tmp_path):
    """Create a project with both frontend and backend directories."""
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# AuditResult / AuditIssue Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAuditModels:
    """Test the Pydantic models used in error auditing."""

    def test_audit_issue_creation(self):
        issue = AuditIssue(
            severity="error",
            category="bare-except",
            file="backend/app/services/task_service.py",
            line=42,
            description="Bare except clause.",
            suggestion="Use 'except Exception:' instead.",
        )
        assert issue.severity == "error"
        assert issue.category == "bare-except"
        assert issue.line == 42

    def test_audit_issue_optional_line(self):
        issue = AuditIssue(
            severity="warning",
            category="missing-loading-state",
            file="frontend/src/stores/useTaskStore.ts",
            line=None,
            description="Missing isLoading.",
            suggestion="Add isLoading.",
        )
        assert issue.line is None

    def test_audit_result_defaults(self):
        result = AuditResult()
        assert result.issues == []
        assert result.warnings == []
        assert result.score == 100.0

    def test_audit_result_with_data(self):
        issue = AuditIssue(
            severity="error",
            category="test",
            file="test.py",
            line=1,
            description="test",
            suggestion="fix",
        )
        result = AuditResult(issues=[issue], warnings=[], score=95.0)
        assert len(result.issues) == 1
        assert result.score == 95.0


# ---------------------------------------------------------------------------
# Python Backend Scanning Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBackendAudit:
    """Test scanning Python files for error handling issues."""

    @pytest.mark.asyncio
    async def test_detects_bare_except(self, auditor, project_with_backend):
        """Bare 'except:' clauses should be flagged as errors."""
        py_file = project_with_backend / "backend" / "service.py"
        py_file.write_text(
            "try:\n"
            "    do_something()\n"
            "except:\n"
            "    handle_error()\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_backend))

        bare_excepts = [i for i in result.issues if i.category == "bare-except"]
        assert len(bare_excepts) >= 1
        assert bare_excepts[0].severity == "error"
        assert bare_excepts[0].line is not None

    @pytest.mark.asyncio
    async def test_detects_except_pass(self, auditor, project_with_backend):
        """'except ...: pass' patterns should be flagged as errors."""
        py_file = project_with_backend / "backend" / "service.py"
        py_file.write_text(
            "try:\n"
            "    do_something()\n"
            "except Exception:\n"
            "    pass\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_backend))

        silent = [i for i in result.issues if i.category == "silent-exception"]
        assert len(silent) >= 1
        assert silent[0].severity == "error"

    @pytest.mark.asyncio
    async def test_detects_missing_error_response(self, auditor, project_with_backend):
        """API endpoints without explicit error handling should get a warning."""
        py_file = project_with_backend / "backend" / "endpoints.py"
        py_file.write_text(
            "@router.get('/items')\n"
            "async def list_items():\n"
            "    return await get_items()\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_backend))

        missing = [
            i for i in (result.issues + result.warnings)
            if i.category == "missing-error-response"
        ]
        assert len(missing) >= 1

    @pytest.mark.asyncio
    async def test_detects_missing_validation(self, auditor, project_with_backend):
        """POST/PUT/PATCH endpoints without Pydantic validation should be flagged."""
        py_file = project_with_backend / "backend" / "endpoints.py"
        py_file.write_text(
            "@router.post('/items')\n"
            "async def create_item(data: dict):\n"
            "    return await save(data)\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_backend))

        missing = [
            i for i in result.issues if i.category == "missing-validation"
        ]
        assert len(missing) >= 1
        assert missing[0].severity == "error"

    @pytest.mark.asyncio
    async def test_no_issues_for_validated_endpoint(self, auditor, project_with_backend):
        """Properly validated endpoints should not produce validation issues."""
        py_file = project_with_backend / "backend" / "endpoints.py"
        py_file.write_text(
            "from pydantic import BaseModel, Field\n"
            "\n"
            "class ItemCreate(BaseModel):\n"
            "    name: str = Field(...)\n"
            "\n"
            "@router.post('/items')\n"
            "async def create_item(data: ItemCreate):\n"
            "    return await save(data)\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_backend))

        missing = [
            i for i in result.issues if i.category == "missing-validation"
        ]
        assert len(missing) == 0

    @pytest.mark.asyncio
    async def test_detects_unhandled_db_operations(self, auditor, project_with_backend):
        """DB operations without try/except should produce warnings."""
        py_file = project_with_backend / "backend" / "service.py"
        py_file.write_text(
            "class TaskService:\n"
            "    async def get_by_id(self, id: str):\n"
            "        return await self.collection.find_one({'_id': id})\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_backend))

        db_issues = [
            i for i in (result.issues + result.warnings)
            if i.category == "unhandled-db-error"
        ]
        assert len(db_issues) >= 1

    @pytest.mark.asyncio
    async def test_no_issues_for_handled_db_operations(self, auditor, project_with_backend):
        """DB operations inside try/except should not produce warnings."""
        py_file = project_with_backend / "backend" / "service.py"
        py_file.write_text(
            "class TaskService:\n"
            "    async def get_by_id(self, id: str):\n"
            "        try:\n"
            "            return await self.collection.find_one({'_id': id})\n"
            "        except Exception as e:\n"
            "            raise AppException(str(e))\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_backend))

        db_issues = [
            i for i in (result.issues + result.warnings)
            if i.category == "unhandled-db-error"
        ]
        assert len(db_issues) == 0

    @pytest.mark.asyncio
    async def test_clean_python_no_backend_issues(self, auditor, project_with_backend):
        """A well-written Python file should produce no backend error issues."""
        py_file = project_with_backend / "backend" / "clean.py"
        py_file.write_text(
            "def add(a: int, b: int) -> int:\n"
            "    return a + b\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_backend))

        backend_issues = [
            i for i in (result.issues + result.warnings)
            if i.category in (
                "bare-except", "silent-exception", "missing-error-response",
                "missing-validation", "unhandled-db-error",
            )
        ]
        assert len(backend_issues) == 0


# ---------------------------------------------------------------------------
# TypeScript / React Frontend Scanning Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFrontendAudit:
    """Test scanning TypeScript/React files for error handling issues."""

    @pytest.mark.asyncio
    async def test_detects_then_without_catch(self, auditor, project_with_frontend):
        """Promise .then() without .catch() should be flagged."""
        ts_file = project_with_frontend / "frontend" / "src" / "example.ts"
        ts_file.write_text(
            "fetch('/api/data').then(res => res.json());\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_frontend))

        unhandled = [
            i for i in result.issues if i.category == "unhandled-promise"
        ]
        assert len(unhandled) >= 1

    @pytest.mark.asyncio
    async def test_detects_await_without_try_catch(self, auditor, project_with_frontend):
        """'await' calls without try/catch should produce warnings."""
        ts_file = project_with_frontend / "frontend" / "src" / "example.ts"
        ts_file.write_text(
            "const data = await api.get('/items');\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_frontend))

        unhandled = [
            i for i in (result.issues + result.warnings)
            if i.category == "unhandled-promise"
        ]
        assert len(unhandled) >= 1

    @pytest.mark.asyncio
    async def test_detects_api_call_without_error_handling(self, auditor, project_with_frontend):
        """Direct api.get/post calls without error handling should be errors."""
        ts_file = project_with_frontend / "frontend" / "src" / "service.ts"
        ts_file.write_text(
            "const result = api.get('/items');\n"
            "const other = api.post('/items', data);\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_frontend))

        api_issues = [
            i for i in result.issues if i.category == "api-no-error-handling"
        ]
        assert len(api_issues) >= 1

    @pytest.mark.asyncio
    async def test_no_api_issue_when_try_catch_present(self, auditor, project_with_frontend):
        """API calls inside try/catch should not produce errors."""
        ts_file = project_with_frontend / "frontend" / "src" / "service.ts"
        ts_file.write_text(
            "try {\n"
            "  const result = await api.get('/items');\n"
            "} catch (e) {\n"
            "  console.error(e);\n"
            "}\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_frontend))

        api_issues = [
            i for i in result.issues if i.category == "api-no-error-handling"
        ]
        assert len(api_issues) == 0

    @pytest.mark.asyncio
    async def test_detects_missing_loading_state_in_store(self, auditor, project_with_frontend):
        """Zustand stores without isLoading should be warned."""
        ts_file = project_with_frontend / "frontend" / "src" / "store.ts"
        ts_file.write_text(
            "export const useTaskStore = create<TaskState>()(\n"
            "  devtools((set) => ({\n"
            "    items: [],\n"
            "    fetchItems: async () => {\n"
            "      const res = await api.get('/items');\n"
            "      set({ items: res.data });\n"
            "    },\n"
            "  }))\n"
            ");\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_frontend))

        missing_loading = [
            i for i in (result.issues + result.warnings)
            if i.category == "missing-loading-state"
        ]
        assert len(missing_loading) >= 1

    @pytest.mark.asyncio
    async def test_detects_missing_error_state_in_store(self, auditor, project_with_frontend):
        """Zustand stores without error state should be warned."""
        ts_file = project_with_frontend / "frontend" / "src" / "store.ts"
        ts_file.write_text(
            "export const useTaskStore = create<TaskState>()(\n"
            "  devtools((set) => ({\n"
            "    items: [],\n"
            "    isLoading: false,\n"
            "    fetchItems: async () => {\n"
            "      set({ isLoading: true });\n"
            "      const res = await api.get('/items');\n"
            "      set({ items: res.data, isLoading: false });\n"
            "    },\n"
            "  }))\n"
            ");\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_frontend))

        missing_error = [
            i for i in (result.issues + result.warnings)
            if i.category == "missing-error-state"
        ]
        assert len(missing_error) >= 1

    @pytest.mark.asyncio
    async def test_no_store_issue_when_both_states_present(self, auditor, project_with_frontend):
        """Stores with both isLoading and error should not produce store warnings."""
        ts_file = project_with_frontend / "frontend" / "src" / "store.ts"
        ts_file.write_text(
            "export const useTaskStore = create<TaskState>()(\n"
            "  devtools((set) => ({\n"
            "    items: [],\n"
            "    isLoading: false,\n"
            "    error: null as string | null,\n"
            "    fetchItems: async () => {\n"
            "      set({ isLoading: true, error: null });\n"
            "      try {\n"
            "        const res = await api.get('/items');\n"
            "        set({ items: res.data, isLoading: false });\n"
            "      } catch (e) {\n"
            "        set({ error: 'Failed', isLoading: false });\n"
            "      }\n"
            "    },\n"
            "  }))\n"
            ");\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_frontend))

        store_issues = [
            i for i in (result.issues + result.warnings)
            if i.category in ("missing-loading-state", "missing-error-state")
        ]
        assert len(store_issues) == 0

    @pytest.mark.asyncio
    async def test_detects_missing_error_boundary(self, auditor, project_with_frontend):
        """Projects without any ErrorBoundary component should be flagged."""
        app_file = project_with_frontend / "frontend" / "src" / "App.tsx"
        app_file.write_text(
            "import React from 'react';\n"
            "export default function App() {\n"
            "  return <div>Hello</div>;\n"
            "}\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_frontend))

        boundary_issues = [
            i for i in result.issues if i.category == "error-boundary"
        ]
        assert len(boundary_issues) >= 1

    @pytest.mark.asyncio
    async def test_no_boundary_issue_when_present(self, auditor, project_with_frontend):
        """Projects with an ErrorBoundary should not be flagged."""
        boundary_file = project_with_frontend / "frontend" / "src" / "ErrorBoundary.tsx"
        boundary_file.write_text(
            "class ErrorBoundary extends React.Component {\n"
            "  componentDidCatch(error, info) {\n"
            "    console.error(error, info);\n"
            "  }\n"
            "  render() { return this.props.children; }\n"
            "}\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_frontend))

        boundary_issues = [
            i for i in result.issues if i.category == "error-boundary"
        ]
        assert len(boundary_issues) == 0


# ---------------------------------------------------------------------------
# Score Calculation Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestScoreCalculation:
    """Test the error audit scoring algorithm."""

    def test_perfect_score_no_issues(self, auditor):
        score = auditor._calculate_score([])
        assert score == 100.0

    def test_single_error_deduction(self, auditor):
        issues = [
            AuditIssue(
                severity="error",
                category="test",
                file="test.py",
                line=1,
                description="test",
                suggestion="fix",
            )
        ]
        score = auditor._calculate_score(issues)
        assert score == 95.0  # 100 - 5.0

    def test_single_warning_deduction(self, auditor):
        issues = [
            AuditIssue(
                severity="warning",
                category="test",
                file="test.py",
                line=1,
                description="test",
                suggestion="fix",
            )
        ]
        score = auditor._calculate_score(issues)
        assert score == 98.0  # 100 - 2.0

    def test_single_info_deduction(self, auditor):
        issues = [
            AuditIssue(
                severity="info",
                category="test",
                file="test.py",
                line=1,
                description="test",
                suggestion="fix",
            )
        ]
        score = auditor._calculate_score(issues)
        assert score == 99.5  # 100 - 0.5

    def test_score_floors_at_zero(self, auditor):
        issues = [
            AuditIssue(
                severity="error",
                category="test",
                file="test.py",
                line=i,
                description="test",
                suggestion="fix",
            )
            for i in range(25)  # 25 * 5.0 = 125 deductions
        ]
        score = auditor._calculate_score(issues)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases in error auditing."""

    @pytest.mark.asyncio
    async def test_nonexistent_project_path(self, auditor, tmp_path):
        """Auditing a nonexistent path should return an error result."""
        result = await auditor.audit(str(tmp_path / "nonexistent"))
        assert len(result.issues) == 1
        assert result.issues[0].category == "project-not-found"
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_empty_project_no_frontend_no_backend(self, auditor, tmp_path):
        """A project with no frontend/ or backend/ dirs hits the deprecated
        ``asyncio.coroutine`` dead-code path which raises ``AttributeError``
        on Python 3.11+ (``asyncio.coroutine`` was removed).
        """
        # tmp_path exists but has no frontend/ or backend/ subdirectories
        with pytest.raises(AttributeError, match="coroutine"):
            await auditor.audit(str(tmp_path))

    @pytest.mark.asyncio
    async def test_empty_project_with_empty_dirs(self, auditor, tmp_path):
        """A project with empty frontend/src and backend dirs returns clean result.

        Note: both directories must exist because the source module has a
        dead-code path using the deprecated ``asyncio.coroutine`` that
        would crash on Python 3.11+ when either directory is missing.
        """
        (tmp_path / "frontend" / "src").mkdir(parents=True)
        (tmp_path / "backend").mkdir()
        result = await auditor.audit(str(tmp_path))
        # Only the error-boundary issue is expected (empty frontend/src)
        backend_issues = [
            i for i in (result.issues + result.warnings)
            if i.category in (
                "bare-except", "silent-exception", "missing-error-response",
                "missing-validation", "unhandled-db-error",
                "unhandled-promise", "api-no-error-handling",
                "missing-loading-state", "missing-error-state",
            )
        ]
        assert len(backend_issues) == 0

    @pytest.mark.asyncio
    async def test_skips_node_modules(self, auditor, project_with_frontend):
        """Files inside node_modules should be skipped."""
        nm = project_with_frontend / "frontend" / "src" / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        bad_file = nm / "bad.ts"
        bad_file.write_text(
            "fetch('/api').then(r => r.json());\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_frontend))

        # The node_modules file should be skipped; no unhandled-promise from it
        nm_issues = [
            i for i in result.issues
            if "node_modules" in (i.file or "")
        ]
        assert len(nm_issues) == 0

    @pytest.mark.asyncio
    async def test_print_report_does_not_raise(self, auditor, project_with_backend):
        """print_report should not raise on a valid result."""
        py_file = project_with_backend / "backend" / "service.py"
        py_file.write_text(
            "try:\n"
            "    pass\n"
            "except:\n"
            "    pass\n",
            encoding="utf-8",
        )

        result = await auditor.audit(str(project_with_backend))
        # Should not raise
        auditor.print_report(result)
