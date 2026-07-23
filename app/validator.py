# app/validator.py
import json
import random
import time
from bson import ObjectId

VALID_CATEGORIES = {
    'business_rules',
    'state_transitions',
    'constraints',
    'data_validation',
    'edge_cases',
    'exception_handling',
}

SYSTEM = (
    "You are a senior Business Analyst and QA architect reviewing requirements for a product feature. "
    "You ALWAYS respond with a single valid JSON array and nothing else."
)

def output_contract_header(version_str="null") -> str:
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT — STRICT JSON ONLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NO markdown. NO explanation. NO extra text outside the JSON array.
Your entire response must be one valid JSON array of objects.
The very first character of your response must be the opening bracket [
The very last character of your response must be the closing bracket ]

[
  {{
    "category": "business_rules",
    "question": "Question text here...",
    "options": [
      "Option A",
      "Option B",
      "Option C",
      "Option D"
    ],
    "correct_option_text": "Option B",
    "source_refs": [
      {{
        "docType": "prd",
        "section": "businessContext.prd.requirements",
        "evidence": "Short evidence text...",
        "versionNumber": {version_str}
      }}
    ]
  }}
]
"""

def build_validator_prompt(feature_id, unified_context, previous_questions=None) -> str:
    if previous_questions is None:
        previous_questions = []
    
    metadata = unified_context.get('metadata') or {}
    version_number = metadata.get('versionNumber')
    feature_name = metadata.get('featureName') or f"Feature {feature_id}"
    feature_description = unified_context.get('featureDescription') or ''
    
    avoid_block = ""
    if previous_questions:
        avoid_block = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUESTIONS TO AVOID — MANDATORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The user has already answered these questions in a previous attempt.
This is a RETAKE. You MUST generate completely fresh questions.

STRICT RULES:
- Do NOT test the same business rule, constraint, or scenario as any question below
- Do NOT rephrase or reword any of the questions below
- Each new question must cover a DIFFERENT decision point entirely
- If the PRD has limited rules, go DEEPER — test edge conditions, boundary values,
  conflict resolution, priority ordering, or implicit rules not yet covered

PREVIOUSLY ASKED QUESTIONS (avoid the underlying rule, not just the wording):
""" + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(previous_questions)) + """

If you find yourself writing a question about the same topic as any above —
STOP and pick a different rule from the PRD instead.
"""

    version_str = str(version_number) if version_number is not None else "null"

    return f"""
You are a senior Business Analyst and QA architect reviewing requirements for a product feature.

Your task is to generate 20 MCQ-based validator questions for the feature described below.
After reasoning, return 15 to 18 high-quality questions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OBJECTIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
These questions will be answered by a Product Owner or BA to:
- Resolve requirement ambiguity
- Validate business decision intent
- Identify gaps before QA begins

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUALITY BAR — READ CAREFULLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DIFFICULTY:
- At least 60% of questions must be MEDIUM or HIGH difficulty
- Easy questions are only allowed if they test a non-obvious business rule
- Do NOT ask questions whose answer is obvious common sense

LANGUAGE VARIETY — MANDATORY:
- Do NOT start more than 2 questions with "What should the system do if..."
- Vary question stems. Use these styles:
  * "Which business rule takes precedence when..."
  * "A user encounters X — what is the correct system behaviour?"
  * "The product team disagrees on Y — which approach aligns with the PRD?"
  * "Under what condition should the system allow..."
  * "If both X and Y occur simultaneously, what should happen?"
  * "What is the expected outcome when..."
  * "Which of the following is NOT a valid..."
  * "In the scenario where..., the correct response is..."
  * "How should the system differentiate between X and Y?"

TOPIC DIVERSITY — MANDATORY:
- Cover DIFFERENT business scenarios across all questions
- Do NOT ask multiple questions about the same topic (e.g., do not ask 2 questions about token expiry, or 2 about email validation)
- Each question must test a DISTINCT decision point or behaviour
- Spread questions across: user flows, error handling, data rules, role behaviour, state changes, boundary conditions, integration points

AVOID COMPLETELY:
- Questions with obviously wrong options (e.g., "Retry indefinitely", "Allow without verification")
- Reworded variants of the same rule across questions
- Generic textbook-style questions not grounded in the feature context
- Technical implementation details (no code, no HTTP status codes, no DB schemas)
- Questions that only a developer would understand

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CATEGORY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use ONLY these 6 categories:
- business_rules
- state_transitions
- constraints
- data_validation
- edge_cases
- exception_handling

Minimum 2 questions per category. Aim for 3 per category across 18 questions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUESTION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Each question must be specific to THIS feature and version context
- Each question must have EXACTLY 4 options
- Options must be plausible and mutually exclusive — no obviously wrong distractors
- Only one option is the most appropriate business decision
- No vague options like "depends", "maybe", "ask admin", "varies"
- Options should be roughly similar in length and tone
- Questions should be understandable by a non-technical Product Owner

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANSWER KEY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Each question MUST include "correct_option_text"
- "correct_option_text" must match EXACTLY one of the 4 options (word for word)
- Do NOT return correct index — backend shuffles options
- The correct answer should NOT always be the most verbose option

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOURCE REF RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Each question MUST include 1 to 3 source_refs.
Each source_ref must be:
{{
  "docType": "prd|hld|lld|figma",
  "section": "short section path from context",
  "evidence": "short evidence text, max 160 chars",
  "versionNumber": {version_str}
}}

Allowed sections:
- summaries.prd / summaries.hld / summaries.lld / summaries.figma
- businessContext.prd.requirements
- businessContext.hld.acceptanceCriteria
- businessContext.lld.requirements
- technicalContext.hld.endpoints
- technicalContext.lld.endpoints
- technicalContext.lld.technicalLines
- summaries.figma.sampleScreens / flows / figmaChanges

Rules:
- Do not invent evidence not present in the context
- Prefer cross-document evidence where available
- If context is limited to one doc, still vary the section references

{output_contract_header(version_str)}

{avoid_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURE CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Feature: {feature_name}
Goal: {feature_description}
Feature ID: {feature_id}
Version: {version_str}

{json.dumps(unified_context, indent=2)}
"""

