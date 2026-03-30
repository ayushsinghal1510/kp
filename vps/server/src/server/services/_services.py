def _parse_list(value : str) -> list : 

    if value == '*' : return ['*']

    return [x.strip() for x in value.split(',')]

def _parse_bool(value : str) -> bool : return value.lower() == 'true'