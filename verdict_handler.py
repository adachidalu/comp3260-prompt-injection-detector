
#Control whether an email is allowed to proceed, requires human review or must be blocked


def handle_verdict(verdict):
    #receives a security verdict and determines what the app is allowed to do
    verdict = str(verdict).strip().lower()

    if verdict == "pass":
        return {
            "status": "PASS",
            "allow_drafting": True,
            "message": "Email approved for drafting."
        }

    elif verdict == "review":
        return {
            "status": "REVIEW",
            "allow_drafting": False,
            "message": "Email held for human review."
        }

    elif verdict == "block":
        return {
            "status": "BLOCK",
            "allow_drafting": False,
            "message": "Email blocked due to security concerns."
        }

    else:
        #unknown verdicts should not approved automatically
        return{
            "status": "REVIEW",
            "allow_drafting": False,
            "message": "Unknown verdict. Human review required."
        }

