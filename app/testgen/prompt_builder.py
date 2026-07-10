# app/testgen/prompt_builder.py
import json
import re
import math

INFRASTRUCTURE_DENY_LIST = {
    'postgresql', 'postgres', 'mysql', 'mongodb', 'sqlite', 'redis',
    'elasticsearch', 'aws s3', 's3', 'gcs', 'azure blob', 'cdn',
    'socket.io', 'websocket', 'kafka', 'rabbitmq', 'sqs', 'sns',
    'express', 'nestjs', 'next.js', 'fastify', 'react native', 'flutter',
    'prisma', 'typeorm', 'sequelize', 'mongoose',
    'node.js', 'nodejs', 'python', 'java', 'golang',
    'jwt', 'oauth', 'passport', 'cloudflare', 'firebase',
    'fcm', 'mapbox', 'foursquare', 'twilio', 'msg91'
}       

TEST_TYPES = ["functional", "e2e", "api", "nfr"]

def output_contract_header(task_name: str) -> str:
    return "\n".join([
        f"TASK: {task_name}",
        "",
        "OUTPUT FORMAT — read this before doing anything else:",
        "Your entire response must be one valid JSON object.",
        "The very first character of your response must be the opening brace {",
        "The very last character of your response must be the closing brace }",
        "Do not write any text, explanation, or comment before or after the JSON.",
        "Do not wrap the JSON in markdown code fences or backticks.",
        "",
        "USER-FACING PROSE RULES — apply to every title, intent, description, expected behavior, and step:",
        "Do not mention document/source attribution such as PRD, HLD, LLD, requirement document, source document, uploaded file, file name, ticket, markdown heading, 'the document states', 'the PRD requires', 'the spec suggests', or similar phrases.",
        "Write the behavior directly in product language. Example: use 'At least one interest must be selected to create an event', not 'PRD requires at least one interest...'."
    ])

def enum_constraint(field_name: str, allowed_values: list[str]) -> str:
    quoted = ", ".join(f'"{v}"' for v in allowed_values)
    return f'The "{field_name}" field must contain exactly one of these values: {quoted}. Any other value makes the entire response invalid.'

def build_version_transition_block(context: dict) -> str:
    summary = str(context.get("versionTransitionSummary") or "").strip()
    impact = context.get("versionImpactAssessment")
    if not summary and not impact:
        return ""
    
    impact_str = f"\nVERSION IMPACT SIGNALS:\n{json.dumps(impact, indent=2)}" if impact else ""
    return f"\nVERSION TRANSITION INTELLIGENCE:\n{summary or 'This generation is version-aware. Respect version changes before reusing coverage.'}{impact_str}\n"

def build_rag_evidence_block(rag_context: dict | None) -> str:
    if not rag_context or not isinstance(rag_context, dict):
        return "RAG EVIDENCE: none."
    
    summary = str(rag_context.get("summary") or "").strip()
    summary = summary if summary else "No RAG summary available."
    
    chunks = rag_context.get("retrieved_chunks") or []
    if not isinstance(chunks, list):
        chunks = []
        
    if not chunks:
        return f"RAG SUMMARY:\n{summary}\n\nRAG CHUNKS: none retrieved."
    
    # Sort chunks by score descending
    def get_score(c):
        val = c.get("finalScore")
        if val is None:
            val = c.get("score")
        if val is None and isinstance(c.get("payload"), dict):
            val = c["payload"].get("score")
        try:
            return float(val) if val is not None else 0.0
        except ValueError:
            return 0.0

    sorted_chunks = sorted(chunks, key=get_score, reverse=True)[:8]
    
    formatted = []
    for idx, chunk in enumerate(sorted_chunks):
        source_type = chunk.get("sourceType")
        if not source_type:
            source_type = chunk.get("source_type")
        if not source_type and isinstance(chunk.get("payload"), dict):
            source_type = chunk["payload"].get("sourceType")
        if not source_type:
            source_type = "UNKNOWN"
            
        score_val = get_score(chunk)
        score_str = f"{score_val:.4f}"
        
        text = chunk.get("text") or chunk.get("content")
        if not text and isinstance(chunk.get("payload"), dict):
            text = chunk["payload"].get("text")
        text = str(text or "")
        short_text = " ".join(text.split()).strip()[:500]
        
        formatted.append(f"[{idx + 1}] SOURCE={source_type} | SCORE={score_str}\n{short_text}")
        
    return f"RAG SUMMARY:\n{summary}\n\nTOP RETRIEVED CHUNKS (highest relevance first):\n" + "\n\n".join(formatted)

def clean_figma_text(value) -> str:
    return " ".join(str(value or "").split()).strip()

def is_useful_ui_text(text: str) -> bool:
    if len(text) < 2 or len(text) > 90:
        return False
    if re.match(r'^[\d\s:%.,/\\|()[\]{}_-]+$', text):
        return False
    if re.match(r'^(lorem ipsum|untitled|frame|group|rectangle|ellipse|vector|b-\d+)', text, re.IGNORECASE):
        return False
    return True

def is_likely_field_label(text: str) -> bool:
    clean = text.strip()
    if len(clean) < 2 or len(clean) > 40:
        return False
    if any(char in clean for char in ['.', '!', '?']):
        return False
        
    normalized = clean.rstrip(':*').strip()
    tokens = [t for t in normalized.split() if t]
    if len(tokens) == 0 or len(tokens) > 4:
        return False
    if any(len(t) > 24 for t in tokens):
        return False
    if any(not re.match(r'^[a-z0-9][a-z0-9_/-]*$', t, re.IGNORECASE) for t in tokens):
        return False
        
    action_like_prefixes = {
        'save', 'submit', 'continue', 'next', 'back', 'cancel', 'delete',
        'edit', 'create', 'update', 'close', 'retry', 'refresh', 'view'
    }
    if tokens[0].lower() in action_like_prefixes and len(tokens) <= 2:
        return False
        
    return clean.endswith(':') or clean.endswith('*') or len(tokens) <= 3

def count_figma_field_candidates(figma: dict = None) -> int:
    if not figma:
        figma = {}
    sample_screens = figma.get("sampleScreens") or []
    fields = set()
    for screen in sample_screens:
        for raw in screen.get("textBlocks") or []:
            text = clean_figma_text(raw)
            if is_useful_ui_text(text) and is_likely_field_label(text):
                fields.add(text)
    return len(fields)

def extract_all_field_labels(figma: dict = None) -> str:
    if not figma or not isinstance(figma, dict):
        return ""
    sample_screens = figma.get("sampleScreens") or []
    labels = set()
    for screen in sample_screens:
        for raw in screen.get("textBlocks") or []:
            clean = clean_figma_text(raw)
            if clean and 2 <= len(clean) <= 50:
                labels.add(clean)
    return "\n".join(list(labels)[:300])

def build_compact_figma_prompt_block(figma: dict = None) -> str:
    if not figma or not isinstance(figma, dict):
        return "FIGMA EVIDENCE: none."
        
    sample_screens = figma.get("sampleScreens") or []
    flows = figma.get("flows") or []
    
    all_text_blocks = set()
    all_actions = set()
    all_field_labels = set()
    
    for s in sample_screens:
        for t in s.get("textBlocks") or []:
            clean = clean_figma_text(t)
            if is_useful_ui_text(clean):
                all_text_blocks.add(clean)
                if is_likely_field_label(clean):
                    all_field_labels.add(clean)
        for a in s.get("actions") or []:
            clean = clean_figma_text(a)
            if clean:
                all_actions.add(clean)
                
    screen_summary = []
    for s in sample_screens[:120]:
        screen_summary.append({
            "name": s.get("name") or "",
            "purpose": s.get("purpose") or "screen",
            "textBlocks": [clean_figma_text(t) for t in s.get("textBlocks") or [] if is_useful_ui_text(clean_figma_text(t))][:14],
            "actions": [clean_figma_text(a) for a in s.get("actions") or [] if clean_figma_text(a)][:8]
        })
        
    field_candidates_by_screen = []
    for s in sample_screens[:180]:
        texts = [clean_figma_text(t) for t in s.get("textBlocks") or [] if is_useful_ui_text(clean_figma_text(t))]
        likely = [t for t in texts if is_likely_field_label(t)]
        fields_subset = likely if likely else texts
        
        item = {
            "screen": s.get("name") or "",
            "fields": fields_subset[:10],
            "actions": [clean_figma_text(a) for a in s.get("actions") or [] if clean_figma_text(a)][:6]
        }
        if item["fields"] or item["actions"]:
            field_candidates_by_screen.append(item)
            
    field_candidates_by_screen = field_candidates_by_screen[:90]
    
    flow_summary = []
    for f in flows[:30]:
        flow_summary.append({
            "from": f.get("from") or "",
            "to": f.get("to") or "",
            "trigger": f.get("trigger") or ""
        })
        
    total_screens = figma.get("totalScreens") or len(sample_screens) or 0
    
    return f"""Total screens: {total_screens}

TOP SCREENS:
{json.dumps(screen_summary, indent=2)}

NAVIGATION FLOWS:
{json.dumps(flow_summary, indent=2)}

FIELD CANDIDATES BY SCREEN:
{json.dumps(field_candidates_by_screen, indent=2)}

HIGH-CONFIDENCE FIELD LABELS:
{", ".join(list(all_field_labels)[:200]) if all_field_labels else 'None detected'}

ALL UI FIELDS AND LABELS:
{", ".join(list(all_text_blocks)[:220]) if all_text_blocks else 'None detected'}

ALL INTERACTIVE ACTIONS:
{", ".join(list(all_actions)[:120]) if all_actions else 'None detected'}"""

