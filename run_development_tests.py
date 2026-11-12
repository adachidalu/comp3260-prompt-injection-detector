from pathlib import Path

from detector import inspect_hidden_html


examples = [
    "genuine.html",
    "hidden_attack.html",
    "hidden_benign.html",
]

for filename in examples:

    # Find the HTML file
    path = Path("development_examples") / filename

    # Read the contents of the HTML file
    html_body = path.read_text(encoding="utf-8")

    # Send the email through our detector
    result = inspect_hidden_html(
        subject="Registration",
        html_body=html_body
    )

    # Show the result
    print("=" * 50)
    print("FILE:", filename)
    print("VERDICT:", result["verdict"])
    print("HIDDEN TEXT:", result["hidden_fragments"])
    print("EVIDENCE:", result["evidence"])

print("=" * 50)