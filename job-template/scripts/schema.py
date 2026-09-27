"""Small strict validator for the shipped JSON Schema subset, without dependencies."""
import re

def validate_schema(value, schema, path='$', coerce=False):
    kind = schema.get('type')
    if coerce and kind in ('number', 'integer') and isinstance(value, str):
        try: value = float(value) if kind == 'number' else int(value)
        except ValueError: pass
    valid = {'object': lambda: isinstance(value, dict), 'array': lambda: isinstance(value, list),
             'string': lambda: isinstance(value, str), 'number': lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
             'integer': lambda: isinstance(value, int) and not isinstance(value, bool), 'boolean': lambda: isinstance(value, bool)}
    if kind in valid and not valid[kind](): raise ValueError(f'{path}: expected {kind}')
    if 'enum' in schema and value not in schema['enum']: raise ValueError(f'{path}: unknown value {value!r}; choose {schema["enum"]}')
    if kind == 'object':
        properties = schema.get('properties', {})
        for key in schema.get('required', []):
            if key not in value: raise ValueError(f'{path}: missing {key}')
        if schema.get('additionalProperties') is False:
            for key in value:
                if key not in properties: raise ValueError(f'{path}: unknown property {key}')
        return {key: validate_schema(item, properties.get(key, {}), path + '.' + key, coerce) for key, item in value.items()}
    if kind == 'array':
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', 100000): raise ValueError(f'{path}: invalid item count')
        return [validate_schema(item, schema.get('items', {}), f'{path}[{i}]', coerce) for i, item in enumerate(value)]
    if kind == 'string':
        if len(value) > schema.get('maxLength', 100000): raise ValueError(f'{path}: too long')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'], value): raise ValueError(f'{path}: invalid format {value!r}')
    if kind in ('number', 'integer'):
        import math
        if not math.isfinite(value) or not schema.get('minimum', -float('inf')) <= value <= schema.get('maximum', float('inf')): raise ValueError(f'{path}: out of range')
    return value
