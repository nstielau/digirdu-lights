"""Optional USB-base snapshot of this boot's OTA check; never persisted."""
from ota_manifest import BASE_VERSION, version_tuple

_state = 'not_checked'
_blocked = None
_reason = None


def reset(state='not_checked', reason=None):
    global _state, _blocked, _reason
    _state, _blocked = state, None
    _reason = str(reason)[:16] if state == 'unavailable' and reason else None


def failure_reason(error, phase='startup'):
    """Return a short, non-sensitive reason suitable for the Device page."""
    text = str(error).lower()
    kind = (type(error).__name__ + ' ' + text).lower()
    if text.startswith('http_status_'):
        code = text.rsplit('_', 1)[-1]
        if code.isdigit():
            return 'HTTP ' + code
    if any(word in kind for word in ('deadline', 'timeout', 'timed out', 'timedout')):
        return 'timeout'
    if any(word in kind for word in ('ssl', 'tls', 'certificate')):
        return 'TLS'
    if phase == 'wifi':
        return 'Wi-Fi'
    if phase == 'http':
        return 'HTTP'
    return 'startup'


def accept(result, running_version):
    """Strictly validate display-only metadata, independently of the manifest."""
    global _state, _blocked, _reason
    reset('unavailable', 'HTTP')
    try:
        info = result['update_status']
        if (type(info) is not dict or set(info) != {'schema', 'state', 'blocked'}
                or type(info['schema']) is not int or info['schema'] != 1
                or info['state'] not in ('checked', 'paused', 'no_release')):
            return
        blocked = info['blocked']
        if blocked is not None:
            if (info['state'] != 'checked' or type(blocked) is not dict
                    or set(blocked) != {'version', 'minimum_base'}
                    or version_tuple(blocked['version']) <= version_tuple(running_version)
                    or version_tuple(blocked['minimum_base']) <= version_tuple(BASE_VERSION)):
                return
            blocked = dict(blocked)
        _state, _blocked, _reason = info['state'], blocked, None
    except (KeyError, TypeError, ValueError):
        pass


def snapshot():
    result = {'schema': 1, 'state': _state,
              'blocked': dict(_blocked) if _blocked is not None else None}
    if _reason is not None:
        result['reason'] = _reason
    return result