def call_llm_json_with_repair(llm, system_prompt, user_prompt, max_tokens=7000) -> list:
    def parse_questions(raw):
        def extract_list_from_parsed(parsed):
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if "question" in k.lower() and isinstance(v, list):
                        return v
                for k, v in parsed.items():
                    if isinstance(v, list):
                        return v
                if all(isinstance(v, dict) and ("question" in v or "q" in v) for v in parsed.values() if isinstance(v, dict)):
                    return list(parsed.values())
            return None

        res = extract_list_from_parsed(raw)
        if res is not None:
            return res

        text = str(raw or "").strip()
        
        try:
            import json_repair
            parsed = json_repair.loads(text)
            res = extract_list_from_parsed(parsed)
            if res is not None:
                return res
        except Exception as repair_exc:
            print(f"[Validator] json-repair failed to parse raw text: {repair_exc}", flush=True)

        first_array, last_array = text.find("["), text.rfind("]")
        first_object, last_object = text.find("{"), text.rfind("}")
        
        candidates = []
        if first_array >= 0 and first_object >= 0:
            if first_array < first_object:
                if last_array > first_array:
                    candidates.append(text[first_array:last_array + 1])
                if last_object > first_object:
                    candidates.append(text[first_object:last_object + 1])
            else:
                if last_object > first_object:
                    candidates.append(text[first_object:last_object + 1])
                if last_array > first_array:
                    candidates.append(text[first_array:last_array + 1])
        else:
            if first_array >= 0 and last_array > first_array:
                candidates.append(text[first_array:last_array + 1])
            if first_object >= 0 and last_object > first_object:
                candidates.append(text[first_object:last_object + 1])
                
        candidates.append(text)
        
        last_err = None
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                res = extract_list_from_parsed(parsed)
                if res is not None:
                    return res
            except Exception as e:
                last_err = e
                try:
                    import json_repair
                    parsed = json_repair.loads(candidate)
                    res = extract_list_from_parsed(parsed)
                    if res is not None:
                        return res
                except Exception:
                    pass
                    
        raise ValueError(f"Validator response must contain an array of questions. Raw error: {last_err}")

    raw_text = ""
    try:
        raw_text = llm._raw_chat(system_prompt, user_prompt, 8192, 0.1, max_tokens)
        return parse_questions(raw_text)
    except Exception as e:
        print(f"[Self-Repair MCQ] JSON parse failed: {e}. Attempting self-repair...", flush=True)
        if not (raw_text or "").strip():
            # Only retry original chat if the first call failed completely (e.g. timeout/network error)
            try:
                raw_text = llm._raw_chat(system_prompt, user_prompt, 8192, 0.2, max_tokens)
            except Exception as retry_err:
                print(f"[Self-Repair MCQ] Retry chat failed: {retry_err}", flush=True)
                raise e
        try:
            repair_user = f"""The previous response failed JSON parsing with this error: {e}
Here is the invalid response that failed parsing:
\"\"\"
{raw_text}
\"\"\"
Repair this JSON array so it is valid and contains ONLY valid JSON objects. Output ONLY the repaired JSON array."""
            repaired_raw = llm._raw_chat("You are a JSON repair agent. Output ONLY a valid JSON array.", repair_user, 8192, 0.1, max_tokens)
            return parse_questions(repaired_raw)
        except Exception as repair_err:
            print(f"[Self-Repair MCQ] Repair failed: {repair_err}.", flush=True)
            raise e

