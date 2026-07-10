# app/test_plan.py
import json
import re
import time
from bson import ObjectId

# ─── String-level cleaners ────────────────────────────────────────────────────
def strip_urls(text: str) -> str:
    return re.sub(r'https?://[^\s"\',)\]>]+', '[link removed]', text)

def strip_html_entities(text: str) -> str:
    return re.sub(r'&(?:amp|lt|gt|quot|apos|#\d{1,6}|#x[\da-fA-F]{1,6});', '', text)

def strip_emoji(text: str) -> str:
    # Remove unicode emoji ranges
    return re.sub(
        '[\u2600-\u27BF\U0001F300-\U0001FAFF\U0001F000-\U0001F02F\U0001F0A0-\U0001F0FF\u2702-\u27B0\u24C2-\U0001F251✅⚠️❌🔴🟡🟢]',
        '', text
    )

def strip_markdown_tables(text: str) -> str:
    lines = text.split('\n')
    cleaned_lines = [line for line in lines if not re.match(r'^\s*\|[\s\-|:]+\|\s*$', line)]
    return '\n'.join(cleaned_lines)

def strip_qa_threads(text: str) -> str:
    s = re.sub(r'Question\s+Comment\s+From\s+PO[\s\S]{0,5000}?(?=\n{2,}|$)', '[PRD Q&A thread removed]', text, flags=re.IGNORECASE)
    s = re.sub(r'\b\d{1,2}\s+(?:Is|Are|What|When|How|Can|Should|Do|Does|Will)\s+[A-Z][^.!?\n]{20,}', '', s)
    return s

def strip_changelog_lines(text: str) -> str:
    lines = text.split('\n')
    cleaned = [line for line in lines if not re.match(r'^\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}', line.strip(), re.IGNORECASE)]
    return '\n'.join(cleaned)

def strip_leading_bullet_prefixes(text: str) -> str:
    lines = text.split('\n')
    cleaned = [re.sub(r'^\d+\.\s+', '', re.sub(r'^[\s•\-–·*]+', '', line)) for line in lines]
    return '\n'.join(cleaned)

def strip_markdown_note_markers(text: str) -> str:
    return re.sub(r'\*{1,2}[A-Za-z]+:\*{1,2}\s*', '', text)

def strip_editorial_placeholders(text: str) -> str:
    patterns = [
        r'^To\s+update\b.*',
        r'^Highlight\s+risks\b.*',
        r'^Risks\s*&\s*Mitigation\s*\(if\s+any\).*',
        r'^Risk\s+Likelihood\s+Impact\s+Mitigation.*',
        r'^TBC\s*$',
        r'^TBD\s*$',
        r'^Deferred\s+to\s+Phase\s+\d.*'
    ]
    s = text
    for p in patterns:
        s = re.sub(p, '', s, flags=re.IGNORECASE | re.MULTILINE)
    return s

def strip_vendor_pricing_blocks(text: str) -> str:
    s = re.sub(r'(?:Plan\s*=\s*(?:Growth|Pro|Enterprise)[^)]*\))', '[vendor pricing removed]', text, flags=re.IGNORECASE)
    s = re.sub(r'\d+\s+(?:USD|usd)\s*/\s*month[^.]*\.', '[pricing removed].', s, flags=re.IGNORECASE)
    s = re.sub(r'(?:MAU|mau)\s*=\s*[\$\d,\.]+[^\n]*', '[pricing removed]', s, flags=re.IGNORECASE)
    return s

def strip_wiki_paths(text: str) -> str:
    return re.sub(r'/wiki/spaces/[^\s"\',)>\]]+', '[wiki path removed]', text)

