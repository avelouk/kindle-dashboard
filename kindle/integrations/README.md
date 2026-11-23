# integrations

Your button scripts go here. One script per device or service: it does one thing, exits 0 on success, and has timeouts on everything. Credentials go in a gitignored `.env` file next to the script.

Wire a script to a button in `kindle/config.json`:

```json
{"id": "my_button", "label": "Do the thing", "command": ["{python}", "integrations/my_script.py", "arg"]}
```

See "Adding a button" in `CLAUDE.md`.