def build_requirements_prompt_block(context: dict = None) -> str:
    if not context:
        context = {}
    requirements = context.get("requirements") or {}
    business_context = context.get("businessContext") or {}
    
    prd_reqs = requirements.get("prd") if isinstance(requirements.get("prd"), list) else []
    hld_reqs = requirements.get("hld") if isinstance(requirements.get("hld"), list) else []
    lld_reqs = requirements.get("lld") if isinstance(requirements.get("lld"), list) else []
    
    biz_prd = business_context.get("prd", {})
    biz_hld = business_context.get("hld", {})
    biz_lld = business_context.get("lld", {})
    
    compact = {
        "prd_requirements": prd_reqs[:25],
        "hld_requirements": hld_reqs[:25],
        "lld_requirements": lld_reqs[:25],
        "business_requirements": {
            "prd": biz_prd.get("requirements", [])[:20] if isinstance(biz_prd.get("requirements"), list) else [],
            "hld": biz_hld.get("requirements", [])[:20] if isinstance(biz_hld.get("requirements"), list) else [],
            "lld": biz_lld.get("requirements", [])[:20] if isinstance(biz_lld.get("requirements"), list) else []
        }
    }
    return json.dumps(compact, indent=2)

def build_grounded_extraction_prompt(context: dict, rag_context: dict) -> str:
    prd = context.get("summaries", {}).get("prd") or ""
    hld = context.get("summaries", {}).get("hld") or ""
    figma = context.get("summaries", {}).get("figma") or {}
    rag_evidence = build_rag_evidence_block(rag_context)
    
    feature_name = context.get("featureName") or 'Unnamed Feature'
    feature_desc = context.get("featureDescription") or 'No description provided.'
    
    raw_api_spec = context.get("rawApiSpec")
    if not raw_api_spec:
        raw_api_spec = context.get("technicalContext", {}).get("apiSpec")
        
    has_raw_spec = False
    if raw_api_spec:
        if isinstance(raw_api_spec, list) and len(raw_api_spec) > 0:
            has_raw_spec = True
        elif isinstance(raw_api_spec, str) and len(raw_api_spec.strip()) > 20:
            has_raw_spec = True
            
    if has_raw_spec:
        spec_text = raw_api_spec if isinstance(raw_api_spec, str) else json.dumps(raw_api_spec, indent=2)
        raw_spec_block = f"""
EXPLICIT API SPECIFICATION (FILTER BEFORE USE):
The following is the COMPLETE API list from the design documents.
It covers MULTIPLE features, not just the current one.

YOUR JOB: From this list, extract ONLY the endpoints that are directly 
required to implement or test this feature:
- FEATURE NAME: {feature_name}
- FEATURE DESCRIPTION: {feature_desc}

Endpoints that belong to other features (e.g., authentication endpoints 
when the feature is about event creation) must NOT appear in your output.
When in doubt about an endpoint's relevance to this feature, EXCLUDE it.

FULL API LIST (select from this, do not copy all):
---
{spec_text}
---
"""
    else:
        raw_spec_block = """
NOTE: No explicit API specification table was provided. Extract only endpoint paths
that are written verbatim (e.g., "POST /events/create") in the EVIDENCE POOL below.
"""

    return f"""{output_contract_header('Extract API entities and endpoints from product documents')}

You are the Grounded Extraction Agent in a QA pipeline.
Your job is extraction, not generation. You copy out only what is explicitly written in the documents.

FEATURE FILTERING (CRITICAL):
You are generating tests ONLY for this specific feature:
- FEATURE NAME: {feature_name}
- FEATURE DESCRIPTION: {feature_desc}
You must evaluate the EVIDENCE POOL below and extract ONLY the endpoints that are actively used by or directly relevant to this specific feature. Do not extract the entire API list if it contains unrelated endpoints.

ENTITY CLASSIFICATION:
Include an entity only when it is something a mobile or web client directly creates, reads, updates,
or deletes through the API. 

These categories are always excluded — never appear in grounded_entities or apis output:
  Databases:       PostgreSQL, MySQL, MongoDB, SQLite, Redis, Elasticsearch, or any database
  Cloud storage:   AWS S3, GCS, Azure Blob, CDN, or any file storage service
  Messaging:       Socket.IO, WebSocket, Kafka, RabbitMQ, SQS, SNS, or any queue or event bus
  Frameworks:      Express, NestJS, Next.js, Fastify, React Native, Flutter, or any framework

FIELD VALUE RULES — violations make the entire response invalid:
- {enum_constraint('entity_type', ['api_resource'])}
- {enum_constraint('complexity', ['low', 'medium', 'high'])}
- {enum_constraint('type', ['input', 'button', 'selector', 'upload', 'picker'])}
- The "endpoint" path in the "apis" array must match exactly what is written in the documents.
- The "evidence_quote" field must contain text that exists verbatim or near-verbatim in the EVIDENCE POOL below. Writing fabricated text makes the response invalid.
- The "evidence_quote" field must never begin with the word "Inferred".

OUTPUT CELLING: Output at most 15 apis items. You MUST filter the list down to ONLY the endpoints relevant to the current feature. Outputting unrelated endpoints makes the response invalid.

EVIDENCE POOL — extract only from what is written below:
---{raw_spec_block}

REQUIREMENT EVIDENCE:
{prd}

ARCHITECTURE EVIDENCE:
{hld}

FIGMA:
{json.dumps(figma, indent=2)}

RAG:
{rag_evidence}
---

OUTPUT SCHEMA:
The JSON object has exactly three keys: "grounded_entities", "apis", "ui_components".

{{
  "grounded_entities": [
    {{
      "entity": "User",
      "entity_type": "api_resource",
      "operations_confirmed": ["read", "update"],
      "permission_note": "users can only update their own profile",
      "evidence_quote": "GET /users/me returns profile status"
    }}
  ],
  "apis": [
    {{
      "method": "POST",
      "endpoint": "/auth/request-otp",
      "complexity": "high",
      "evidence_quote": "POST /auth/request-otp — Input: mobile_number"
    }}
  ],
  "ui_components": [
    {{
      "screen": "Login",
      "element": "Mobile Number",
      "type": "input",
      "evidence_quote": "User enters mobile number to request OTP"
    }}
  ]
}}""".strip()

def is_few_shot_leak(item: any, lowercase_corpus: str = None) -> bool:
    if not item or not isinstance(item, dict):
        return False
        
    quote = str(item.get("evidence_quote") or item.get("intent") or item.get("expected_behavior") or "").strip()
    low_quote = quote.lower()
    
    if (
        'returns profile status' in low_quote or
        'input: mobile_number' in low_quote or
        'enters mobile number to request otp' in low_quote or
        'list read required to support confirmed create operation' in low_quote or
        'titles to be between 5 and 100 characters' in low_quote
    ):
        return True
        
    endpoint = str(item.get("endpoint") or item.get("path") or "").strip().lower()
    field = str(item.get("field") or item.get("element") or "").strip().lower()
    screen = str(item.get("screen") or "").strip().lower()
    
    is_otp_endpoint = endpoint == '/auth/request-otp' or endpoint == '/api/v1/auth/otp'
    is_otp_field = field == 'mobile number' and screen == 'login'
    is_event_field = field == 'event title'
    
    if is_otp_endpoint or is_otp_field or is_event_field:
        if lowercase_corpus:
            is_endpoint_supported = is_otp_endpoint and (endpoint in lowercase_corpus or 'otp' in lowercase_corpus)
            is_field_supported = (is_otp_field and ('mobile' in lowercase_corpus or 'phone' in lowercase_corpus)) or \
                                 (is_event_field and ('event' in lowercase_corpus or 'title' in lowercase_corpus))
                                 
            if is_endpoint_supported or is_field_supported:
                return False
        return True
        
    return False

def filter_hallucinated_entities(entities: list, lowercase_corpus: str = None) -> list:
    out = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        if is_few_shot_leak(entity, lowercase_corpus):
            continue
            
        quote = str(entity.get("evidence_quote") or "").strip()
        if quote.startswith('Extracted from rawApiSpec:'):
            out.append(entity)
            continue
            
        name = str(entity.get("entity") or entity.get("name") or entity.get("endpoint") or "").strip().lower()
        if not name or name in ('undefined', 'null'):
            continue
            
        if not quote:
            continue
            
        if quote.lower().startswith('inferred'):
            continue
            
        if name in INFRASTRUCTURE_DENY_LIST:
            continue
            
        out.append(entity)
    return out