def strip_long_noisy_lines(text: str) -> str:
    lines = text.split('\n')
    out = []
    for line in lines:
        t = line.strip()
        if len(t) > 300:
            out.append('[long content removed]')
            continue
        if re.match(r'^\d+\s+(?:return|const|let|var|import|export|function|<[A-Z]|/|\{|\})', t, re.IGNORECASE):
            continue
        if re.search(r'\bappId\s*=\s*\{|\buserId\s*=\s*"|\bconversationId\s*=|<Chatbox', t, re.IGNORECASE):
            continue
        if re.search(r'\bDELETE\b.*/[a-z_]+/|\bService\s+Method\b|\bRequest\s+Schema\b|\bResponse\s+Schema\b', t, re.IGNORECASE):
            continue
        if re.match(r'^Over\s+\d+%\s+of\s+(?:respondents|users|farmers)', t, re.IGNORECASE):
            continue
        if re.match(r'^P[0-9]\s+\S', t, re.IGNORECASE):
            continue
        if re.match(r'^(?:Low|Medium|High|Critical)\s+(?:Low|Medium|High|Critical)\s+', t, re.IGNORECASE):
            continue
        out.append(line)
    return '\n'.join(out)

def clean_string(text: str) -> str:
    s = text
    s = strip_urls(s)
    s = strip_html_entities(s)
    s = strip_emoji(s)
    s = strip_markdown_tables(s)
    s = strip_changelog_lines(s)
    s = strip_leading_bullet_prefixes(s)
    s = strip_markdown_note_markers(s)
    s = strip_editorial_placeholders(s)
    s = strip_qa_threads(s)
    s = strip_vendor_pricing_blocks(s)
    s = strip_wiki_paths(s)
    s = strip_long_noisy_lines(s)
    # Collapse multiple whitespace/newlines
    s = re.sub(r'[ \t]{2,}', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s).strip()
    return s

def clean_value(value):
    if value is None:
        return value
    if isinstance(value, str):
        return clean_string(value)
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        return [clean_value(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_value(v) for k, v in value.items()}
    return value

def sanitize_context_for_prompt(ctx: dict) -> dict:
    return clean_value(ctx)

def compress_context(ctx: dict) -> dict:
    drop_keys = {'rawText', 'raw', 'fullText', 'prdRaw', 'hldRaw', 'lldRaw'}
    
    def compress(value, depth: int):
        if depth > 5:
            return '[truncated]'
        if value is None:
            return value
        if isinstance(value, str):
            return value[:800] + '…' if len(value) > 800 else value
        if isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, list):
            return [compress(item, depth + 1) for item in value[:20]]
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k in drop_keys:
                    continue
                out[k] = compress(v, depth + 1)
            return out
        return value
        
    return compress(ctx, 0)

# ─── Fallback & Prompt Builders ──────────────────────────────────────────────

