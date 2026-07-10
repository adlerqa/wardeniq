# app/testgen/lineage.py
import hashlib
import re

LINEAGE_SIMILARITY_THRESHOLD = 0.45
LINEAGE_AMBIGUITY_MARGIN = 0.1
LINEAGE_HIGH_CONFIDENCE = 0.75

LINEAGE_STOPWORDS = {
    'a', 'an', 'the', 'is', 'are', 'to', 'of', 'for', 'with', 'and', 'or', 'test', 'tests',
    'should', 'when', 'then', 'given', 'verify', 'verifies', 'check', 'checks', 'that', 'this',
    'user', 'users', 'system', 'case', 'ensure', 'ensures', 'it', 'in', 'on', 'be', 'as', 'via',
    'api', 'endpoint', 'request', 'requests', 'response', 'responses', 'send', 'sends', 'sent',
    'return', 'returns', 'returned', 'status', 'code', 'call', 'calls', 'data', 'payload',
    'body', 'header', 'headers', 'value', 'values', 'field', 'fields', 'input', 'inputs',
    'expect', 'expected', 'expects', 'assert', 'asserts', 'validate', 'validates', 'validation',
    'correct', 'correctly', 'successfully', 'error', 'message', 'using', 'from', 'attempt', 'attempts',
}

ROUTE_FIELDS = ['backend_assertions', 'steps', 'expected_behavior', 'intent', 'preconditions', 'expected_result', 'ui_journey_steps']
ROUTE_PATTERN = re.compile(r'\b(?:GET|POST|PUT|PATCH|DELETE)\s+(\/[\w/{}:.-]*)', re.IGNORECASE)

def stringify_step(step) -> str:
    if step is None:
        return ''
    if isinstance(step, (str, int, float, bool)):
        return str(step).strip().lower()
        
    if isinstance(step, list):
        return " ".join(stringify_step(item) for item in step if item).strip()
        
    if isinstance(step, dict):
        content = str(step.get("content") or step.get("step") or step.get("description") or step.get("title") or "").strip().lower()
        expected = str(step.get("expectedResult") or step.get("expected_result") or step.get("expected_behavior") or "").strip().lower()
        if content and expected:
            return f"{content} {expected}".strip()
        if content:
            return content
        if expected:
            return expected
            
        return " ".join(stringify_step(value) for value in step.values() if value).strip()
        
    return str(step).strip().lower()

def generate_test_identity_hash(test: dict, ignore_steps: bool = False) -> str:
    components = []
    category = str(test.get("category") or '').lower()
    
    # Check if it has API traits
    is_api = (category == 'api_tests' or test.get("method") or test.get("endpoint"))
    
    # Check UI traits
    is_ui = (category == 'ui_validations' or test.get("field") or test.get("validation_type") or test.get("type") or test.get("screen"))
    
    if is_api:
        method = str(test.get("method") or '').upper().strip()
        endpoint = str(test.get("endpoint") or '').lower().strip().rstrip('/')
        endpoint = re.sub(r'/[0-9a-f-]{36}', '/{id}', endpoint)
        endpoint = re.sub(r'/\d+', '/{id}', endpoint)
        
        expected_result = test.get("expected_result") or {}
        status_code = ""
        if isinstance(expected_result, dict):
            status_code = str(expected_result.get("status_code") or test.get("status_code") or '').strip()
        else:
            status_code = str(test.get("status_code") or '').strip()
            
        intent = str(test.get("intent") or test.get("title") or '').lower()
        intent = re.sub(r'[^a-z0-9]', '', intent)
        
        steps = ''
        if not ignore_steps:
            test_steps = test.get("steps")
            if isinstance(test_steps, list):
                steps = "|".join(sorted(stringify_step(s) for s in test_steps))
            else:
                steps = str(test_steps or '').lower().strip()
                
        components = [method, endpoint, status_code, intent, steps]
        
    elif is_ui:
        field = str(test.get("field") or '').lower().strip()
        v_type = str(test.get("validation_type") or test.get("type") or '').lower().strip()
        screen = str(test.get("screen") or '').lower().strip()
        
        if field or v_type or screen:
            components = [field, v_type, screen]
        else:
            intent = str(test.get("intent") or test.get("title") or test.get("description") or '').lower()
            intent = re.sub(r'[^a-z0-9]', '', intent)
            
            endpoint = str(test.get("endpoint") or '').lower().strip().rstrip('/')
            endpoint = re.sub(r'/[0-9a-f-]{36}', '/{id}', endpoint)
            endpoint = re.sub(r'/\d+', '/{id}', endpoint)
            
            steps = ''
            if not ignore_steps:
                test_steps = test.get("steps")
                if isinstance(test_steps, list):
                    steps = "|".join(sorted(stringify_step(s) for s in test_steps))
                else:
                    steps = str(test_steps or '').lower().strip()
            components = [intent, endpoint, steps]
    else:
        intent = str(test.get("intent") or test.get("title") or '').lower().strip()
        steps = ''
        if not ignore_steps:
            test_steps = test.get("steps")
            if isinstance(test_steps, list):
                steps = "|".join(stringify_step(s) for s in test_steps)
            else:
                steps = str(test_steps or '').lower().strip()
        components = [intent, steps]
        
    raw_string = "::".join(v for v in components if v is not None)
    return hashlib.md5(raw_string.encode('utf-8')).hexdigest()