def build_raw_api_spec_from_documents(context: dict, rag_context: dict = None) -> str | None:
    if context.get("rawApiSpec") and isinstance(context["rawApiSpec"], str) and len(context["rawApiSpec"].strip()) > 10:
        return context["rawApiSpec"]
        
    text_sources = []
    
    if rag_context and isinstance(rag_context.get("retrieved_chunks"), list):
        raw_text = "\n".join(c.get("text") or "" for c in rag_context["retrieved_chunks"] if isinstance(c, dict))
        if raw_text:
            text_sources.append(raw_text)
            
    tc = context.get("technicalContext") or {}
    if isinstance(tc.get("apiSpec"), str):
        text_sources.append(tc["apiSpec"])
    if isinstance(tc.get("rawHld"), str):
        text_sources.append(tc["rawHld"])
    if isinstance(tc.get("rawPrd"), str):
        text_sources.append(tc["rawPrd"])
    if isinstance(tc.get("lldText"), str):
        text_sources.append(tc["lldText"])
    if isinstance(tc.get("hldText"), str):
        text_sources.append(tc["hldText"])
        
    if isinstance(tc.get("endpoints"), list):
        parts = []
        for e in tc["endpoints"]:
            if isinstance(e, str):
                parts.append(e)
            elif isinstance(e, dict):
                parts.append(f"{e.get('method') or 'GET'} {e.get('endpoint') or e.get('path') or ''}")
        text_sources.append("\n".join(parts))
        
    reqs = context.get("requirements") or {}
    for key in ['hld', 'lld', 'prd']:
        if isinstance(reqs.get(key), list):
            text_sources.append("\n".join(reqs[key]))
            
    biz = context.get("businessContext") or {}
    for key in ['hld', 'lld', 'prd']:
        r = biz.get(key, {}).get("requirements")
        if isinstance(r, list):
            text_sources.append("\n".join(r))
            
    summaries = context.get("summaries") or {}
    for key in ['prd', 'hld', 'lld']:
        if isinstance(summaries.get(key), str):
            text_sources.append(summaries[key])
            
    all_text = "\n".join(src for src in text_sources if src)
    lines = all_text.split('\n')
    found = set()
    
    for line in lines:
        match = re.search(r'\b(GET|POST|PUT|PATCH|DELETE)\s+(/[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=%:]+)', line, re.IGNORECASE)
        if match:
            method, path = match.group(1), match.group(2)
            found.add(f"{method.upper()} {path}")
            
    if found:
        return "\n".join(sorted(found))
    return None

def build_crud_inference_prompt(grounded_entities: list, context: dict) -> str:
    feature_name = context.get("featureName") or 'Unnamed Feature'
    entity_count = len(grounded_entities)
    raw_api_spec = context.get("rawApiSpec") or context.get("technicalContext", {}).get("apiSpec")
    has_raw_spec = bool(raw_api_spec)
    
    if has_raw_spec:
        return f"""{output_contract_header('CRUD inference disabled — raw API spec is authoritative')}
An explicit API specification is present. No inference is allowed.
Output exactly this JSON object and nothing else:
{{"apis": []}}""".strip()

    max_endpoints = 5 if has_raw_spec else min(entity_count * 4, 20)
    
    if entity_count < 2:
        return f"""{output_contract_header('CRUD inference — early exit due to insufficient entities')}

The grounded entity list contains {entity_count} confirmed API resource(s), which is below
the minimum of 2 required to infer CRUD endpoints safely.

Output exactly this JSON object and nothing else:
{{"apis": []}}""".strip()

    entity_names = ", ".join(f'"{e.get("entity")}"' for e in grounded_entities if isinstance(e, dict))
    raw_spec_note = """
IMPORTANT: An explicit API specification was already provided to Pass 1. Pass 1 has extracted
the real endpoint paths from that specification. Your job in Pass 2 is only to fill genuine
gaps — for example, if the spec shows DELETE /events/:id but no GET /events/:id, you may
infer the GET. Do not change the path format or prefix. If Pass 1's grounded APIs already
cover the CRUD surface adequately, output {"apis": []} immediately.
""" if has_raw_spec else ''

    return f"""{output_contract_header('Infer REST CRUD endpoints for confirmed API entities')}

You are the CRUD Inference Agent in a QA pipeline.
Your input is a list of confirmed API resource entities extracted from product documents.
Your output is a list of REST endpoints inferred from standard CRUD conventions.{raw_spec_note}

FIELD VALUE RULES — violations make the entire response invalid:
- {enum_constraint('method', ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])}
- {enum_constraint('complexity', ['low', 'medium', 'high'])}
- The "evidence_quote" field must begin with exactly this phrase: "Inferred from standard CRUD for" followed by the entity name. Any other value makes the response invalid.
- The "endpoint" path must use the SAME path format as the grounded APIs already extracted (e.g., if grounded APIs use "/events/:id", use that format, not "/api/v1/events/:id"). It must never contain a technology name such as postgres, redis, s3, socket, kafka. An endpoint containing a technology name makes the response invalid.

INFERENCE RULES — apply in order:
1. Work only with these confirmed entities: {entity_names}. Adding endpoints for any other entity makes the response invalid.
2. For each entity with "create" confirmed: infer GET (list) endpoint if not already grounded.
3. For each entity with "update" confirmed: infer GET (by id) if not already grounded.
4. For each entity whose permission_note mentions deletion: infer DELETE (by id) if not already grounded.
5. Do not add any endpoint that duplicates a path already in the grounded APIs list.
6. When in doubt, output {{"apis": []}} — an empty list is always valid.

A VALID business rule test must verify a CONSTRAINT or PERMISSION BOUNDARY that the system enforces.
It answers the question: "What happens when a user tries to violate a rule?"
Valid subjects: ownership restrictions, mandatory preconditions, time constraints, role gates, capacity limits.

These categories are INVALID as business rule tests — generating them makes the response invalid:
- UI timer display behavior or countdown animations (these are frontend tests)
- Slot count display updates in real-time
- Discovery radius, city filtering, or geographic scoping behaviors
- Active status filtering (is_active = true) unless it directly blocks a user action
- Client-side form validation that duplicates what a UI test covers
- Optional UX behaviors ("user can skip profile completion")
- Feature descriptions that don't enforce a boundary ("global city discovery enabled")

OUTPUT CEILING: Output at most {max_endpoints} endpoints total. Outputting more makes the response invalid.

FEATURE NAME: {feature_name}

GROUNDED ENTITIES FROM PASS 1:
{json.dumps(grounded_entities, indent=2)}

OUTPUT SCHEMA:
The JSON object has exactly one key: "apis".
Use the path format from the grounded entities above, not invented path formats.

{{
  "apis": [
    {{
      "method": "GET",
      "endpoint": "/events/nearby",
      "complexity": "medium",
      "evidence_quote": "Inferred from standard CRUD for Event — list read required to support confirmed create operation"
    }}
  ]
}}""".strip()

def build_shared_context_block(context: dict, rag_context: dict, raw_api_spec: str | None) -> str:
    prd = context.get("summaries", {}).get("prd") or ""
    hld = context.get("summaries", {}).get("hld") or ""
    lld = context.get("summaries", {}).get("lld") or ""
    requirements_block = build_requirements_prompt_block(context)
    technical_context = context.get("technicalContext") or {}
    rag_evidence = build_rag_evidence_block(rag_context)
    already_covered = context.get("summaries", {}).get("alreadyCovered") or ""
    
    sibling_warning = f"""⛔ DO NOT GENERATE TESTS FOR THE FOLLOWING CONCEPTS — THEY ARE ALREADY COVERED BY SIBLING FEATURES:
{already_covered}
If you generate a test that overlaps with any concept above, it will be automatically rejected and invalidate your response.
""" if already_covered else ""

    spec_note = f"EXPLICIT API SPECIFICATION (every generated test endpoint MUST come from this list):\n{raw_api_spec}" if raw_api_spec else "NOTE: No explicit API spec provided. Extract only endpoints written verbatim in the evidence above."

    return "\n".join([
        f"FEATURE NAME: {context.get('featureName', 'Unnamed Feature')}",
        f"FEATURE DESCRIPTION: {context.get('featureDescription', '')}",
        "",
        "REQUIREMENT EVIDENCE:",
        prd,
        "",
        "ARCHITECTURE EVIDENCE:",
        hld,
        "",
        "DESIGN EVIDENCE:",
        lld,
        "",
        sibling_warning,
        "",
        spec_note,
        "",
        "REQUIREMENTS:",
        requirements_block,
        "",
        "TECHNICAL CONTEXT:",
        json.dumps(technical_context, indent=2),
        "",
        "RAG EVIDENCE:",
        rag_evidence
    ])