def build_fallback_test_plan(project_id, feature_id, version_number, project_name, feature_name, feature_description, unified_context) -> dict:
    summaries = unified_context.get('summaries') or {}
    requirements = unified_context.get('requirements') or {}
    business_context = unified_context.get('business_context') or {}
    flags = unified_context.get('flags') or {}
    
    prd_reqs = requirements.get('prd') or []
    hld_reqs = requirements.get('hld') or []
    lld_reqs = requirements.get('lld') or []
    
    def get_req_text(r):
        if isinstance(r, str):
            return r
        if isinstance(r, dict):
            return r.get("text") or r.get("requirement") or r.get("description") or ""
        return str(r)
        
    prd_reqs_str = [get_req_text(r) for r in prd_reqs if get_req_text(r)][:14]
    hld_reqs_str = [get_req_text(r) for r in hld_reqs if get_req_text(r)][:10]
    lld_reqs_str = [get_req_text(r) for r in lld_reqs if get_req_text(r)][:10]
    
    all_reqs = prd_reqs_str + hld_reqs_str + lld_reqs_str
    in_scope_items = all_reqs[:12] if all_reqs else ["Execute standard workflows based on requirements."]
    
    risks = [
        'Risk: Unclear requirement interpretation may lead to missed validation coverage — Mitigation: Align with product owner before execution starts.',
        'Risk: Environment instability may delay end-to-end execution windows — Mitigation: Confirm QA environment readiness as part of entry criteria.',
        'Risk: Dependency readiness may affect API and workflow validation — Mitigation: Identify and track all external dependencies before execution.',
        'Risk: Late test data availability may impact negative and edge-case coverage — Mitigation: Prepare datasets in advance and flag gaps early.',
    ]
    
    scenario_seeds = prd_reqs_str + hld_reqs_str + lld_reqs_str
    if not scenario_seeds:
        scenario_seeds = [
            'Validate successful execution of the primary documented workflow.',
            'Validate invalid input handling and user-facing error responses.',
            'Validate boundary conditions and rejected-case behavior.',
            'Validate dependency failure handling and graceful recovery paths.',
        ]
    else:
        scenario_seeds = scenario_seeds[:15]
        
    scenario_rows = [{"Scenario": s, "Expected": "System behaves consistently with requirements."} for s in scenario_seeds]
    
    has_api = flags.get("hasApiEvidence", False) or bool(unified_context.get("technicalContext", {}).get("apiSpec"))
    has_ui = flags.get("hasUI", False)
    
    test_types_rows = [
        {
            "Testing Type": "Functional Testing",
            "Applicable": "Y",
            "Notes": "Validate primary business flows and acceptance behavior."
        },
        {
            "Testing Type": "API Testing",
            "Applicable": "Y" if has_api else "N",
            "Notes": "Validate REST API contracts and status responses." if has_api else "No direct API endpoints documented."
        },
        {
            "Testing Type": "UI Testing",
            "Applicable": "Y" if has_ui else "N",
            "Notes": "Validate visual states and interactive UI components." if has_ui else "No UI screen documentation provided."
        },
        {
            "Testing Type": "Negative Testing",
            "Applicable": "Y",
            "Notes": "Validate invalid inputs, limits, and error message prompts."
        },
        {
            "Testing Type": "Regression Testing",
            "Applicable": "Y",
            "Notes": "Confirm existing dependencies remain stable post-release."
        }
    ]
    
    coverage_rows = [
        { "Coverage Area": "Primary positive workflows", "Mandatory": "Y", "Covered": "Y" },
        { "Coverage Area": "Negative / validation scenarios", "Mandatory": "Y", "Covered": "Y" },
        { "Coverage Area": "Boundary and edge conditions", "Mandatory": "Y", "Covered": "Y" },
        { "Coverage Area": "API contract and response handling", "Mandatory": "Y", "Covered": "Y" if has_api else "N" },
        { "Coverage Area": "UI states and interaction behavior", "Mandatory": "Y", "Covered": "Y" if has_ui else "N" }
    ]
    
    return {
        "meta": {
            "projectId": str(project_id),
            "featureId": str(feature_id),
            "featureName": feature_name,
            "projectName": project_name,
            "featureVersionNumber": version_number,
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "COMPLETED",
            "source": "fallback"
        },
        "sections": [
            {
                "id": "project_details",
                "title": "Project Details",
                "type": "key_value",
                "content": [
                    { "key": "Project Name", "value": project_name },
                    { "key": "Feature Name", "value": feature_name },
                    { "key": "Version", "value": str(version_number) }
                ]
            },
            {
                "id": "objective",
                "title": "Objective",
                "type": "paragraph",
                "content": feature_description or f"Validate requirements for {feature_name}."
            },
            {
                "id": "test_summary",
                "title": "Test Summary",
                "type": "bullets",
                "content": ["Ensure overall release criteria match PRD specifications."]
            },
            {
                "id": "scope",
                "title": "Scope",
                "type": "grouped_list",
                "content": {
                    "in_scope": in_scope_items,
                    "out_of_scope": ["Infrastructure configurations", "Third-party platform maintenance"]
                }
            },
            {
                "id": "test_types",
                "title": "Test Types",
                "type": "table",
                "content": {
                    "columns": ["Testing Type", "Applicable", "Notes"],
                    "rows": test_types_rows
                }
            },
            {
                "id": "testing_coverage",
                "title": "Testing Coverage",
                "type": "table",
                "content": {
                    "columns": ["Coverage Area", "Mandatory", "Covered"],
                    "rows": coverage_rows
                }
            },
            {
                "id": "test_scenarios",
                "title": "Test Scenarios",
                "type": "table",
                "content": {
                    "columns": ["Scenario", "Expected"],
                    "rows": scenario_rows
                }
            },
            {
                "id": "risks_mitigation",
                "title": "Risks & Mitigation",
                "type": "bullets",
                "content": risks
            }
        ]
    }