def generate_test_slug(test: dict) -> str:
    category = str(test.get("category") or '').lower()
    intent_slug = str(test.get("intent") or test.get("title") or '').lower()
    intent_slug = re.sub(r'[^a-z0-9]', '', intent_slug)[:50]
    
    is_api = (category == 'api_tests' or test.get("method") or test.get("endpoint"))
    is_ui = (category == 'ui_validations' or test.get("field") or test.get("validation_type") or test.get("type") or test.get("screen"))
    
    if is_api:
        method = str(test.get("method") or '').upper().strip()
        endpoint = str(test.get("endpoint") or '').lower().strip().rstrip('/')
        endpoint = re.sub(r'/[0-9a-f-]{36}', '/{id}', endpoint)
        endpoint = re.sub(r'/\d+', '/{id}', endpoint)
        return f"api|{method}|{endpoint}|{intent_slug}"
        
    if is_ui:
        field = str(test.get("field") or '').lower().strip()
        v_type = str(test.get("validation_type") or test.get("type") or '').lower().strip()
        screen = str(test.get("screen") or '').lower().strip()
        if field or v_type or screen:
            return f"ui|{field}|{v_type}|{screen}|{intent_slug}"
            
        endpoint = str(test.get("endpoint") or '').lower().strip().rstrip('/')
        endpoint = re.sub(r'/[0-9a-f-]{36}', '/{id}', endpoint)
        endpoint = re.sub(r'/\d+', '/{id}', endpoint)
        return f"ui|{intent_slug}|{endpoint}"
        
    return f"gen|{category}|{intent_slug}"

def normalize_endpoint(endpoint) -> str:
    endpoint = str(endpoint or '').lower().strip().rstrip('/')
    endpoint = re.sub(r'/[0-9a-f-]{36}', '/{id}', endpoint)
    endpoint = re.sub(r'/\d+', '/{id}', endpoint)
    return endpoint

def exact_status_code(test: dict) -> str:
    expected_result = test.get("expected_result") or {}
    sc = ""
    if isinstance(expected_result, dict):
        sc = str(expected_result.get("status_code") or test.get("status_code") or '').strip()
    else:
        sc = str(test.get("status_code") or '').strip()
        
    m = re.match(r'[1-5]\d{2}', sc)
    return m.group(0) if m else ''

def is_strong_lineage(test: dict) -> bool:
    category = str(test.get("category") or '').lower()
    if category == 'api_tests' or test.get("method") or test.get("endpoint"):
        return True
    if (category == 'ui_validations' or test.get("field") or test.get("validation_type") or test.get("type") or test.get("screen")) and (
        test.get("field") or test.get("validation_type") or test.get("type") or test.get("screen")
    ):
        return True
    return False

