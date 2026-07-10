import sys
import os
import json

sys.path.insert(0, '/app')

from main import store, current_llm
import validator

feature_id = '6a3cd1e25a99fc841269cc87'
version_number = 1

unified_context = store.build_unified_context(feature_id, version_number)
llm = current_llm()

# Get prompt
prompt = validator.build_validator_prompt(feature_id, unified_context)

try:
    print("\nCalling LLM...")
    raw_text = llm._raw_chat(validator.SYSTEM, prompt, 8192, 0.1, 7000)
    print("\nRaw LLM output length:", len(raw_text))
    print("\nRaw LLM output start:\n", raw_text[:300])
    
    # Try parsing
    questions = validator.call_llm_json_with_repair(llm, validator.SYSTEM, prompt)
    print("\nParsed questions count:", len(questions))
    if questions:
        print("\nFirst parsed question:", json.dumps(questions[0], indent=2))
        
    # Check normalization
    print("\nRunning normalization...")
    normalized = validator.normalize_and_filter_questions(questions, version_number)
    print("\nNormalized questions count:", len(normalized))
except Exception as e:
    import traceback
    traceback.print_exc()
