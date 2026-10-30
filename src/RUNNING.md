# Running the Itinerary Planning Agent

Open PowerShell in the `src` directory:

Activate the existing virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

If dependencies are not installed yet, install them with:

```powershell
python -m pip install -r requirements.txt
```

Start the Streamlit app:

```powershell
python -m streamlit run app.py
```

If the app is already running with an older version of the code, stop it with
`Ctrl+C`, then restart it from the repository root with:

```powershell
cd ".\src"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The app starts with the **Hello Kitty** profile. Use the **User profile** selector
at the top to switch to **Pokemon**. Each profile has separate saved hotels,
itineraries, and memory approvals under `runtime\users\<profile-id>\`.

Then open the URL shown in the terminal, usually:

```text
http://localhost:8501
```

To run the tests:

```powershell
python -m pytest tests\test_itinerary.py
```

If PowerShell prevents virtual-environment activation, run Streamlit directly:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Troubleshooting a lab session lock

If you see:

```text
RunError: Another lab session holds the lock. Close it first; see README for stale locks.
```

First close any other running copy of the Streamlit app or `agent.py`. Only
one lab session can use the shared `.lab-state` accounting files at a time.

If no other copy is running, check for a stale lock from the `src` directory:

```powershell
Test-Path .lab-state\session.lock
```

Only when no lab session is running, remove the stale lock:

```powershell
Remove-Item .lab-state\session.lock
```

Then start the app again:

```powershell
python -m streamlit run app.py
```
