import requests
import typing
import json

def get_anki_connect_request(action, **params) -> str:
    request: dict = {
        "action": action,
        "version": 6,
        "params": params,
    }
    return json.dumps(request)


def invoke_anki_connect(
        url: str,
        action: str,
        **params
) -> typing.Any:
    response: requests.Response = requests.post(
        url,
        get_anki_connect_request(action, **params)
    )
    try:
        response.raise_for_status()
    except Exception as e:
        print("Error getting response from AnkiConnect: " + str(e))

    response_table = json.loads(response.text)
    if len(response_table) != 2:
        raise Exception("response has an unexpected number of fields")
    if "error" not in response_table:
        raise Exception("response is missing required error field")
    if "result" not in response_table:
        raise Exception("response is missing required result field")
    if response_table["error"] is not None:
        raise Exception(response_table["error"])
    return response_table["result"]
