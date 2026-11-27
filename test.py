
from database.db_manager import (
    initialize_db,
    log_verdict,
    log_action_request,
    log_test_result,
    get_verdicts,
    get_action_requests,
    get_test_results,
    get_database_summary
)

initialize_db()

# Test 1: Store a verdict
log_verdict(
    email_id="EMAIL001",
    verdict="BLOCK",
    evidence=["Suspicious instruction detected"],
    reason="Potential prompt injection"
)

# Test 2: Store a denied action
log_action_request(
    action_type="read_student_record",
    target="STUDENT_RECORD_001",
    approved=False,
    reason="Unauthorized access"
)

# Test 3: Store a test result
log_test_result(
    test_name="Output Validator Test",
    status="PASS",
    details={"approved": True}
)

# Display stored records
print("VERDICTS:")
print(get_verdicts())

print("\nACTION REQUESTS:")
print(get_action_requests())

print("\nTEST RESULTS:")
print(get_test_results())

print("\nDATABASE SUMMARY:")
print(get_database_summary())