def build_fusion_pass_prompt(unified_context: dict, project_existing_tests: list) -> str:
    prd = unified_context.get("summaries", {}).get("prd") or ""
    feature_name = unified_context.get("featureName") or 'Unnamed Feature'
    
    siblings_block = []
    for s in unified_context.get("graphContext", {}).get("siblings") or []:
        managed = ", ".join(e.get("name") for e in s.get("entities", []) if e.get("relation") == 'primary')
        deps = ", ".join(e.get("name") for e in s.get("entities", []) if e.get("relation") == 'reference')
        siblings_block.append(f"- {s.get('name')}: {s.get('abstract')}\n  [Managed: {managed or 'None'}] | [Depends On: {deps or 'None'}]")
    siblings_str = "\n".join(siblings_block) if siblings_block else 'No direct architectural siblings found.'

    ancestor_str = ""
    if unified_context.get("semanticAncestorLabel"):
        reason = unified_context.get("semanticAncestorReason") or unified_context.get("semanticAncestor", {}).get("reason") or "Graph context matched multiple features."
        ancestor_str = f"""GRAPH-SELECTED SEMANTIC ANCESTOR SET (HIGH-CONFIDENCE GRAPH REUSE SOURCES):
Feature(s): {unified_context.get("semanticAncestorLabel")}
Reason(s): {reason}
"""

    prev_ver_str = ""
    if unified_context.get("previousVersionTests"):
        prev_ver_str = f"PREVIOUS VERSION TESTS (HIGHEST PRIORITY REUSE):\n{json.dumps(unified_context['previousVersionTests'], indent=2)}\n"

    transition_str = build_version_transition_block(unified_context)

    # Simplified UML format for python context
    graph_context = unified_context.get("graphContext", {})
    edges = graph_context.get("relationships", {}).get("edges", [])
    uml_parts = ["@startuml", f"[{feature_name}] as Current"]
    for idx, edge in enumerate(edges):
        source = edge.get("source", "Current")
        target = edge.get("target", "")
        etype = edge.get("type", "uses")
        if target:
            uml_parts.append(f"[{source}] --> [{target}] : {etype}")
    uml_parts.append("@enduml")
    graph_uml = "\n".join(uml_parts)

    return f"""{output_contract_header('Analyze Cross-Feature Overlap (Graph Fusion)')}

You are the Senior Graph Fusion QA Architect. 
Your goal is to ensure the testing suite is lean, professional, and DRY (Don't Repeat Yourself).
A professional QA never writes a test twice. If a sibling feature already tests a shared component or API, we REUSE it.

CURRENT FEATURE: {feature_name}
REQUIREMENTS: {prd}

PROJECT ECOSYSTEM (Level 3): 
{graph_context.get("ecosystem") or "Unknown"}

SIBLING FEATURE ABSTRACTS (Detailed Architectural Context):
{siblings_str}

FEATURE FLOW NEIGHBORHOOD (Mind Map / UML):
{graph_uml}

EXISTING PROJECT TESTS (Level 1 - Semantically related):
{json.dumps(project_existing_tests[:100], indent=2)}

{ancestor_str}
{prev_ver_str}{transition_str}
TASK:
1. Identify tests from "Existing Project Tests" that cover requirements of the "Current Feature".
2. Create a list of "covered_endpoints" (API Method + Path) that already have sufficient coverage.
3. Create a list of "covered_flows" (Functional journeys) that are already tested.
4. Define the "New Delta": What exactly is unique to THIS feature that hasn't been tested yet?

INHERITANCE MODES:
- INHERIT_EXACT: Use this if the test matches the current requirement perfectly. You will provide only the reference_key.
- INHERIT_ADAPTED: Use this if the test is 90% relevant but needs a small tweak (e.g., different role, different endpoint version). You must provide "repair_instructions".

RULES:
- If an API endpoint (e.g. POST /auth/send-otp) is already tested for its happy and negative paths in a sibling feature, mark it in "covered_endpoints".
- PRIORITIZE REUSE: If a test in the "EXISTING PROJECT TESTS" matches a current requirement or endpoint, you MUST inherit it. Avoid generating new tests for things we already have.
- 90% REUSE TARGET: If this feature is a variation of an existing feature, aim to inherit ~90% of the relevant tests.
- SHARED NAMES ARE NOT ENOUGH: Do not inherit a test only because it shares broad nouns like user, event, profile, or flow. Cross-feature reuse is valid only when the current evidence shows the same endpoint, the same logic node, or the same explicit behavior.
- PREVIOUS VERSION MANDATE: If "PREVIOUS VERSION TESTS" are provided, they are the GOLD STANDARD. You MUST inherit every single test from the previous version unless the requirement has explicitly changed or the endpoint was removed.
- VERSION LINEAGE: Treat previous-version reuse as internal lineage. Keep visible labels version-neutral unless the current feature is explicitly cross-feature reuse.
- METHOD INTEGRITY: A GET and a POST on the same endpoint are usually different actions. Only inherit across different methods if the intent is IDENTICAL.
- DELTA RULE: If the "Current Feature" introduces a NEW PARAMETER, NEW ROLE, or NEW STATE to an existing endpoint, DO NOT reuse the old test blindly. You must identify that a new test is needed for this delta.
- The "already_covered_summary" should be a message to subsequent agents: "DO NOT write tests for X, Y, Z as they are already in the library. Focus only on the new deltas A, B."

OUTPUT SCHEMA:
{{
  "inherited_tests": [
     {{ 
       "reference_key": "proj_id::feat_id::ver::category::test_id",
       "identity_hash": "a1b2c3d4e5f6",
       "mode": "INHERIT_EXACT",
       "title": "Clear Title",
       "intent": "Full intent statement"
     }},
     {{ 
       "reference_key": "proj_id::feat_id::ver::category::test_id",
       "identity_hash": "b2c3d4e5f6g7",
       "mode": "INHERIT_ADAPTED",
       "repair_instructions": "Change authentication role from 'User' to 'Admin'",
       "title": "Clear Title",
       "intent": "Full intent statement"
     }}
  ],
  "covered_endpoints": [
     {{ "method": "POST", "path": "/api/v1/auth/otp" }}
  ],
  "covered_flows": [
     "User login journey",
     "Token validation"
  ],
  "already_covered_summary": "Endpoints A and B are fully covered. Focus only on the new Discovery logic."
}}""".strip()

