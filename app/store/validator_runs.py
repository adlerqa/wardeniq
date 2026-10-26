"""MCQ Validator run lifecycle: creation, status/result updates, and the
question/answer sets for each run.

Moved out of store.py (Phase 5 of docs/internal/REFACTOR_PLAN.md).
"""

import time

from bson import ObjectId


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # mypy-only: gives this mixin visibility into the collection attributes and
    # cross-mixin helpers that store/__init__.py's Store actually composes in at
    # runtime (BaseStore.__init__ sets self.projects/self.cases/etc; other mixins
    # add their own methods). At runtime this mixin still inherits only `object`
    # (see the `else` branch) — Store's own MRO (store/__init__.py) is what really
    # provides these at runtime, unchanged from before this TYPE_CHECKING addition.
    from store.base import BaseStore as _Base
else:
    _Base = object


class ValidatorRunsMixin(_Base):
    """No __init__: shares the collection attributes/state that store/base.py's
    BaseStore.__init__ sets up (composed last in store/__init__.py's Store MRO)."""

    def create_validator_run(self, feature_id, is_retake=False, version_number=None):
        now = time.time()
        # Find highest run_number for this feature_id
        highest = self.validator_runs.find_one({"feature_id": feature_id}, sort=[("run_number", -1)])
        run_number = (highest.get("run_number", 0) + 1) if highest else 1
        
        doc = {
            "feature_id": feature_id,
            "version_number": version_number,
            "run_number": run_number,
            "status": "generating", "stage": "Preparing validator context",
            "progress": 5, "error": None,
            "is_retake": is_retake,
            "clarity_score": None,
            "weak_areas": [],
            "results": None,
            "created_at": now,
            "updated_at": now
        }
        res = self.validator_runs.insert_one(doc)
        return str(res.inserted_id)

    def update_validator_run_status(self, run_id, status, error=None, stage=None, progress=None):
        fields = {"status": status, "error": error, "updated_at": time.time()}
        if stage is not None:
            fields["stage"] = stage
        if progress is not None:
            fields["progress"] = max(0, min(100, int(progress)))
        self.validator_runs.update_one(
            {"_id": ObjectId(run_id)},
            {"$set": fields}
        )

    def update_validator_run_results(self, run_id, clarity_score, weak_areas, results):
        self.validator_runs.update_one(
            {"_id": ObjectId(run_id)},
            {"$set": {
                "clarity_score": clarity_score,
                "weak_areas": weak_areas,
                "results": results,
                "status": "completed",
                "stage": "Completed",
                "progress": 100,
                "updated_at": time.time()
            }}
        )

    def get_validator_run(self, run_id):
        run = self.validator_runs.find_one({"_id": ObjectId(run_id)})
        if run:
            run["id"] = str(run.pop("_id"))
        return run

    def list_validator_runs(self, feature_id):
        out = []
        for r in self.validator_runs.find({"feature_id": feature_id}).sort("run_number", -1):
            r["id"] = str(r.pop("_id"))
            out.append(r)
        return out

    def insert_validator_questions(self, run_id, questions):
        # questions: list of NormalizedQuestion dicts
        docs = []
        for i, q in enumerate(questions):
            docs.append({
                "validator_run_id": run_id,
                "order_index": i,
                "category": q.get("category"),
                "question": q.get("question"),
                "options": q.get("options"),
                "correct_answer_index": q.get("correct_answer_index"),
                "source_refs": q.get("source_refs"),
                "created_at": time.time()
            })
        if docs:
            self.validator_questions.insert_many(docs)

    def get_validator_questions(self, run_id):
        out = []
        for q in self.validator_questions.find({"validator_run_id": run_id}).sort("order_index", 1):
            q["id"] = str(q.pop("_id"))
            out.append(q)
        return out

    def save_validator_answers(self, run_id, answers):
        # answers: list of PreparedAnswer dicts/inputs
        for a in answers:
            key = {"validator_run_id": run_id, "question_id": a["question_id"]}
            self.validator_answers.update_one(
                key,
                {"$set": {
                    "selected_index": a["selected_index"],
                    "confidence": a["confidence"],
                    "comment": a.get("comment"),
                    "answered_by": a.get("answered_by"),
                    "updated_at": time.time()
                }, "$setOnInsert": {"created_at": time.time()}},
                upsert=True
            )

    def get_validator_answers(self, run_id):
        out = []
        for a in self.validator_answers.find({"validator_run_id": run_id}):
            a["id"] = str(a.pop("_id"))
            out.append(a)
        return out