def build_test_plan_prompt(feature_name, feature_description, project_name, version_number, unified_context, fallback_plan) -> str:
    compact_context = {
        "featureName": unified_context.get('featureName') or feature_name,
        "featureDescription": unified_context.get('featureDescription') or feature_description,
        "summaries": unified_context.get('summaries') or {},
        "requirements": unified_context.get('requirements') or {},
        "businessContext": unified_context.get('businessContext') or {},
        "technicalContext": unified_context.get('technicalContext') or {},
        "flags": unified_context.get('flags') or {},
    }
    
    sanitized = sanitize_context_for_prompt(compact_context)
    compressed = compress_context(sanitized)
    
    return f"""
You are generating a feature-specific QA Test Plan from stored product and technical documents.

STRICT RULES:
- Return ONLY valid JSON
- No markdown formatting (like *, **, or table syntax) inside strings
- No emojis or raw HTML artifacts (e.g., ✅, ⚠️, &amp;)
- No prose outside JSON
- Do not invent project-specific facts that are not grounded in the input
- Keep the plan feature-specific
- Keep section titles professional and concise
- Prefer practical QA language
- The response must be editable JSON
- Do not repeat the same sentence structure across sections
- Do not add unsupported pages, dashboards, auth methods, roles, or integrations that are not clearly grounded in the provided evidence
- When evidence is weak, use safe QA wording without inventing product facts

GROUNDING RULES:
- Use only information supported by the uploaded documents / unified context
- Prefer grounded detail over generic filler
- If exact implementation details are missing, write safe testing guidance tied to the feature context instead of hallucinating product behavior

SCOPE EXTRACTION RULES:
- When generating the "Scope" section, extract ONLY concise, testable, functional user requirements for the "in_scope" array.
- NEVER include raw URLs, vendor names, pricing figures, or Q&A conversation threads in the "in_scope" array.
- NEVER include lines that start with "http" or contain "sharepoint", "atlassian", "confluence", or similar tool paths.
- NEVER include PRD review questions, clarifications, or comment threads as scope items.
- NEVER include raw markdown table rows, evaluation criteria, or architecture decision records as scope items.
- NEVER include date-prefixed changelog entries such as "12 Feb 2026 1.2 Update the scope..." -- these are document revision notes, not requirements.
- NEVER include raw bullet-point lines copied verbatim starting with a bullet symbol or dash.
- NEVER include Wh-questions ("What T&C updates are required...?") -- these are open clarifications, not requirements.
- NEVER include business vision or marketing narrative such as "Seller Chat is not only a support feature but a growth and scale initiative..." -- not testable.
- NEVER include lines containing "GMV", "stickiness", "scale initiative", "long term stickiness", or similar marketing language.
- NEVER copy numbered acceptance-criteria lines verbatim (e.g. "1. As a reporter who has blocked a seller...") -- rephrase these into clean "[Actor] can/should [action]" format.
- NEVER include raw code, JSX, or API specification text as scope items (e.g. lines starting with "return (", "<Chatbox", "DELETE /", "4 return ( 5 < Chatbox...").
- NEVER include survey or market research statistics as scope items (e.g. "Over 80% of respondents...").
- NEVER include priority/severity labels as scope items (e.g. "P1 Block user from using chat", "Medium High Phase 1...").
- NEVER include partial sentences or app-name-only fragments (e.g. "Yaraconnect app. This allows...").
- DO NOT leave "out_of_scope" empty if the context mentions features that are "deferred", "Phase 2", "future expansion", or explicitly excluded.
- Each in_scope item must follow the format: "[Actor] can/should [action] [context]"
- Each item must describe a specific user action, system behavior, or acceptance condition in plain English.
- Target 6 to 12 in_scope items. Do not pad with noise.

SECTION DEPTH RULES:
- "objective" should be a concise but meaningful paragraph
- "test_summary" must contain 4 to 6 concise bullets
- "test_strategy" must contain 8 to 12 practical bullets
- "testing_coverage" should contain 6 to 10 meaningful rows
- "test_scenarios" should contain 10 to 15 meaningful rows whenever enough evidence exists
- "environment_details", "test_data", "entry_criteria", "exit_criteria", "roles_responsibilities",
  "defect_management", "risks_mitigation", "dependencies", "deliverables", "metrics", and "sign_off"
  should contain 5 to 8 useful bullets whenever possible
- Make bullets specific, actionable, and readable
- Do not keep sections artificially short when more grounded detail is available

TEST SCENARIO RULES:
- Each "Scenario" cell must describe a plain-English user action and context — e.g. "Farmer initiates a chat with a seller from the product page"
- Each "Expected" cell must describe the specific system outcome — e.g. "Chat window opens and displays seller name and online status"
- NEVER use raw URLs, PRD question text, vendor pricing rows, or markdown table syntax as scenario descriptions
- NEVER use generic fillers like "System should behave consistently with the documented requirement"
- Each row must be independently meaningful and testable

TEST TYPE RULES:
- "test_types" MUST include these exact separate testing types:
  1. Functional Testing
  2. API Testing
  3. UI Testing
  4. Negative Testing
  5. Regression Testing
  6. Performance Testing
  7. Security Testing
- For each row:
  - "Applicable" must be "Y" or "N"
  - "Notes" should explain what will be validated and why it matters

RISKS AND MITIGATION RULES:
- Each bullet must name a specific, concrete QA or delivery risk and its mitigation strategy.
- Format every bullet as: "Risk: [description] -- Mitigation: [action]"
- Write 5 to 8 bullets, all in the Risk/Mitigation format.

TARGET FEATURE:
- Project Name: {project_name or 'Unknown Project'}
- Feature Name: {feature_name or 'Unknown Feature'}
- Feature Description: {feature_description or ''}
- Version Number: {version_number}

RETURN JSON IN THIS SHAPE:
{{
  "meta": {{
    "projectId": "",
    "featureId": "",
    "featureName": "",
    "projectName": "",
    "featureVersionNumber": 0,
    "generatedAt": "",
    "updatedAt": "",
    "status": "COMPLETED",
    "source": "ai_generated"
  }},
  "sections": [
    {{
      "id": "project_details",
      "title": "Project Details",
      "type": "key_value",
      "content": [
        {{ "key": "Project Name", "value": "" }},
        {{ "key": "Feature Name", "value": "" }},
        {{ "key": "Version", "value": "" }}
      ]
    }},
    {{
      "id": "objective",
      "title": "Objective",
      "type": "paragraph",
      "content": ""
    }},
    {{
      "id": "test_summary",
      "title": "Test Summary",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "scope",
      "title": "Scope",
      "type": "grouped_list",
      "content": {{
        "in_scope": [],
        "out_of_scope": []
      }}
    }},
    {{
      "id": "test_strategy",
      "title": "Test Strategy",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "test_types",
      "title": "Test Types",
      "type": "table",
      "content": {{
        "columns": ["Testing Type", "Applicable", "Notes"],
        "rows": []
      }}
    }},
    {{
      "id": "testing_coverage",
      "title": "Testing Coverage",
      "type": "table",
      "content": {{
        "columns": ["Coverage Area", "Mandatory", "Covered"],
        "rows": []
      }}
    }},
    {{
      "id": "environment_details",
      "title": "Environment Details",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "test_data",
      "title": "Test Data",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "entry_criteria",
      "title": "Entry Criteria",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "exit_criteria",
      "title": "Exit Criteria",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "roles_responsibilities",
      "title": "Roles & Responsibilities",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "test_scenarios",
      "title": "Test Scenarios",
      "type": "table",
      "content": {{
        "columns": ["Scenario", "Expected"],
        "rows": []
      }}
    }},
    {{
      "id": "defect_management",
      "title": "Defect Management",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "risks_mitigation",
      "title": "Risks & Mitigation",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "dependencies",
      "title": "Dependencies",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "deliverables",
      "title": "Deliverables",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "metrics",
      "title": "Metrics",
      "type": "bullets",
      "content": []
    }},
    {{
      "id": "sign_off",
      "title": "Sign-Off",
      "type": "bullets",
      "content": []
    }}
  ]
}}

STRUCTURAL FORMATTING REFERENCE ONLY (DO NOT USE FOR CONTENT):
{json.dumps(fallback_plan, indent=2)}

GROUNDING CONTEXT:
{json.dumps(compressed, indent=2)}
"""

