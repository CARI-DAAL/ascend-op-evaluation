"""Leased external-method bootstrap; stdlib until declared dependencies load.

The parent owns identity, output validation and publication. This process reports
only what a caller-supplied method returned; it does not certify candidate truth.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import shutil
import sys
import traceback
import types
from pathlib import Path

PROTOCOL = 'custom-method-result-v1'
MAX_REPORT_BYTES = 64 * 1024


class EnvironmentUnavailable(RuntimeError):
    pass


class ProtocolError(ValueError):
    pass


def check_environment(request):
    requirements = request.get('requirements', {})
    observed = {'python': sys.version.split()[0], 'packages': {}, 'tools': {},
                'device': request.get('device', 'cpu')}
    for name, expected in requirements.get('packages', {}).items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise EnvironmentUnavailable(f'missing package: {name}') from error
        observed['packages'][name] = actual
        if actual != expected:
            raise EnvironmentUnavailable(f'package version mismatch: {name}')
    for tool in requirements.get('tools', []):
        path = shutil.which(tool)
        if path is None:
            raise EnvironmentUnavailable(f'missing tool: {tool}')
        observed['tools'][tool] = str(Path(path).resolve())
    if request.get('device') == 'npu:0':
        try:
            import torch
            import torch_npu  # noqa: F401
            if not torch.npu.is_available():
                raise EnvironmentUnavailable('assigned NPU is unavailable')
            torch.npu.set_device(0)
        except EnvironmentUnavailable:
            raise
        except Exception as error:
            raise EnvironmentUnavailable(f'NPU runtime unavailable: {type(error).__name__}') from error
    return observed


def load_entrypoint(root, entrypoint, method_ref):
    module, function = entrypoint.split(':', 1)
    namespace = '_evaluation_method_' + method_ref.removeprefix('sha256:')
    package = types.ModuleType(namespace)
    package.__path__ = [str(root)]
    sys.modules[namespace] = package
    # Relative imports resolve in the isolated namespace. Existing standalone
    # projects may still use absolute local imports through this private path.
    sys.path.insert(0, str(root))
    loaded = importlib.import_module(namespace + '.' + module)
    location = getattr(loaded, '__file__', None)
    if location is None or not Path(location).resolve().is_relative_to(root):
        raise ProtocolError('method entrypoint resolved outside its package')
    callback = getattr(loaded, function, None)
    if not callable(callback):
        raise ProtocolError('method entrypoint is not callable')
    return callback


def run(request):
    try:
        observed = check_environment(request)
        root = Path(request['package_dir']).resolve(strict=True)
        callback = load_entrypoint(root, request['entrypoint'], request['method_ref'])
        public = {key: value for key, value in request.items()
                  if key not in {'package_dir', 'entrypoint', 'requirements'}}
        if request.get('scratch_dir'):
            os.chdir(request['scratch_dir'])
        from triton_evaluation.runtime.process_title import set_stage
        set_stage('method', backend='method', initialize=True)
        report = callback(public)
        if not isinstance(report, dict):
            raise ProtocolError('method return value must be a JSON object')
        try:
            encoded = json.dumps(report, allow_nan=False, ensure_ascii=False).encode('utf-8')
        except (ValueError, TypeError) as error:
            raise ProtocolError('method report must contain finite JSON values') from error
        if len(encoded) > MAX_REPORT_BYTES:
            raise ProtocolError('method report exceeds 64 KiB')
        return {'protocol': PROTOCOL, 'outcome': 'completed', 'report': report, 'error': None,
                'runtime_observation': observed}
    except EnvironmentUnavailable as error:
        return failure('environment_unavailable', error)
    except ProtocolError as error:
        return failure('protocol_error', error)
    except BaseException as error:
        # Includes explicit SystemExit: a clean interpreter exit is not a report.
        traceback.print_exc(file=sys.stderr)
        return failure('method_error', error)


def failure(outcome, error):
    message = ' '.join(f'{type(error).__name__}: {error}'.split())
    message = message.encode('utf-8')[:512].decode('utf-8', errors='ignore')
    return {'protocol': PROTOCOL, 'outcome': outcome, 'report': None, 'error': message}


def main():
    from triton_evaluation.runtime.process_title import set_stage

    set_stage('load', backend='method', initialize=True)
    sys.dont_write_bytecode = True
    request_path, result_path = map(Path, sys.argv[1:3])
    request = json.loads(request_path.read_text(encoding='utf-8'))
    result = run(request)
    temporary = result_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, allow_nan=False, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, result_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
