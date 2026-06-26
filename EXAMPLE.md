# Example Feature: Enhanced Review Summary

## Overview

This example markdown file demonstrates how PR branch comparison works.

## What Changed

- Added structured summary output to the review agent
- Improved confidence scoring for security findings
- New `review_summary.json` output format

## Example Output

```json
{
  "pr_number": 42,
  "repo": "org/repo",
  "findings": [
    {
      "category": "security",
      "severity": "high",
      "file": "backend/auth.py",
      "line": 87,
      "message": "Hardcoded secret detected"
    }
  ],
  "confidence": 0.91,
  "reviewed_at": "2026-06-26T10:00:00Z"
}
```

## Notes

- This file was created on branch `tp` to demonstrate branch diffing
- Compare this against `main` to see what was added