def normalize_question_key(text: str) -> str:
    cleaned = String_clean = str(text or '').lower()
    cleaned = re_sub = "".join(c for c in cleaned if c.isalnum() or c.isspace())
    stopwords = {
        'what', 'which', 'when', 'how', 'should', 'would', 'must', 'is', 'are', 'was', 'were',
        'the', 'a', 'an', 'if', 'for', 'to', 'of', 'in', 'on', 'after', 'before'
    }
    tokens = [t for t in cleaned.split() if t not in stopwords]
    return " ".join(tokens)

def normalize_unique_options(options) -> list:
    out = []
    seen = set()
    arr = options if isinstance(options, list) else []
    for item in arr:
        val = str(item or '').strip()
        if not val:
            continue
        key = val.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(val)
        if len(out) == 4:
            break
    return out

def normalize_source_refs(source_refs, version_number) -> list:
    allowed_doc_types = {'prd', 'hld', 'lld', 'figma'}
    if not isinstance(source_refs, list) or not source_refs:
        return [{
            "docType": "prd",
            "section": "businessContext.prd.requirements",
            "evidence": "Derived from feature context",
            "versionNumber": version_number
        }]
    
    normalized = []
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue
        doc_type = str(ref.get("docType") or '').lower().strip()
        if doc_type not in allowed_doc_types:
            continue
        
        normalized.append({
            "docType": doc_type,
            "section": str(ref.get("section") or 'unknown').strip(),
            "evidence": str(ref.get("evidence") or '')[:160].strip(),
            "versionNumber": int(ref["versionNumber"]) if ref.get("versionNumber") is not None else version_number
        })
        if len(normalized) >= 3:
            break
            
    return normalized if normalized else [{
        "docType": "prd",
        "section": "businessContext.prd.requirements",
        "evidence": "Derived from feature context",
        "versionNumber": version_number
    }]