def build_api_agent_task_prompt(
    target_chunk: list,
    focus_mode: str,
    max_tests: int,
    feature_name: str = 'Unnamed Feature',
    feature_description: str = '',
    already_covered_summary: str = ''
) -> str:
    focus_modes = {
        "happy": {
            "title": 'HAPPY PATH TESTS ONLY',
            "rule": 'Every test in this response must have a 2xx status code. Allowed values for status_code: 200, 201, 202, 204.',
            "forbidden": 'A test with a non-2xx status code makes this response invalid.',
            "coverage_matrix": 'Evaluate: 1. Standard Success. 2. Edge-case Success (e.g., optional fields omitted). 3. Role-based Success (e.g., Admin vs User).'
        },
        "negative": {
            "title": 'NEGATIVE AND VALIDATION TESTS ONLY',
            "rule": 'Every test in this response must have a non-2xx status code. Allowed values for status_code: 400, 401, 403, 404, 409, 422.',
            "forbidden": 'A test with a 2xx, 500, or 503 status code makes this response invalid.',
            "coverage_matrix": 'Evaluate: 1. Auth/Security (401/403). 2. Input Validation / Malformed Data (400/422). 3. Business Rule / State Violations (409). 4. Not Found (404).'
        },
        "chaos": {
            "title": 'CHAOS AND CONCURRENCY TESTS ONLY',
            "rule": 'Every test must represent a race condition, rate limit, or domain-specific failure. Allowed status codes: 409, 429, 500, 503, or 401 on retry.',
            "forbidden": """DO NOT FORCE TESTS. For each assigned endpoint, reason about its systemic risk profile in "endpoint_analysis" BEFORE deciding to generate a chaos test.

Risk reasoning guide:
  WRITE a chaos test when the endpoint matches any of these profiles:
  - High-traffic reads (e.g. GET /events/nearby, GET /feed, GET /search) → rate-limit (429) and cache stampede scenarios
  - Auth-dependent reads (e.g. GET /users/me, GET /profile) → degraded auth service scenarios (503 → 401 on retry)
  - State-mutating writes (POST/PUT/PATCH/DELETE) → race conditions, partial writes, idempotent retries
  - Any endpoint with downstream dependencies named in the EVIDENCE POOL → cascade failure scenarios

  SKIP (omit entirely) when the endpoint matches:
  - Simple health/config reads with no dependencies (GET /health, GET /status)
  - Stateless logout with no meaningful side effects
  - Any endpoint where failure has no observable consequence to data integrity or UX

The key question: "If this endpoint fails or gets hammered, does something break that a user or the system would notice?" If yes, write the test. If no, omit it.""",
            "coverage_matrix": """Evaluate each endpoint against these categories — pick only those that apply:
  1. Concurrent Mutations — race conditions (POST/PUT/PATCH/DELETE)
  2. Rate Limiting (429) — any high-traffic endpoint including GETs
  3. Idempotent Retries — state-mutating writes only
  4. Downstream Service Failure — any endpoint with named dependencies
  5. Cache Stampede — high-traffic GET endpoints backed by cache"""
        }
    }
    
    focus = focus_modes.get(focus_mode, focus_modes["happy"])
    
    endpoint_instruction = f"ASSIGNED ENDPOINTS:\nGenerate tests for these specific endpoints only.\n{json.dumps(target_chunk, indent=2)}" if target_chunk else "Generate tests for the endpoints described in the shared context above."
    
    complexity_score = 0
    for ep in target_chunk:
        c = str(ep.get("complexity") or 'medium').lower()
        complexity_score += (4 if c == 'high' else 3 if c == 'medium' else 1)
        
    ceiling = max_tests if max_tests > 0 else min(complexity_score if complexity_score > 0 else len(target_chunk) * 3, 15)
    
    sibling_avoid = f"""\n⛔ DO NOT GENERATE TESTS FOR THE FOLLOWING CONCEPTS (Already Covered by Sibling Features):\n{already_covered_summary}\nAny test overlapping with the above will be automatically rejected and invalidate your response.\n""" if already_covered_summary else ""

    return f"""TASK: Generate {focus["title"]} for the assigned API endpoints

{output_contract_header('Generate focused API worker test cases')}

FOCUS MODE: {focus["title"]}
{focus["rule"]}
{focus["forbidden"]}
COVERAGE MATRIX: {focus["coverage_matrix"]}

FEATURE SCOPE — read this before generating any test:
You are generating tests ONLY for this feature: "{feature_name}".
Feature goal: "{feature_description or 'See the evidence summary in the system context.'}".
Every test title, intent, and step must be directly relevant to this feature.{sibling_avoid}
Generating a test for a different feature or module makes the response invalid.

=== ANTI-SPAM & ANTI-LAZY RULES ===
1. FORCED REASONING: Complete "endpoint_analysis" BEFORE writing any tests.
2. NO GENERIC SPAM: No "Database connection failed" tests for every endpoint. Chaos applies only where failure has observable consequences named in the shared context.
3. NO QUOTAS: Simple endpoints need 1 test. Complex endpoints need 4-5. Let your analysis dictate the count.
4. DELTA AWARENESS: If an assigned endpoint is already partially covered (see shared context), you MUST still generate NEW tests for any unique parameters, constraints, or business logic introduced by THIS feature.

FIELD VALUE RULES — violations make the entire response invalid:
- {enum_constraint('test_suite', ['Smoke', 'Regression', 'Edge', 'Chaos'])}
- {enum_constraint('priority', ['High', 'Medium', 'Low'])}
- {enum_constraint('method', ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])}
- The "expected_result" field must be a JSON object with exactly four keys: "status_code" (a number), "db_changes" (array), "side_effects" (array), and "negative_assertions" (array). A plain string value makes the response invalid.
- The "steps" array must use objects with "content" and a concise one-line "expectedResult" for every step that can show an observable outcome. Keep the top-level "expected_result" as the whole-test outcome only.
- The "endpoint" field must exactly match one assigned endpoint path. Inventing or prefixing paths makes the response invalid.
- The "intent" field must explain the specific behavior being tested. Generic intents make the response invalid.

OUTPUT CEILING: At most {ceiling} tests. This is a ceiling, not a target.

{endpoint_instruction}

OUTPUT SCHEMA — begin with endpoint_analysis, then api_tests:
{{
  "endpoint_analysis": [
    {{
      "endpoint": "/api/v1/events",
      "method": "POST",
      "chaos_eligible": true,
      "chaos_reason": "State-mutating write with downstream DB dependency. Race condition risk.",
      "reasoning": "Requires host role, full payload, downstream side effects.",
      "planned_test_count": 2
    }}
  ],
  "api_tests": [
    {{
      "id": "API-1",
      "title": "Participant receives 403 when attempting to create an event",
      "intent": "Only hosts can create events; this verifies the role-based boundary.",
      "test_suite": "Regression",
      "priority": "High",
      "confidence": 0.95,
      "module": "Events",
      "method": "POST",
      "endpoint": "/api/v1/events",
      "description": "Authenticated participant submits a valid event payload but is rejected.",
      "steps": [
        {{ "content": "Given an authenticated user with the 'participant' role", "expectedResult": "The user is authenticated and available for the request." }},
        {{ "content": "When POST /api/v1/events is called with a valid payload", "expectedResult": "The request reaches authorization and validation checks." }},
        {{ "content": "Then the response status is 403 Forbidden", "expectedResult": "The API returns 403 Forbidden." }}
      ],
      "expected_result": {{
        "status_code": 403,
        "db_changes": [],
        "side_effects": [],
        "negative_assertions": ["No event row is created in the database"]
      }}
    }}
  ]
}}""".strip()

def build_api_agent_prompt(
    context: dict,
    rag_context: dict,
    target_chunk: list = None,
    focus_mode: str = 'happy'
) -> dict:
    if target_chunk is None:
        target_chunk = []
        
    complexity_score = 0
    for ep in target_chunk:
        c = str(ep.get("complexity") or 'medium').lower()
        complexity_score += (4 if c == 'high' else 3 if c == 'medium' else 1)
        
    endpoint_count = len(target_chunk) or 1
    has_valid_complexity = any(ep.get("complexity") for ep in target_chunk)
    raw_ceiling = complexity_score if has_valid_complexity else endpoint_count * 3
    
    risky_endpoint_count = 0
    for ep in target_chunk:
        strategy = ep.get("strategy_profile") or {}
        if isinstance(strategy, dict) and strategy.get("chaosEligible"):
            risky_endpoint_count += 1
            continue
            
        method = str(ep.get("method") or '').upper()
        complexity = str(ep.get("complexity") or '').lower()
        fallback_weight = (5 if method in ['POST', 'PUT', 'PATCH', 'DELETE'] else 0) + (3 if complexity == 'high' else 0)
        if fallback_weight >= 4:
            risky_endpoint_count += 1
            
    focus_ceilings = {
        "happy": min(max(endpoint_count, 3), 10),
        "negative": min(max(math.ceil(endpoint_count * 0.9), 3), 10),
        "chaos": min(max(math.ceil(risky_endpoint_count * 0.6), 1 if risky_endpoint_count > 0 else 0), 5)
    }
    
    max_tests = min(raw_ceiling, focus_ceilings.get(focus_mode, 5))
    
    system_content = build_shared_context_block(context, rag_context, context.get("rawApiSpec"))
    user_content = build_api_agent_task_prompt(
        target_chunk,
        focus_mode,
        max_tests,
        context.get("featureName") or 'Unnamed Feature',
        context.get("featureDescription") or '',
        context.get("summaries", {}).get("alreadyCovered") or ''
    )
    
    return {
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]
    }