def generate_lineage_key(test: dict) -> str:
    category = str(test.get("category") or '').lower()
    
    if category == 'api_tests' or test.get("method") or test.get("endpoint"):
        method = str(test.get("method") or '').upper().strip()
        return '|'.join(['api', method, normalize_endpoint(test.get("endpoint")), exact_status_code(test)])
        
    if category == 'ui_validations' or test.get("field") or test.get("validation_type") or test.get("type") or test.get("screen"):
        field = str(test.get("field") or '').lower().strip()
        v_type = str(test.get("validation_type") or test.get("type") or '').lower().strip()
        screen = str(test.get("screen") or '').lower().strip()
        if field or v_type or screen:
            return '|'.join(['ui', screen, field, v_type])
        return '|'.join(['ui', normalize_endpoint(test.get("endpoint"))])
        
    return '|'.join(['gen', category])

def scenario_text(test: dict) -> str:
    parts = [str(test.get("title") or test.get("intent") or '')]
    test_steps = test.get("steps")
    if isinstance(test_steps, list):
        parts.append(" ".join(stringify_step(s) for s in test_steps))
    else:
        parts.append(str(test_steps or ''))
    return " ".join(parts).lower()

def keyword_4xx_kind(text: str) -> str:
    if re.search(r'\b(rate limit|rate-limit|throttl)', text):
        return 'rate_limit'
    if re.search(r'\b(unauthorized|unauthenticated|no token|without (a )?token|expired (token|session)|not logged in)\b', text):
        return 'unauthorized'
    if re.search(r'\b(forbidden|permission|access denied|insufficient (role|privilege|permission)s?)\b', text):
        return 'forbidden'
    if re.search(r'\b(not found|nonexistent|non-existent|unknown (id|resource)|deleted (id|resource))\b', text):
        return 'not_found'
    if re.search(r'\b(duplicate|already exists?|already registered|conflict)\b', text):
        return 'conflict'
    if re.search(r'\b(missing|required|empty|blank|omitted|without|absent|null)\b', text):
        return 'missing_field'
    if re.search(r'\b(boundary|max(imum)?|min(imum)?|exceed(s|ed)?|too (long|short|large|small)|length limit|overflow)\b', text):
        return 'boundary'
    if re.search(r'\b(invalid|malformed|incorrect|wrong|unsupported|bad)\b', text):
        return 'invalid_input'
    return ''

def derive_scenario_kind(test: dict) -> str:
    sc = exact_status_code(test)
    text = scenario_text(test)
    if sc:
        n = int(sc)
        if 200 <= n < 300:
            return 'happy_path'
        if n >= 500:
            return 'server_error'
        if n == 401:
            return 'unauthorized'
        if n == 403:
            return 'forbidden'
        if n == 404:
            return 'not_found'
        if n == 409:
            return 'conflict'
        if n == 429:
            return 'rate_limit'
        if n == 400 or n == 422:
            return keyword_4xx_kind(text)
        return ''
    return keyword_4xx_kind(text)

def scenario_kinds_incompatible(a: str, b: str) -> bool:
    return a != '' and b != '' and a != b

def flatten_to_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(flatten_to_text(item) for item in value if item)
    if isinstance(value, dict):
        return " ".join(flatten_to_text(val) for val in value.values() if val)
    return str(value)

def referenced_routes(test: dict) -> set[str]:
    text = " ".join(flatten_to_text(test.get(k)) for k in ROUTE_FIELDS if test.get(k))
    out = set()
    for m in ROUTE_PATTERN.finditer(text):
        raw = str(m.group(1))
        if not raw or raw == '/':
            continue
        out.add(normalize_endpoint(raw))
    return out

def routes_incompatible(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    for r in a:
        if r in b:
            return False
    return True

def lineage_token_set(test: dict) -> set[str]:
    parts = [str(test.get("title") or test.get("intent") or '')]
    test_steps = test.get("steps")
    if isinstance(test_steps, list):
        parts.append(" ".join(stringify_step(s) for s in test_steps))
    else:
        parts.append(str(test_steps or ''))
        
    raw_str = " ".join(parts).lower()
    tokens = [t for t in re.split(r'[^a-z0-9]+', raw_str) if t and t not in LINEAGE_STOPWORDS]
    return set(tokens)

def token_set_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter / union) if union > 0 else 0.0
