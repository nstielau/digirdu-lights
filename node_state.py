"""USB-base validated node identity. No generated Python, hardware imports or secrets."""
import json
import os
from hardware import S3, V2

PATH = '/node_state.json'
MAX_BYTES = 2048


def canonical_role(role):
    return {'leader': 'producer', 'follower': 'consumer'}.get(role, role)


def valid_mac(value):
    if type(value) is not str or len(value) != 17:
        return False
    try:
        parts = value.split(':')
        return len(parts) == 6 and all(len(p) == 2 for p in parts) and len(bytes.fromhex(''.join(parts))) == 6
    except ValueError:
        return False


def validate(data):
    allowed = {'schema', 'radio_role', 'radio_group', 'leader_mac'}
    if type(data) is not dict or set(data) - allowed:
        raise ValueError('Invalid node state fields')
    if type(data.get('schema')) is not int or data['schema'] != 1:
        raise ValueError('Invalid node state schema')
    if data.get('radio_role') not in ('producer', 'consumer'):
        raise ValueError('Invalid saved role')
    group = data.get('radio_group')
    if type(group) is not int or not 0 <= group <= 65535:
        raise ValueError('Invalid saved group')
    if ('leader_mac' in data and not valid_mac(data['leader_mac'])
            or data['radio_role'] == 'consumer' and not valid_mac(data.get('leader_mac'))):
        raise ValueError('Consumer requires explicit producer source MAC')
    return data


def load(path=PATH):
    try:
        with open(path) as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return {}
        return validate(json.loads(raw))
    except (OSError, ValueError, TypeError):
        return {}


def resolve(board_id, overrides, path=PATH):
    result = dict(load(path))
    result.pop('schema', None)
    result.update(overrides)
    if 'radio_role' in result:
        result['radio_role'] = canonical_role(result['radio_role'])
    if board_id == S3:
        # Never inherit FeatherS2's external IO43 button or invisible source MAC.
        result.setdefault('button_next_gpio', 1)
        result.setdefault('button_extra_next_gpio', None)
        if result.get('radio_role') == 'consumer' and not valid_mac(result.get('leader_mac')):
            raise ValueError('Consumer requires explicit producer source MAC')
    elif 'radio_role' not in result:
        result['radio_role'] = 'consumer'
    if board_id == V2 and result.get('radio_role') != 'consumer':
        raise ValueError('ESP32 V2 supports consumer only')
    return result


def save(data, path=PATH, writable=None, enrolled_role=None):
    validate(data)
    if enrolled_role and canonical_role(enrolled_role) != data['radio_role']:
        raise ValueError('Role locked: update enrolled identity through host workflow')
    if writable is None:
        import storage
        writable = not storage.getmount('/').readonly
    if not writable:
        raise RuntimeError('USB host owns filesystem; use make configure-node')
    encoded = json.dumps(data)
    if len(encoded) > MAX_BYTES:
        raise ValueError('Node state too large')
    temporary = path + '.tmp'
    with open(temporary, 'w') as stream:
        stream.write(encoded)
        stream.flush()
    if hasattr(os, 'sync'):
        os.sync()
    if load(temporary) != data:
        raise OSError('Node state readback failed')
    os.rename(temporary, path)
    if load(path) != data:
        raise OSError('Node state final verification failed')


def current():
    import board
    try:
        from node_config import OVERRIDES
    except ImportError:
        OVERRIDES = {}
    return resolve(board.board_id, OVERRIDES)