def build_ui_agent_prompt(context: dict, target_chunk: list = None) -> dict:
    if target_chunk is None:
        target_chunk = []
    figma = context.get("summaries", {}).get("figma") or {}
    smoke_mode = context.get("flags", {}).get("smokeMode") is True
    
    field_labels = extract_all_field_labels(figma)
    field_label_count = len([f for f in field_labels.split('\n') if f]) if field_labels else 0
    figma_field_count = count_figma_field_candidates(figma)
    component_count = len(target_chunk)
    
    available_field_count = max(figma_field_count, field_label_count)
    has_field_evidence = (
        available_field_count > 0 or
        component_count > 0 or
        len(str(context.get("summaries", {}).get("prd") or "")) > 20 or
        len(str(context.get("summaries", {}).get("hld") or "")) > 20
    )
    
    if has_field_evidence:
        if smoke_mode:
            max_tests = 5
        elif component_count > 0:
            max_tests = min(max(component_count * 2, 10), 50)
        else:
            max_tests = min(max(math.ceil(available_field_count * 0.45), 12), 80)
            
        min_tests = min(max_tests, max(4, math.ceil(component_count * 0.5)) if component_count > 0 else max(8, math.ceil(max_tests * 0.45)))
    else:
        max_tests = 0
        min_tests = 0
        
    if not has_field_evidence:
        component_instruction = 'No interactive form fields are supported by the current feature evidence. Output exactly {"ui_validations":[]}.'
    elif component_count > 0:
        component_instruction = f"ASSIGNED COMPONENTS:\nGenerate validations for these UI components only. Testing any component not in this list makes the response invalid.\n{json.dumps(target_chunk, indent=2)}"
    else:
        component_instruction = 'Generate UI validations by mining the FIGMA EVIDENCE in the shared context, especially FIELD CANDIDATES BY SCREEN and HIGH-CONFIDENCE FIELD LABELS.'
        
    already_covered = context.get("summaries", {}).get("alreadyCovered") or ""
    sibling_avoid = f"\n⛔ DO NOT GENERATE TESTS FOR THE FOLLOWING CONCEPTS (Already Covered by Sibling Features):\n{already_covered}\nAny test overlapping with the above will be automatically rejected and invalidate your response.\n" if already_covered else ""

    no_field_notice = '\nNo field evidence exists in the current feature. Output no UI validations.' if not has_field_evidence else ''

    user_content = f"""TASK: Generate UI field validation test cases

FEATURE SCOPE:
Generate UI validations ONLY for this feature: "{context.get("featureName", "Unnamed Feature")}".
Feature goal: "{context.get("featureDescription") or 'See the evidence summary in the system context.'}".{sibling_avoid}
Only include fields that belong to this feature's screens. Fields from other features make the response invalid.{no_field_notice}

{output_contract_header('Generate UI validations')}

You are a Senior Frontend QA Engineer generating UI validation test cases only.

A test item is a valid UI validation only when all three of the following are true:
1. The field is a visible, interactive element that a user physically operates: an input field, dropdown, file picker, date selector, or toggle.
2. The validation enforces a business rule that blocks or changes a user action.
3. The field is explicitly named in the supplied product, design, or screen evidence below.

A test item is invalid as a UI validation when:
- It describes server-side behavior, database storage, encryption, or token management.
- It tests a concept not visible in the screen evidence (e.g. session state, auth headers).
- The "field" value is a generic description rather than the exact label from the screen.

FIELD VALUE RULES — violations make the entire response invalid:
- {enum_constraint('test_suite', ['Smoke', 'Regression'])}
- {enum_constraint('priority', ['High', 'Medium', 'Low'])}
- {enum_constraint('validation_type', ['required', 'minLength', 'maxLength', 'format', 'state'])}
- The "field" value must be the exact label string of the interactive element as it appears in Figma or the documents. A generic name such as "text input" or "field" makes the response invalid.
- The "expected_behavior" value must describe what the user sees on screen when the validation triggers. Describing a server action makes the response invalid.

OUTPUT TARGET:
- Generate at least {min_tests} validations when the evidence contains enough distinct fields.
- Output at most {max_tests} validations. Outputting more makes the response invalid.
- Cover distinct field labels first. Repeating the same field and validation_type combination makes the response invalid.

{component_instruction}

OUTPUT SCHEMA:
The JSON object has exactly one key: "ui_validations".
The values below are examples — replace each one with a real value from the evidence.

{{
  "ui_validations": [
    {{
      "id": "UI-1",
      "field": "Event Title",
      "intent": "Event titles must be between 5 and 100 characters to prevent empty or excessively long listings.",
      "test_suite": "Smoke",
      "priority": "High",
      "confidence": 0.90,
      "validation_type": "maxLength",
      "expected_behavior": "When the user types more than 100 characters into the Event Title field, the field border turns red and an inline error appears below: Title must be 100 characters or fewer"
    }}
  ]
}}""".strip()

    system_content = build_shared_context_block(context, {}, context.get("rawApiSpec"))
    
    return {
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]
    }

def build_e2e_agent_prompt(
    context: dict,
    pruned_api_dictionary: list,
    pruned_ui_dictionary: list,
    rag_context: dict,
    discovered_api_surface: int = None
) -> str:
    prd = context.get("summaries", {}).get("prd") or ""
    hld = context.get("summaries", {}).get("hld") or ""
    business_context = context.get("businessContext") or {}
    rag_evidence = build_rag_evidence_block(rag_context)
    api_count = len(pruned_api_dictionary)
    
    if discovered_api_surface is None:
        discovered_api_surface = api_count
        
    smoke_mode = context.get("flags", {}).get("smokeMode") is True
    cross_feature_journeys = context.get("crossFeatureJourneys") or []
    cross_feature_budget_percent = float(context.get("generationHints", {}).get("crossFeatureBudgetPercent") or 20)
    version_transition_block = build_version_transition_block(context)
    
    max_e2e = 3 if smoke_mode else min(max(math.ceil(discovered_api_surface / 3), 8), 20)
    max_edge = 2 if smoke_mode else min(max(math.ceil(api_count / 4), 6), 14)
    
    prd_rules = len(business_context.get("prd", {}).get("requirements") or []) if isinstance(business_context.get("prd", {}).get("requirements"), list) else 5
    max_business = 2 if smoke_mode else max(prd_rules if prd_rules > 0 else 10, 10)
    
    min_e2e = 1 if smoke_mode else min(max_e2e, max(6, math.ceil(max_e2e * 0.6)))
    min_edge = 1 if smoke_mode else min(max_edge, max(4, math.ceil(max_edge * 0.55)))
    corruption_edge_target = max(1, math.ceil(min_edge * 0.25))
    max_cross_feature_e2e = max(1, math.floor(max_e2e * (max(0.0, min(100.0, cross_feature_budget_percent)) / 100.0))) if cross_feature_journeys else 0
    
    already_covered = context.get("summaries", {}).get("alreadyCovered") or ""
    covered_str = f"PROJECT INHERITED COVERAGE (Already tested in sibling features - DO NOT DUPLICATE OR RE-GENERATE THESE):\n{already_covered}\n" if already_covered else ""

    return f"""{output_contract_header('Generate E2E flows, edge cases, and business rule tests')}

FEATURE SCOPE:
You are generating tests ONLY for this feature: "{context.get("featureName", "Unnamed Feature")}".
Feature goal: "{context.get("featureDescription") or 'See the evidence summaries in the evidence pool.'}".
Every test must be directly relevant to this feature. Tests for other features make the response invalid.
{version_transition_block}
{covered_str}
You are the Senior E2E and Business Test Agent in a QA pipeline.
Your task is to build a lean regression suite that complements existing coverage.
DO NOT generate tests for journeys or rules that are listed in the "PROJECT INHERITED COVERAGE" above.
Only use the API and UI dictionaries below to construct NEW tests.

FIELD VALUE RULES — violations make the entire response invalid:
- {enum_constraint('test_suite', ['Smoke', 'Regression', 'Chaos', 'Edge'])}
- {enum_constraint('priority', ['High', 'Medium', 'Low'])}
- A Chaos test must name an actual service from the EVIDENCE POOL in its title or intent. Using a generic placeholder such as "the service" or "downstream system" makes the response invalid.
- A business test's "intent" field must closely paraphrase a specific business rule from the requirement evidence. A vague intent such as "verify business rules are enforced" makes the response invalid.
- All array fields (preconditions, ui_journey_steps, backend_assertions, steps) must contain at least one item. An empty array in any of these fields makes the response invalid.
- The "expected_result" field in business_tests must be a JSON object with status_code, db_changes, side_effects, and negative_assertions. A plain string value makes the response invalid.
- The "steps" array must use objects with "content" and a concise one-line "expectedResult" for every step that can show an observable outcome. Keep the top-level "expected_result" as the whole-test outcome only.

OUTPUT CEILINGS:
- "e2e_tests" array: at most {max_e2e} items and generate at least {min_e2e}. Outputting more makes the response invalid.
- "edge_cases" array: at most {max_edge} items and generate at least {min_edge}. Outputting more makes the response invalid.
- "business_tests" array: at most {max_business} items. Outputting more makes the response invalid.

E2E TEST RULES:
Generate end-to-end flows that chain UI actions to API calls to database state assertions.
Cross-feature premium mode is enabled only for the curated journey candidates below.
Generate at most {max_cross_feature_e2e} cross-feature e2e_tests from those candidates. The remaining e2e_tests must stay inside the current feature boundary.
If the curated journey list is empty, generate zero cross-feature tests.
Include Chaos scenarios only when a specific downstream service such as PostgreSQL, AWS S3, Redis, Twilio, a queue, storage service, or notification provider is named in the EVIDENCE POOL. If no such service is named, generate zero Chaos tests; this is correct and expected.
Chaos scenario types — adapt each to the actual services named in the EVIDENCE POOL:
  Type A — Partial write: the primary API call succeeds but a downstream write fails silently.
  Type B — Concurrent mutation: two actors modify the same resource simultaneously; one must receive a deterministic conflict response.
  Type C — Idempotent retry: client retries a timed-out call the server already processed; no duplicate state is created.
  Type D — Cascade failure: a named dependency goes down; the feature fails gracefully with a specific error code.

EDGE CASE RULES:
Generate {corruption_edge_target} edge_cases as state-corruption scenarios derived from actual mutating endpoints in the API DICTIONARY below.
An edge case title must describe a system behavior scenario in plain language.
An edge case title that contains "API-" followed by a number makes the response invalid.
An edge case title that is a verbatim copy of an API test title makes the response invalid.

BUSINESS TEST RULES:
Generate exactly one test per distinct business rule. The total must not exceed {max_business}.
A business rule test must verify a CONSTRAINT or PERMISSION BOUNDARY — something the system actively enforces.
It answers: "What happens when a user violates a rule?"
A test whose intent describes display behavior, optional UX flow, slot update rendering, timer animation,
geographic filtering, or active-status display makes the response invalid — these are not rule enforcement.
When the evidence names a concrete dependency, include one business test proving a business rule still holds while that dependency is degraded.


API DICTIONARY ({api_count} endpoints — use only these routes):
{json.dumps(pruned_api_dictionary, indent=2)}

UI DICTIONARY ({len(pruned_ui_dictionary)} components — use only these fields):
{json.dumps(pruned_ui_dictionary, indent=2)}

CURATED CROSS-FEATURE E2E JOURNEYS (premium graph hints, use only if directly supported):
{json.dumps(cross_feature_journeys, indent=2) if cross_feature_journeys else '[]'}

EVIDENCE POOL:
BUSINESS RULES: {json.dumps(business_context, indent=2)}
REQUIREMENT EVIDENCE: {prd}
ARCHITECTURE EVIDENCE: {hld}
RAG EVIDENCE: {rag_evidence}

OUTPUT SCHEMA:
The JSON object has exactly three keys: "e2e_tests", "edge_cases", "business_tests".
The values below are examples — replace each one with real values from the evidence and dictionaries.

{{
  "e2e_tests": [
    {{
      "id": "E2E-1",
      "title": "Host creates event then PostgreSQL write fails on participant join — state remains consistent",
      "intent": "Verify that a failed participant join does not leave an orphaned join_request row in the database",
      "test_suite": "Chaos",
      "priority": "High",
      "confidence": 0.88,
      "preconditions": [
        "An authenticated host user exists with a confirmed upcoming event",
        "PostgreSQL is configured to fail writes to the join_requests table after the first insert"
      ],
      "ui_journey_steps": [
        "Participant navigates to the event detail screen",
        "Participant taps the Join Event button",
        "The app displays a loading spinner for 3 seconds",
        "The app shows an error toast: Unable to join event, please try again"
      ],
      "backend_assertions": [
        "POST /api/v1/events/:id/join returns 503",
        "No orphaned join_request row exists in the database for this participant and event",
        "The event participant_count field is unchanged"
      ]
    }}
  ],
  "edge_cases": [
    {{
      "id": "EDGE-1",
      "title": "Concurrent host delete and participant join on the same event",
      "intent": "Two simultaneous mutations to the same event resource must produce a deterministic non-corrupt outcome",
      "test_suite": "Chaos",
      "priority": "High",
      "confidence": 0.82,
      "expected_behavior": "One request succeeds based on which acquires the database row lock first. The other receives a 409 Conflict response. No partial state is persisted — the event is either fully deleted or the join_request is fully created, never both."
    }}
  ],
  "business_tests": [
    {{
      "id": "BUS-1",
      "title": "Non-host users cannot delete an event even when the auth service is degraded",
      "intent": "Only the event host may delete their own event, even when the auth service is returning 200 for all permission checks due to a misconfiguration.",
      "test_suite": "Chaos",
      "priority": "High",
      "confidence": 0.95,
      "steps": [
        {{ "content": "Given the auth service is returning 200 for all role checks regardless of the user's actual role", "expectedResult": "The user is still treated according to the local authorization rules." }},
        {{ "content": "When a participant user calls DELETE /api/v1/events/:id", "expectedResult": "The delete request is evaluated by the API layer." }},
        {{ "content": "Then the API layer's local role-based middleware intercepts the request before reaching the auth service", "expectedResult": "The middleware blocks the request before the external auth service is used." }},
        {{ "content": "And the response status is 403 Forbidden", "expectedResult": "The API returns 403 Forbidden." }},
        {{ "content": "And the event row in the database is unchanged", "expectedResult": "No event data is modified in the database." }}
      ],
      "expected_result": {{
        "status_code": 403,
        "db_changes": [],
        "side_effects": [],
        "negative_assertions": [
          "The event is not deleted from the database",
          "No audit log entry records the unauthorized deletion as successful"
        ]
      }}
    }}
  ]
}}""".strip()