def shuffle_question_options(options, correct_option_text) -> tuple:
    # Match correct option
    target = correct_option_text.strip().lower()
    correct_idx = -1
    for idx, opt in enumerate(options):
        if opt.strip().lower() == target:
            correct_idx = idx
            break
            
    if correct_idx == -1:
        return options, 0
        
    items = [{"text": text, "is_correct": (i == correct_idx)} for i, text in enumerate(options)]
    random.shuffle(items)
    
    new_options = [x["text"] for x in items]
    new_correct_idx = next(i for i, x in enumerate(items) if x["is_correct"])
    return new_options, new_correct_idx

def normalize_and_filter_questions(parsed_questions, version_number) -> list:
    seen = set()
    final_questions = []
    
    for q in parsed_questions:
        if not isinstance(q, dict):
            continue
        category = str(q.get("category") or '').strip().lower().replace(" ", "_").replace("-", "_")
        question = str(q.get("question") or '').strip()
        options = normalize_unique_options(q.get("options"))
        correct_option_text = str(q.get("correct_option_text") or '').strip()
        
        if category not in VALID_CATEGORIES:
            continue
        if not question or len(question) < 25:
            continue
        if len(options) != 4:
            continue
        if not correct_option_text:
            continue
            
        key = normalize_question_key(question)
        if not key or key in seen:
            continue
            
        # Shuffle options and find index
        shuffled_opts, correct_idx = shuffle_question_options(options, correct_option_text)
        
        final_questions.append({
            "category": category,
            "question": question,
            "options": shuffled_opts,
            "correct_answer_index": correct_idx,
            "source_refs": normalize_source_refs(q.get("source_refs"), version_number)
        })
        seen.add(key)
        if len(final_questions) >= 20:
            break
            
    if len(final_questions) < 5:
        raise ValueError(f"Validator generated only {len(final_questions)} quality questions")
        
    return final_questions[:18]

def get_rating_meta(score: int) -> dict:
    if score >= 90:
        return {
            "rating": "Excellent",
            "description": "High clarity. Ready for QA validation."
        }
    if score >= 75:
        return {
            "rating": "Good",
            "description": "Strong requirement clarity with minor review needed."
        }
    if score >= 50:
        return {
            "rating": "Average",
            "description": "Moderate clarity. Review incorrect answers before QA validation."
        }
    return {
        "rating": "Poor",
        "description": "Low clarity. Revisit requirements before QA validation."
    }

def detect_weak_areas(questions, answers) -> list:
    category_map = {}
    for q in questions:
        cat = q.get("category")
        if cat not in category_map:
            category_map[cat] = {"answered": 0, "correct": 0}
            
    for ans in answers:
        q_id = str(ans.get("question_id"))
        q = next((x for x in questions if str(x.get("id")) == q_id), None)
        if not q:
            continue
        cat = q.get("category")
        correct_idx = q.get("correct_answer_index")
        selected_idx = ans.get("selected_index")
        
        category_map[cat]["answered"] += 1
        if correct_idx is not None and selected_idx is not None:
            if int(selected_idx) == int(correct_idx):
                category_map[cat]["correct"] += 1
                
    weak = []
    for cat, stats in category_map.items():
        if not stats["answered"]:
            continue
        accuracy = (stats["correct"] / stats["answered"]) * 100
        if accuracy < 60:
            weak.append(cat)
            
    return weak

def compute_validator_score(questions, answers) -> dict:
    total_questions = len(questions)
    answered_count = len(answers)
    completion_percent = round((answered_count / total_questions) * 100) if total_questions else 0
    
    correct_count = 0
    wrong_count = 0
    
    for ans in answers:
        q_id = str(ans.get("question_id"))
        q = next((x for x in questions if str(x.get("id")) == q_id), None)
        if not q:
            continue
        correct_idx = q.get("correct_answer_index")
        selected_idx = ans.get("selected_index")
        
        if correct_idx is not None and selected_idx is not None:
            if int(selected_idx) == int(correct_idx):
                correct_count += 1
            else:
                wrong_count += 1
                
    clarity_score = round((correct_count / answered_count) * 100) if answered_count else 0
    weak_areas = detect_weak_areas(questions, answers)
    rating_meta = get_rating_meta(clarity_score)
    
    return {
        "clarityScore": clarity_score,
        "correctCount": correct_count,
        "wrongCount": wrong_count,
        "answeredCount": answered_count,
        "totalQuestions": total_questions,
        "completionPercent": completion_percent,
        "rating": rating_meta["rating"],
        "description": rating_meta["description"],
        "weakAreas": weak_areas,
        "feedback": rating_meta["description"]
    }

