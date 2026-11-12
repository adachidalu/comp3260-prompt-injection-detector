# Favour — Session Report 1 (Simple Explanation)

**Project:** Detecting Indirect Prompt Injection in University Email Assistants  
**Workstream:** Detection rules for disguised attacks  
**Lesson:** Hidden HTML text

## What was done

Created `detector.py`, a Python starter that finds text in HTML elements hidden using a few common mechanisms, checks for suspicious instructions, and returns `pass` or `review` with evidence. Created four automated tests and a README.

## Why this matters

An email can show an ordinary registration question while carrying a hidden line that tries to make the AI give an incorrect answer. Our detector helps a staff reviewer notice such content before drafting.

## Easy explanation of the program

`HTMLParser` reads the email's HTML structure. The code keeps track of whether text is inside a hidden part. Regular expressions search that hidden text for warning patterns. The result includes the suspicious wording so a reviewer can check it.

## What has been proven

The supplied examples run with Python's standard library. These are small known-example checks, **not** accuracy measurements on the project's 650-email held-out evaluation set.

## What is not finished

The code does not implement all four disguises, a comprehensive HTML parser, plain-text detection, the `block` decision, email intake, AI drafting, or authorization checks. Attackers can evade simple rules.

## What Favour should learn next

Run the code locally, explain the hidden HTML example, add another test, and then implement Base64 decoding carefully with limits to avoid resource-exhaustion risks.
