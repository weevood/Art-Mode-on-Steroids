# Art-Mode-on-Steroids
ART Runner is a lightweight Python-based tool for unlocking the Art Mode on Samsung The Frame TVs. Use the full power of the Samsung API to automate image downloads, dynamically manage your collections, and customize the display beyond the limitations of the SmartThings app.

It provides:
- a one-shot execution mode
- a continuous cron-like execution mode
- centralized configuration
- structured logging

---

## Repository Structure

```
.
├── art.py           # One-shot execution
├── art_cron.py      # Periodic execution loop
├── config.py        # Centralized configuration
├── _art_upload.py   # Upload logic (external)
├── _art_set.py      # Set logic (external)
└── README.md
```

---

## Configuration

All configurable parameters are defined in `config.py`.

```python
INTERVAL = 60  # seconds
```

This allows you to extend configuration without touching business logic by :
- tune execution frequency

---

## Usage

### One-shot execution

Runs both scripts once:

```bash
python3 art.py
```

---

### Continuous (cron-like) execution

Runs the scripts repeatedly with a fixed interval:

```bash
python3 art_cron.py
```

---

## Logging

- `art.py` uses `DEBUG` level
- `art_cron.py` uses `INFO` level

Logs are printed to stdout and can easily be redirected to a file or logging system.