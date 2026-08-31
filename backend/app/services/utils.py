def parse_returned_json(text):
    try:
        return json.loads(text)
    except JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise AiResponseError("A non-JSON response was received.")

        return json.loads(match.group(0))

