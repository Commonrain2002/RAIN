import json
import os

import requests

apiKey = os.environ.get("OPENROUTER_API_KEY")
if not apiKey:
    raise SystemExit("OPENROUTER_API_KEY environment variable is not set.")

response = requests.get(
    url="https://openrouter.ai/api/v1/key",
    headers={
        "Authorization": f"Bearer {apiKey}",
    },
)

print(json.dumps(response.json(), indent=2))