def generate_test_plan_job(store, llm, run_id, feature_id):
    try:
        feature = store.get_feature(feature_id)
        if not feature:
            raise ValueError("Feature not found")
            
        version_number = int(feature.get("version", 1))
        project_id = feature.get("project_id")
        project = store.projects.find_one({"_id": ObjectId(project_id)})
        project_name = project.get("name", "") if project else "WardenIQ Project"
        
        # Build unified context
        unified_context = store.build_unified_context(feature_id, version_number)
        
        fallback_plan = build_fallback_test_plan(
            project_id=project_id,
            feature_id=feature_id,
            version_number=version_number,
            project_name=project_name,
            feature_name=feature.get("name"),
            feature_description=feature.get("summary") or "",
            unified_context=unified_context
        )
        
        prompt = build_test_plan_prompt(
            feature_name=feature.get("name"),
            feature_description=feature.get("summary") or "",
            project_name=project_name,
            version_number=version_number,
            unified_context=unified_context,
            fallback_plan=fallback_plan
        )
        
        system_prompt = "You are generating a feature-specific QA Test Plan. You ALWAYS respond with a single valid JSON object."
        
        from testgen.service import call_llm_json_with_repair
        try:
            plan_json = call_llm_json_with_repair(llm, system_prompt, prompt, max_tokens=8000)
        except Exception as e:
            print(f"[TestPlan] LLM call failed, using fallback: {e}", flush=True)
            plan_json = fallback_plan
            plan_json["meta"]["source"] = "fallback"
            
        if not isinstance(plan_json, dict):
            plan_json = {}
        if "meta" not in plan_json:
            plan_json["meta"] = fallback_plan["meta"]
        else:
            # Overwrite crucial meta fields
            plan_json["meta"]["projectId"] = str(project_id)
            plan_json["meta"]["featureId"] = str(feature_id)
            plan_json["meta"]["projectName"] = project_name
            plan_json["meta"]["featureName"] = feature.get("name")
            plan_json["meta"]["featureVersionNumber"] = version_number
            plan_json["meta"]["generatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            plan_json["meta"]["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            plan_json["meta"]["status"] = "COMPLETED"
            plan_json["meta"]["source"] = plan_json["meta"].get("source") or "ai_generated"
            
        if "sections" not in plan_json:
            plan_json["sections"] = fallback_plan["sections"]
            
        store.update_test_plan_run(run_id, status="COMPLETED", content=plan_json)
    except Exception as e:
        print(f"[TestPlan] Job error: {e}", flush=True)
        store.update_test_plan_run(run_id, status="FAILED", error=str(e))

# ─── PDF / CSV Exporters ─────────────────────────────────────────────────────

def pdf_escape(value: str) -> str:
    return str(value or '').replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

def wrap_line(text: str, max_len=95) -> list:
    words = str(text or '').split()
    if not words:
        return ['']
    lines = []
    current = ''
    for w in words:
        next_line = f"{current} {w}" if current else w
        if len(next_line) > max_len:
            if current:
                lines.append(current)
            current = w
        else:
            current = next_line
    if current:
        lines.append(current)
    return lines

def flatten_unknown(value, depth=0) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return wrap_line(value)
    if isinstance(value, (int, float, bool)):
        return [str(value)]
        
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str):
                out.extend(wrap_line(f"- {item}"))
            else:
                out.extend(flatten_unknown(item, depth + 1))
        return out
        
    if isinstance(value, dict):
        out = []
        if 'columns' in value and 'rows' in value:
            cols = [str(x) for x in value.get("columns") or []]
            out.extend(wrap_line(" | ".join(cols)))
            for row in value.get("rows") or []:
                if isinstance(row, list):
                    out.extend(wrap_line(" | ".join(str(v) for v in row)))
                elif isinstance(row, dict):
                    vals = [str(row.get(c) or '') for c in cols]
                    out.extend(wrap_line(" | ".join(vals)))
            return out
            
        if 'in_scope' in value or 'out_of_scope' in value:
            in_s = value.get("in_scope") or []
            out_s = value.get("out_of_scope") or []
            if in_s:
                out.append("In Scope:")
                for item in in_s:
                    out.extend(wrap_line(f"- {item}"))
            if out_s:
                out.append("Out of Scope:")
                for item in out_s:
                    out.extend(wrap_line(f"- {item}"))
            return out
            
        for k, v in value.items():
            if isinstance(v, (list, dict)):
                out.append(f"{k}:")
                out.extend(flatten_unknown(v, depth + 1))
            else:
                out.extend(wrap_line(f"{k}: {v}"))
        return out
        
    return [str(value)]