def build_validated_output(questions, answers) -> dict:
    output = {}
    for q in questions:
        cat = q.get("category")
        if cat not in output:
            output[cat] = []
            
        q_id = str(q.get("id"))
        ans = next((x for x in answers if str(x.get("question_id")) == q_id), None)
        if not ans:
            continue
            
        options = q.get("options") or []
        selected_idx = ans.get("selected_index")
        correct_idx = q.get("correct_answer_index")
        
        selected_opt = options[selected_idx] if selected_idx is not None and 0 <= selected_idx < len(options) else None
        correct_opt = options[correct_idx] if correct_idx is not None and 0 <= correct_idx < len(options) else None
        
        output[cat].append({
            "question": q.get("question"),
            "selected_option": selected_opt,
            "correct_option": correct_opt,
            "is_correct": (selected_idx == correct_idx) if (selected_idx is not None and correct_idx is not None) else None,
            "confidence": ans.get("confidence"),
            "source_refs": q.get("source_refs") or []
        })
        
    return output

def build_question_result(q, ans) -> dict:
    options = q.get("options") or []
    correct_idx = q.get("correct_answer_index")
    selected_idx = ans.get("selected_index") if ans else None
    
    return {
        "questionId": str(q["id"]),
        "orderIndex": q.get("order_index", 0),
        "category": q.get("category"),
        "question": q.get("question"),
        "options": options,
        "correctAnswerIndex": correct_idx,
        "correctOption": options[correct_idx] if correct_idx is not None and 0 <= correct_idx < len(options) else None,
        "selectedIndex": selected_idx,
        "selectedOption": options[selected_idx] if selected_idx is not None and 0 <= selected_idx < len(options) else None,
        "isCorrect": (selected_idx == correct_idx) if (selected_idx is not None and correct_idx is not None) else None,
        "confidence": ans.get("confidence") if ans else None,
        "comment": ans.get("comment") if ans else None
    }

def get_existing_validator(store, feature_id, force_new=False) -> dict | None:
    feature = store.get_feature(feature_id)
    if not feature:
        raise ValueError("Feature not found")
    version_number = int(feature.get("version", 1))
    runs = store.list_validator_runs(feature_id)
    latest_run = next(
        (run for run in runs if int(run.get("version_number") or version_number) == version_number),
        None,
    )
    if not force_new and latest_run:
        questions = store.get_validator_questions(latest_run["id"])
        answers = store.get_validator_answers(latest_run["id"])
        if latest_run.get("status") == "completed":
            scoring = compute_validator_score(questions, answers)
            validated_output = build_validated_output(questions, answers)
            
            ans_map = {str(a["question_id"]): a for a in answers}
            question_results = [build_question_result(q, ans_map.get(str(q["id"]))) for q in questions]
            
            # Combine run metadata and score
            score_data = {
                **scoring,
                "validatedOutput": validated_output,
                "questionResults": question_results,
                "correctQuestions": [q for q in question_results if q["isCorrect"] is True],
                "incorrectQuestions": [q for q in question_results if q["isCorrect"] is False]
            }
            return {
                "run": latest_run,
                "versionNumber": version_number,
                "questions": questions,
                "answers": answers,
                "mode": "score",
                "score": score_data
            }
        if latest_run.get("status") in {"ready", "draft", "in_progress"}:
            return {
                "run": latest_run,
                "versionNumber": version_number,
                "questions": questions,
                "answers": answers,
                "mode": "resume"
            }
        if latest_run.get("status") == "generating":
            return {
                "run": latest_run,
                "versionNumber": version_number,
                "questions": questions,
                "answers": answers,
                "mode": "generating",
            }
    return None


