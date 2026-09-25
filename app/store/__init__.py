"""Normalized QA store on Percona MongoDB + mongot.

Collections
  features         {name, project, source, text, summary, embedding}
  test_steps       {action, expected, embedding, usage_count}        ← atomic, reusable
  test_cases       {title, type, priority, preconditions, step_ids[], tags,
                    embedding, source_feature_id, similar_to[]}        ← references steps
  associations     {feature_id, test_case_id, origin, score}          ← many-to-many

Key properties
  * A test case references steps by id → editing a step propagates everywhere.
  * A test case can be associated to many features (reuse without duplication).
  * Dedup uses cosine similarity (Atlas score space = (1+cos)/2).

Split into store/ (Phase 5 of REFACTOR_PLAN.md, Option A: mixin composition) from a
single 3,889-line store.py. Each domain file below defines a mixin holding only its
own methods — no `__init__`, no collection setup — sharing the `self.db` / collection
attributes that `BaseStore.__init__` (store/base.py) sets up. `Store` composes every
mixin plus `BaseStore` (last, so its `__init__` wins the MRO); every existing call site
(`store.get_feature(x)`, `store.cases.find(...)`, etc.) resolves identically, unchanged,
because Python resolves `self.<name>` against the instance's actual class regardless of
which mixin's method body is running — this is what makes Option A a zero-call-site-edit
split. See REFACTOR_PLAN.md section 13 for the full rationale and the per-file method
accounting.

No duplicate method/property name exists across any mixin (see
`tests/test_no_duplicate_store_methods` — this guards against Python's MRO silently
picking one implementation and shadowing another, which would be undetectable at import
time).
"""
from store.audit import AuditMixin
from store.base import BaseStore
from store.code_coverage import CodeCoverageMixin
from store.coverage_snapshots import CoverageSnapshotsMixin
from store.dashboard import DashboardMixin
from store.documents import DocumentsMixin
from store.features import FeaturesMixin
from store.jobs import JobsMixin
from store.projects import ProjectsMixin
from store.repos_prs import ReposPrsMixin
from store.settings import SettingsMixin
from store.sheet_import import SheetImportMixin
from store.steps_test_cases import StepsTestCasesMixin
from store.test_cycles import TestCyclesMixin
from store.test_plan_runs import TestPlanRunsMixin
from store.usage import UsageMixin
from store.users_auth import UsersAuthMixin
from store.validator_runs import ValidatorRunsMixin


class Store(
    ProjectsMixin,
    FeaturesMixin,
    StepsTestCasesMixin,
    JobsMixin,
    UsageMixin,
    UsersAuthMixin,
    ReposPrsMixin,
    CodeCoverageMixin,
    ValidatorRunsMixin,
    TestPlanRunsMixin,
    TestCyclesMixin,
    DocumentsMixin,
    SettingsMixin,
    SheetImportMixin,
    AuditMixin,
    DashboardMixin,
    CoverageSnapshotsMixin,
    BaseStore,
):
    """Composes every domain mixin. `BaseStore` is last so its `__init__` (the only
    `__init__` in the MRO) wins — no other mixin defines one. See module docstring."""
