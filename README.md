# Datter

**Datter: Data Analysis Platform**

Datter data platform hopes to offer an intuitive easy to use UI where analytics and visualizations can be generated without the need for programming. All activity on the platform will be completed by button clicking and and click and drag actions in a dashboard like web pages based graphical interface.

## How to run locally

**IMPORTANT: GENERATE A SECRET TOKEN FOR AUTHENTICATION**

1. Copy `example.env` to `.env`
2. Open `.env` and insert your string of 32 random bytes encoded as 64 hex characters
3. Save the file

**Requirements** Python 3.10

1. Create a Python 3.10 virtual environment and activate it
2. `pip install -r requirements.txt`
3. `python server.py`
4. Voila! Open http://localhost:8080 in your preferred web browser.