def section_to_lines(section: dict) -> list:
    lines = []
    lines.append(section.get("title") or "Untitled Section")
    lines.extend(flatten_unknown(section.get("content")))
    lines.append('')
    return lines

def document_to_lines(plan: dict) -> list:
    lines = []
    meta = plan.get("meta") or {}
    lines.append("Test Plan")
    lines.append(f"Project: {meta.get('projectName') or ''}")
    lines.append(f"Feature: {meta.get('featureName') or ''}")
    lines.append(f"Version: {meta.get('featureVersionNumber') or ''}")
    lines.append(f"Status: {meta.get('status') or ''}")
    lines.append('')
    for sec in plan.get("sections") or []:
        lines.extend(section_to_lines(sec))
    return lines

def build_simple_pdf(lines: list) -> bytes:
    # Basic PDF Generator yielding a text layout
    page_width = 595
    page_height = 842
    margin_left = 40
    margin_top = 40
    line_height = 14
    usable_height = page_height - margin_top - 40
    lines_per_page = max(1, usable_height // line_height)
    
    pages = []
    for i in range(0, len(lines), lines_per_page):
        pages.append(lines[i:i+lines_per_page])
        
    objects = []
    def add_object(body: str) -> int:
        objects.append(body)
        return len(objects)
        
    catalog_id = add_object('<< /Type /Catalog /Pages 2 0 R >>')
    pages_id = add_object('<< /Type /Pages /Kids [] /Count 0 >>')
    font_id = add_object('<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>')
    
    page_obj_ids = []
    for page_lines in pages:
        content_parts = ['BT', '/F1 11 Tf', f"{margin_left} {page_height - margin_top} Td"]
        for idx, line in enumerate(page_lines):
            text = pdf_escape(line)
            if idx == 0:
                content_parts.append(f"({text}) Tj")
            else:
                content_parts.append(f"0 -{line_height} Td")
                content_parts.append(f"({text}) Tj")
        content_parts.append('ET')
        
        content_stream = '\n'.join(content_parts)
        stream_len = len(content_stream.encode('utf-8'))
        content_id = add_object(f"<< /Length {stream_len} >>\nstream\n{content_stream}\nendstream")
        page_id = add_object(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {page_width} {page_height}] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>")
        page_obj_ids.append(page_id)
        
    kids_str = " ".join(f"{id} 0 R" for id in page_obj_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_obj_ids)} >>"
    
    parts = ['%PDF-1.4']
    offsets = [0]
    for i, obj in enumerate(objects):
        current_pdf = '\n'.join(parts)
        offsets.append(len(current_pdf.encode('utf-8')))
        parts.append(f"{i + 1} 0 obj\n{obj}\nendobj")
        
    xref_offset = len(('\n'.join(parts) + '\n').encode('utf-8'))
    parts.append('xref')
    parts.append(f"0 {len(objects) + 1}")
    parts.append('0000000000 65535 f ')
    for off in offsets[1:]:
        parts.append(f"{str(off).zfill(10)} 00000 n ")
        
    parts.append('trailer')
    parts.append(f"<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>")
    parts.append('startxref')
    parts.append(str(xref_offset))
    parts.append('%%EOF')
    
    return '\n'.join(parts).encode('utf-8')