def build_e2e_fallback_prompt(
    context: dict,
    api_dictionary: list,
    ui_dictionary: list,
    rag_context: dict
) -> str:
    prd = context.get("summaries", {}).get("prd") or ""
    hld = context.get("summaries", {}).get("hld") or ""
    rag_evidence = build_rag_evidence_block(rag_context)
    
    max_e2e = min(max(math.ceil(len(api_dictionary) / 3), 6), 12)
    min_e2e = min(max_e2e, max(5, math.ceil(max_e2e * 0.5)))
    
    cross_feature_journeys = context.get("crossFeatureJourneys") or []
    cross_feature_budget_percent = float(context.get("generationHints", {}).get("crossFeatureBudgetPercent") or 20)
    max_cross_feature_e2e = max(1, math.floor(max_e2e * (max(0.0, min(100.0, cross_feature_budget_percent)) / 100.0))) if cross_feature_journeys else 0
    version_transition_block = build_version_transition_block(context)
    
    return f"""{output_contract_header('Generate focused E2E flow test cases')}

FEATURE SCOPE:
You are generating tests ONLY for this feature: "{context.get("featureName", "Unnamed Feature")}".
Feature goal: "{context.get("featureDescription") or 'See the evidence summary in the evidence pool.'}".
Every test must be directly relevant to this feature. Tests for other features make the response invalid.
{version_transition_block}

You are the focused E2E fallback agent in a QA pipeline.
The previous combined E2E/Edge/Business pass produced too few end-to-end flows.
Generate only e2e_tests. Do not generate API-only tests, UI-only validations, edge_cases, or business_tests.

FIELD VALUE RULES - violations make the entire response invalid:
- {enum_constraint('test_suite', ['Smoke', 'Regression', 'Chaos'])}
- {enum_constraint('priority', ['High', 'Medium', 'Low'])}
- Every test must reference at least one route from API DICTIONARY and at least one field or screen from UI DICTIONARY when UI evidence exists.
- Every array field must contain at least one item.
- Generate at most {max_cross_feature_e2e} cross-feature tests, and only from the curated journey list below.
- Include Chaos scenarios only when a specific downstream service such as PostgreSQL, AWS S3, Redis, Twilio, a queue, storage service, or notification provider is named in the EVIDENCE POOL. If no such service is named, generate zero Chaos tests; this is correct and expected.

OUTPUT TARGET:
- Generate at least {min_e2e} e2e_tests when the dictionaries contain enough routes.
- Output at most {max_e2e} e2e_tests. Outputting more makes the response invalid.
- Prefer distinct user journeys over many variants of the same journey.

API DICTIONARY ({len(api_dictionary)} endpoints - use only these routes):
{json.dumps(api_dictionary, indent=2)}

UI DICTIONARY ({len(ui_dictionary)} components - use only these fields or screens):
{json.dumps(ui_dictionary, indent=2)}

CURATED CROSS-FEATURE E2E JOURNEYS (premium graph hints, optional and capped):
{json.dumps(cross_feature_journeys, indent=2) if cross_feature_journeys else '[]'}

EVIDENCE POOL:
FEATURE NAME: {context.get("featureName", "Unnamed Feature")}
REQUIREMENT EVIDENCE: {prd}
ARCHITECTURE EVIDENCE: {hld}
RAG EVIDENCE: {rag_evidence}

OUTPUT SCHEMA:
The JSON object has exactly one key: "e2e_tests".
The values below are examples - replace each one with real values from the evidence and dictionaries.

{{
  "e2e_tests": [
    {{
      "id": "E2E-1",
      "title": "User completes the primary feature flow from form input to persisted backend state",
      "intent": "Verify the main user journey succeeds across UI, API, and database state",
      "test_suite": "Smoke",
      "priority": "High",
      "confidence": 0.90,
      "preconditions": [
        "An authenticated user is available",
        "Required feature data exists"
      ],
      "ui_journey_steps": [
        "User opens the relevant feature screen",
        "User fills the required fields",
        "User submits the form"
      ],
      "backend_assertions": [
        "The referenced API route returns a 2xx response",
        "The expected persisted state is created or updated"
      ]
    }}
  ]
}}""".strip()