def generate_validator_run(store, llm, feature_id, run_id=None, progress_fn=None) -> dict:
    feature = store.get_feature(feature_id)
    if not feature:
        raise ValueError("Feature not found")
    version_number = int(feature.get("version", 1))
    runs = store.list_validator_runs(feature_id)
    latest_previous = next((run for run in runs if run.get("id") != run_id), None)
    prev_questions = []
    if latest_previous:
        prev_questions = [
            q.get("question") for q in store.get_validator_questions(latest_previous["id"])
        ]
    if not run_id:
        run_id = store.create_validator_run(
            feature_id, is_retake=bool(prev_questions), version_number=version_number
        )

    def progress(stage, percent):
        suffix = f" ({percent}%)" if percent is not None else ""
        print(f"[Validator] {stage}{suffix}", flush=True)
        store.update_validator_run_status(
            run_id, "generating", stage=stage, progress=percent
        )
        if progress_fn:
            progress_fn(stage=stage, progress=percent)

    progress("Loading version-specific source documents", 15)
    unified_context = store.build_unified_context(feature_id, version_number)
    progress("Generating requirement-clarity questions", 40)
    prompt = build_validator_prompt(feature_id, unified_context, prev_questions)
    try:
        parsed = call_llm_json_with_repair(llm, SYSTEM, prompt)
        progress("Normalizing and validating MCQ quality", 75)
        questions = normalize_and_filter_questions(parsed, version_number)
        store.insert_validator_questions(run_id, questions)
        store.update_validator_run_status(
            run_id, "ready", stage="Ready for answers", progress=100
        )
        saved_questions = store.get_validator_questions(run_id)
        return {
            "run": store.get_validator_run(run_id),
            "versionNumber": version_number,
            "questions": saved_questions,
            "answers": [],
            "mode": "fresh"
        }
    except Exception as exc:
        store.update_validator_run_status(
            run_id, "failed", error=str(exc), stage="Generation failed", progress=100
        )
        raise


def get_or_create_validator(store, llm, feature_id, force_new=False) -> dict:
    existing = get_existing_validator(store, feature_id, force_new=force_new)
    if existing:
        return existing
    return generate_validator_run(store, llm, feature_id)

def submit_validator(store, run_id, answers, answered_by=None) -> dict:
    # answers is a list of dicts: [{"questionId": "...", "selectedIndex": 2, "confidence": 4, "comment": "..."}]
    questions = store.get_validator_questions(run_id)
    if not questions:
        raise ValueError(f"No questions found for run {run_id}")
        
    # Map input format to storage format
    storage_answers = []
    for ans in answers:
        storage_answers.append({
            "question_id": ans["questionId"],
            "selected_index": int(ans["selectedIndex"]),
            "confidence": int(ans.get("confidence") or 3),
            "comment": ans.get("comment"),
            "answered_by": answered_by
        })
        
    # Save answers
    store.save_validator_answers(run_id, storage_answers)
    
    # Re-retrieve to compute score
    all_answers = store.get_validator_answers(run_id)
    scoring = compute_validator_score(questions, all_answers)
    validated_output = build_validated_output(questions, all_answers)
    
    # Update validator run results
    store.update_validator_run_results(
        run_id=run_id,
        clarity_score=scoring["clarityScore"],
        weak_areas=scoring["weakAreas"],
        results=validated_output
    )
    
    ans_map = {str(a["question_id"]): a for a in all_answers}
    question_results = [build_question_result(q, ans_map.get(str(q["id"]))) for q in questions]
    
    score_data = {
        **scoring,
        "validatedOutput": validated_output,
        "questionResults": question_results,
        "correctQuestions": [q for q in question_results if q["isCorrect"] is True],
        "incorrectQuestions": [q for q in question_results if q["isCorrect"] is False]
    }
    
    return score_data
