#Prevent unauthorized access to mock student records and prevent external information transfers.

def authorize_action(action_request):
    #Checks whether a requested action is permitted. Returns a decision, explanation, and audit event.

    # Reject malformed requests
    if not isinstance(action_request, dict):
        action_type = "unknown"
        allowed = False
        reason = "Invalid action request."

    else:
        action_type = action_request.get("action_type", "unknown")

        if not isinstance(action_type, str):
            action_type = "unknown"

        action_type = action_type.strip().lower()

        # Rule 1: Private student records cannot be accessed
        if action_type == "read_student_record":
            allowed = False
            reason = "Unauthorized access to student records denied."

        # Rule 2: External transfers are prohibited
        elif action_type == "external_transfer":
            allowed = False
            reason = "External information transfer denied."

        # Rule 3: Mock university policies may be accessed
        elif action_type == "read_mock_policy":
            allowed = True
            reason = "Access to mock university policy permitted."

        # Rule 4: All unrecognized actions are denied
        else:
            allowed = False
            reason = "Unknown or unauthorized action denied."

    # Create an audit event for security logging
    audit_event = {
        "action_type": action_type,
        "allowed": allowed,
        "reason": reason
    }

    return {
        "allowed": allowed,
        "reason": reason,
        "action_type": action_type,
        "audit_event": audit_event
    }