def build_business_test_prompt(context: dict) -> str:
    prd_text = context.get("summaries", {}).get("prd") or ""
    business_rules = context.get("businessContext", {}).get("prd", {}).get("requirements") or []
    if not isinstance(business_rules, list):
        business_rules = []
        
    max_tests = len(business_rules) if business_rules else 10
    count_instruction = f"The requirement evidence contains {len(business_rules)} distinct rules. Generate exactly {len(business_rules)} tests — one per rule." if business_rules else "Count the distinct rules in the requirement evidence below. Generate exactly one test per rule. Do not group rules together."

    return f"""{output_contract_header('Generate one business rule test per requirement rule')}

You are a Senior QA Engineer generating business rule test cases.
{count_instruction}

FIELD VALUE RULES — violations make the entire response invalid:
- {enum_constraint('test_suite', ['Smoke', 'Regression', 'Chaos'])}
- {enum_constraint('priority', ['High', 'Medium', 'Low'])}
- The "expected_result" field must be a JSON object with exactly four keys: "status_code" (a number), "db_changes" (an array of strings), "side_effects" (an array of strings), "negative_assertions" (an array of strings). A plain string value makes the response invalid.
- The "intent" field must closely paraphrase the specific rule being tested, but must not begin with any document/source attribution such as a filename, document type, ticket, specification, "according to the document", or "the requirements state". Put source attribution in lineage metadata, not testcase prose. A generic or vague intent makes the response invalid.
- The "steps" array must contain at least 3 items following Given / When / Then format.
- The "steps" array must use objects with "content" and a concise one-line "expectedResult" for every step that can show an observable outcome. Keep the top-level "expected_result" as the whole-test outcome only.

OUTPUT CEILING: Output at most {max_tests} tests. Generating a test for a topic not stated in the requirement evidence below also makes the response invalid.

BUSINESS CONTEXT:
{json.dumps(context.get("businessContext") or {}, indent=2)}

REQUIREMENT EVIDENCE (authoritative — test only rules stated here):
{prd_text}

OUTPUT SCHEMA:
The JSON object has exactly one key: "business_tests".
The values below are examples — replace each one with a real value from the requirement evidence above.

{{
  "business_tests": [
    {{
      "id": "BUS-1",
      "title": "Only the event host can delete their own event",
      "intent": "Event deletion is restricted to the host user who created the event.",
      "test_suite": "Regression",
      "priority": "High",
      "confidence": 0.95,
      "steps": [
        {{ "content": "Given an authenticated participant user and an existing event created by a different host", "expectedResult": "The user is authenticated and the event exists." }},
        {{ "content": "When DELETE /api/v1/events/:id is called by the participant", "expectedResult": "The delete request is rejected with authorization failure." }},
        {{ "content": "Then the response status is 403 and the event record is unchanged in the database", "expectedResult": "The API returns 403 Forbidden and the database remains unchanged." }}
      ],
      "expected_result": {{
        "status_code": 403,
        "db_changes": [],
        "side_effects": [],
        "negative_assertions": [
          "The event is not deleted from the database",
          "No cascade delete is triggered on related participant or join_request records"
        ]
      }}
    }}
  ]
}}""".strip()

def build_repair_prompt(params: dict) -> str:
    unified_context = params.get("unifiedContext") or {}
    rag_context = params.get("ragContext") or {}
    rag_validation = params.get("ragValidation") or {}
    
    prd = unified_context.get("summaries", {}).get("prd") or ""
    hld = unified_context.get("summaries", {}).get("hld") or ""
    lld = unified_context.get("summaries", {}).get("lld") or ""
    figma_block = build_compact_figma_prompt_block(unified_context.get("summaries", {}).get("figma") or {})
    rag_evidence = build_rag_evidence_block(rag_context)
    requirements_block = build_requirements_prompt_block(unified_context)
    technical_context = unified_context.get("technicalContext") or {}
    already_covered = unified_context.get("summaries", {}).get("alreadyCovered") or ""
    version_transition_block = build_version_transition_block(unified_context)
    
    covered_str = f"PROJECT INHERITED COVERAGE (Already tested in sibling features - DO NOT DUPLICATE THESE):\n{already_covered}\n" if already_covered else ""
    
    api_forbidden_notice = '\nSTRICT RULE: No API specification was provided (hasApiEvidence=false). You are FORBIDDEN from adding any new tests to the "api_tests_delta" bucket. Focus entirely on UI Validations, E2E, Edge Cases, and Business rules.' if unified_context.get("flags", {}).get("hasApiEvidence") is False else ""

    return f"""{output_contract_header('Generate a minimal delta patch for the existing test suite')}

You are the Semantic Repair Agent in a QA pipeline.
Your job is to output the smallest possible patch that fixes the listed coverage gaps.

{covered_str}{version_transition_block}
SCOPE RULES:
Output only what is needed to fix the listed gaps. Adding tests beyond the listed gaps makes the response invalid.
Removing tests not mentioned in the gaps also makes the response invalid.

REMOVAL RULES:
To remove a test, use its "_hash" value — a 12-character hex string. Copy it exactly character for character.
If the hash is not available, provide both "title" and "intent" as a pair. Providing only "title" without "intent" makes the removal entry invalid.

FIELD VALUE RULES for all new tests — violations make the response invalid:
- {enum_constraint('test_suite', ['Smoke', 'Regression', 'Edge', 'Chaos'])}
- {enum_constraint('priority', ['High', 'Medium', 'Low'])}
- {enum_constraint('method', ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])}
- The "expected_result" in api_tests_delta items must be a JSON object, not a plain string.
- New tests must reference endpoints or fields that exist in the EVIDENCE POOL below. Inventing an endpoint not found in the evidence makes the response invalid.{api_forbidden_notice}

EVIDENCE POOL (source for all new tests):
REQUIREMENT EVIDENCE: {prd}
ARCHITECTURE EVIDENCE: {hld}
DESIGN EVIDENCE: {lld}
FIGMA: {figma_block}
TECHNICAL CONTEXT: {json.dumps(technical_context, indent=2)}
REQUIREMENTS: {requirements_block}
RAG EVIDENCE: {rag_evidence}

COVERAGE GAPS TO FIX:
{json.dumps(rag_validation, indent=2)}

OUTPUT SCHEMA:
The JSON object has exactly five keys as shown. Each delta bucket has exactly three sub-keys.
If a bucket needs no changes, its three sub-arrays must all be empty arrays.
The values below are examples — replace each one with real values from the evidence and gaps above.

{{
  "api_tests_delta": {{
    "tests_to_remove_by_hash": ["a1b2c3d4e5f6"],
    "tests_to_remove": [
      {{"title": "Exact title of the test to remove", "intent": "Exact intent of the test to remove"}}
    ],
    "tests_to_add": [
      {{
        "id": "API-NEW-1",
        "title": "Non-host receives 403 when attempting to update event details",
        "intent": "RAG gap: the authorization check for the event update endpoint was not covered by any existing test",
        "test_suite": "Regression",
        "priority": "High",
        "confidence": 0.90,
        "module": "Events",
        "method": "PUT",
        "endpoint": "/api/v1/events/:id",
        "description": "A participant user calls PUT on an event they do not own and receives 403 Forbidden",
        "steps": [
          {{ "content": "Given an authenticated participant user and an event created by a different host", "expectedResult": "The user is authenticated and the event exists." }},
          {{ "content": "When PUT /api/v1/events/:id is called with a valid payload", "expectedResult": "The request is rejected with authorization failure." }},
          {{ "content": "Then the response status is 403 and the event data in the database is unchanged", "expectedResult": "The API returns 403 Forbidden and event record remains unchanged." }}
        ],
        "expected_result": {{
          "status_code": 403,
          "db_changes": [],
          "side_effects": [],
          "negative_assertions": ["The event record is not modified in the database"]
        }}
      }}
    ]
  }},
  "ui_validations_delta": {{
    "tests_to_remove_by_hash": [],
    "tests_to_remove": [],
    "tests_to_add": []
  }},
  "e2e_tests_delta": {{
    "tests_to_remove_by_hash": [],
    "tests_to_remove": [],
    "tests_to_add": []
  }},
  "edge_cases_delta": {{
    "tests_to_remove_by_hash": [],
    "tests_to_remove": [],
    "tests_to_add": []
  }},
  "business_tests_delta": {{
    "tests_to_remove_by_hash": [],
    "tests_to_remove": [],
    "tests_to_add": []
  }}
}}""".strip()

def build_individual_test_repair_prompt(
    context: dict,
    original_test: dict,
    repair_instructions: str
) -> str:
    return f"""{output_contract_header('Repair a specific test case based on delta instructions')}

You are the Test Repair Agent. 
Your goal is to take an existing test case and modify it according to specific instructions.
Maintain the original structure and style of the test, but apply the changes requested.

ORIGINAL TEST:
{json.dumps(original_test, indent=2)}

REPAIR INSTRUCTIONS:
{repair_instructions}

CONTEXT:
Feature: {context.get("featureName")}
Description: {context.get("featureDescription")}

OUTPUT SCHEMA:
The output must be the repaired test case object in the exact same schema as the input.""".strip()

def build_flow_discovery_prompt(
    feature_name: str,
    feature_description: str,
    ecosystem: str,
    siblings: list
) -> str:
    siblings_str = "\n".join(f"- {s.get('name')}: {s.get('abstract')}" for s in siblings) if siblings else 'No existing sibling features found.'
    return f"""{output_contract_header('Discover Architectural Flow (Project Mind Map)')}

You are the Principal Solution Architect. Your task is to build a "Mental Model" of how a new feature integrates into the existing project ecosystem.

PROJECT ECOSYSTEM:
{ecosystem or 'Unknown system architecture.'}

SIBLING FEATURES (Context):
{siblings_str}

NEW FEATURE:
Name: {feature_name}
Description: {feature_description}

TASK:
1. Identify the "Relationship" between this new feature and the existing ones.
2. Describe the "Data Flow" (e.g., "User authenticates in Login feature, receiving a token which is then used by this feature to access API X").
3. Create a concise "Architectural Mind Map" (3-4 sentences) that explains the "Big Picture" of this feature within the project.

OUTPUT:
Provide a structured summary of the Architectural Flow. Be technical, concise, and focused on connectivity.""".strip()