def build_test_plan_pdf(plan: dict) -> bytes:
    lines = document_to_lines(plan)
    return build_simple_pdf(lines)

# ─── CSV flattening logic ────────────────────────────────────────────────────

def escape_csv(val) -> str:
    s = "" if val is None else str(val)
    return f'"{s.replace(chr(34), chr(34)+chr(34))}"'

def list_items(val) -> list:
    if not isinstance(val, list):
        return []
    out = []
    for item in val:
        if isinstance(item, (str, int, float, bool)):
            out.append(str(item).strip())
        elif isinstance(item, dict):
            # check common keys
            for k in ["text", "value", "label", "title", "key", "name"]:
                if item.get(k) is not None:
                    out.append(str(item[k]).strip())
                    break
    return [x for x in out if x]

def flatten_section(sec: dict) -> list:
    title = sec.get("title") or ""
    sec_id = sec.get("id") or ""
    sec_type = sec.get("type") or ""
    content = sec.get("content")
    
    rows = []
    def make_row(subsection="", details="", applicable="", notes="", mandatory="", covered="", expected=""):
        return {
            "Section": title,
            "Subsection": subsection,
            "Details": details,
            "Applicable": applicable,
            "Notes": notes,
            "Mandatory": mandatory,
            "Covered": covered,
            "Expected Result": expected
        }
        
    if sec_type == 'paragraph':
        rows.append(make_row(details=str(content or '').strip()))
    elif sec_type in ['bullets', 'checklist']:
        items = list_items(content)
        if not items:
            rows.append(make_row())
        for item in items:
            rows.append(make_row(details=item))
    elif sec_type == 'key_value':
        items = content if isinstance(content, list) else []
        if not items:
            rows.append(make_row())
        for item in items:
            if isinstance(item, dict):
                rows.append(make_row(subsection=str(item.get("key") or ''), details=str(item.get("value") or '')))
    elif sec_type == 'grouped_list':
        obj = content if isinstance(content, dict) else {}
        in_s = list_items(obj.get("in_scope"))
        out_s = list_items(obj.get("out_of_scope"))
        for item in in_s:
            rows.append(make_row(subsection="In Scope", details=item))
        for item in out_s:
            rows.append(make_row(subsection="Out of Scope", details=item))
        if not in_s and not out_s:
            rows.append(make_row())
    elif sec_type == 'table':
        obj = content if isinstance(content, dict) else {}
        tbl_rows = obj.get("rows") or []
        if not tbl_rows:
            rows.append(make_row())
        for r in tbl_rows:
            if isinstance(r, dict):
                if sec_id == 'test_types':
                    rows.append(make_row(subsection=str(r.get("Testing Type") or ''), applicable=str(r.get("Applicable") or ''), notes=str(r.get("Notes") or '')))
                elif sec_id == 'testing_coverage':
                    rows.append(make_row(subsection=str(r.get("Coverage Area") or ''), mandatory=str(r.get("Mandatory") or ''), covered=str(r.get("Covered") or '')))
                elif sec_id == 'test_scenarios':
                    rows.append(make_row(details=str(r.get("Scenario") or ''), expected=str(r.get("Expected") or '')))
                else:
                    # generic columns
                    cols = obj.get("columns") or []
                    details = " | ".join(f"{col}: {r.get(col)}" for col in cols if r.get(col) is not None)
                    rows.append(make_row(details=details))
    else:
        rows.append(make_row(details=str(content or '').strip()))
        
    return rows

def build_test_plan_csv(plan: dict) -> str:
    header = [
        'Section',
        'Subsection',
        'Details',
        'Applicable',
        'Notes',
        'Mandatory',
        'Covered',
        'Expected Result',
    ]
    
    rows = []
    for sec in plan.get("sections") or []:
        rows.extend(flatten_section(sec))
        
    csv_lines = [",".join(header)]
    for r in rows:
        line_vals = [
            r["Section"], r["Subsection"], r["Details"], r["Applicable"],
            r["Notes"], r["Mandatory"], r["Covered"], r["Expected Result"]
        ]
        csv_lines.append(",".join(escape_csv(v) for v in line_vals))
        
    return "\n".join(csv_lines)
