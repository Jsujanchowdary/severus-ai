import json
import os

import requests

# Configuration with environment variable overrides
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000/api/dashboards/db")
AUTH_USER = os.getenv("GRAFANA_USER", "admin")
AUTH_PASS = os.getenv("GRAFANA_PASS", "admin123")
AUTH = (AUTH_USER, AUTH_PASS)

# Local path relative to the script
DASHBOARD_FILE = os.getenv("DASHBOARD_FILE", "config/grafana-dashboard-application.json")

def import_dashboard():
    print(f"🔍 Attempting to import dashboard from {DASHBOARD_FILE} to {GRAFANA_URL}...")

    if not os.path.exists(DASHBOARD_FILE):
        print(f"❌ Dashboard file not found: {DASHBOARD_FILE}")
        return

    with open(DASHBOARD_FILE, 'r') as f:
        try:
            dashboard_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON: {e}")
            return

    # Ensure overwrite is set
    dashboard_data['overwrite'] = True

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    try:
        response = requests.post(GRAFANA_URL, auth=AUTH, json=dashboard_data, headers=headers)
        if response.status_code == 200:
            print("✅ Dashboard imported successfully!")
            print(json.dumps(response.json(), indent=2))
        else:
            print(f"❌ Failed to import dashboard. Status: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Connectivity Error: {e}")
        print("💡 Tip: If running locally, ensure you have port-forwarded Grafana: kubectl port-forward svc/kube-prometheus-stack-grafana 3000:80")

if __name__ == "__main__":
    import_dashboard()
