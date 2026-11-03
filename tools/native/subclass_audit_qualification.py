"""Pure qualification rules for tools/native/subclass-audit.py.

This module deliberately has no PDF, subprocess, Reader or file-system access.
It only decides whether one native probe result and the completed case set are
clean enough to report.  Original caught errors and console messages are kept
verbatim; malformed or missing diagnostic streams are always failures.
"""

_MISSING = object()


def _diagnostic_streams(data):
    """Return (structure issues, errors, console messages) from a probe report.

    ``errors`` and ``console.messages`` are the two diagnostic streams emitted
    by the native host.  A report that omits either stream, or presents it with
    the wrong shape, cannot establish cleanliness.
    """
    if not isinstance(data, dict):
        return ['probe report is not an object'], [], []

    diagnostics = data.get('diagnostics', _MISSING)
    if diagnostics is _MISSING:
        return ['diagnostics is missing'], [], []
    if not isinstance(diagnostics, dict):
        return ['diagnostics is not an object'], [], []

    issues = []
    errors = diagnostics.get('errors', _MISSING)
    if errors is _MISSING:
        issues.append('diagnostics.errors is missing')
        errors = []
    elif not isinstance(errors, list):
        issues.append('diagnostics.errors is not a list')
        errors = []
    else:
        if any(not isinstance(item, dict) for item in errors):
            issues.append('diagnostics.errors contains a non-object entry')
        errors = list(errors)

    console = diagnostics.get('console', _MISSING)
    if console is _MISSING:
        issues.append('diagnostics.console is missing')
        messages = []
    elif not isinstance(console, dict):
        issues.append('diagnostics.console is not an object')
        messages = []
    else:
        messages = console.get('messages', _MISSING)
        if messages is _MISSING:
            issues.append('diagnostics.console.messages is missing')
            messages = []
        elif not isinstance(messages, list):
            issues.append('diagnostics.console.messages is not a list')
            messages = []
        else:
            if any(not isinstance(item, dict) for item in messages):
                issues.append(
                    'diagnostics.console.messages contains a non-object entry'
                )
            messages = list(messages)
    return issues, errors, messages


def qualify_probe(returncode, data, phase='creation'):
    """Qualify one probe execution.

    ``phase`` is only used in the reported reason (``creation`` or ``reopen``).
    Execution success requires exit status zero and an explicit boolean
    ``passed`` of true.  Diagnostics must be well-formed and both streams must
    be empty.  The function never raises for a malformed or missing report.
    """
    issues, errors, messages = _diagnostic_streams(data)
    reported_error = data.get('error') if isinstance(data, dict) else None
    detail = reported_error if isinstance(reported_error, str) and reported_error else ''
    execution_passed = (
        returncode == 0
        and isinstance(data, dict)
        and data.get('passed') is True
    )

    if returncode != 0:
        error = f'{phase} probe exited with status {returncode}'
        if detail:
            error += f': {detail}'
    elif not execution_passed:
        error = f'{phase} probe did not report execution success'
        if detail:
            error += f': {detail}'
    elif issues:
        error = f'{phase} diagnostic structure is malformed: ' + '; '.join(issues)
    else:
        problems = []
        if errors:
            problems.append(f'{len(errors)} original caught error(s)')
        if messages:
            problems.append(f'{len(messages)} original console message(s)')
        error = None
        if problems:
            error = (
                f'{phase} probe reported ' + ' and '.join(problems)
                + ' requiring qualification'
            )

    return {
        'phase': phase,
        'execution_passed': execution_passed,
        'diagnostics_checked': not issues,
        'diagnostic_errors': errors,
        'console_messages': messages,
        'diagnostic_structure_errors': issues,
        'passed': execution_passed and not issues and not errors and not messages,
        'error': error,
    }


def reopen_qualification(case, returncode, data):
    """Return a copy of a creation-qualified case with reopen qualification.

    A reopen can only preserve a pass; it can never turn a failed creation case
    into a pass.  Creation diagnostic fields and provenance fields stay intact.
    """
    if not isinstance(case, dict):
        raise TypeError('case must be an object')
    probe = qualify_probe(returncode, data, phase='reopen')
    result = dict(case)
    result.update({
        'reopen_execution_passed': probe['execution_passed'],
        'reopen_diagnostics_checked': probe['diagnostics_checked'],
        'reopen_diagnostic_errors': probe['diagnostic_errors'],
        'reopen_console_messages': probe['console_messages'],
        'reopen_diagnostic_structure_errors': probe['diagnostic_structure_errors'],
        'reopen_error': probe['error'],
        'passed': case.get('passed') is True and probe['passed'],
    })
    if probe['error'] is not None:
        result['error'] = probe['error']
    elif result['passed'] is not True and not result.get('error'):
        result['error'] = 'Creation qualification did not pass'
    return result


def case_set_complete(fixtures):
    """Return ``(complete, reason)`` for the audited fixture cases.

    An empty fixture list, a fixture with no attempted cases, or any case that
    lacks clean creation/reopen diagnostics is incomplete.  This prevents an
    empty ``all(...)`` from claiming success without qualified cases.
    """
    if not isinstance(fixtures, list) or not fixtures:
        return False, 'no fixture cases were audited'
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            return False, 'fixture entry is malformed'
        name = fixture.get('fixture', '<unknown fixture>')
        cases = fixture.get('cases')
        if not isinstance(cases, list) or not cases:
            return False, f'{name} has zero completed cases'
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                return False, f'{name} case {index} is malformed'
            label = '%s %s/%s' % (
                name, case.get('class', '?'), case.get('subclass', '?')
            )
            if case.get('execution_passed') is not True:
                return False, f'{label} creation execution did not pass'
            if case.get('diagnostics_checked') is not True:
                return False, f'{label} creation diagnostics were not checked'
            if case.get('diagnostic_structure_errors'):
                return False, f'{label} creation diagnostic structure is malformed'
            if case.get('diagnostic_errors') != []:
                return False, f'{label} creation errors are not empty'
            if case.get('console_messages') != []:
                return False, f'{label} creation console messages are not empty'
            if case.get('reopen_execution_passed') is not True:
                return False, f'{label} reopen execution did not pass'
            if case.get('reopen_diagnostics_checked') is not True:
                return False, f'{label} reopen diagnostics were not checked'
            if case.get('reopen_diagnostic_structure_errors'):
                return False, f'{label} reopen diagnostic structure is malformed'
            if case.get('reopen_diagnostic_errors') != []:
                return False, f'{label} reopen errors are not empty'
            if case.get('reopen_console_messages') != []:
                return False, f'{label} reopen console messages are not empty'
            if case.get('passed') is not True:
                return False, f'{label} did not pass'
    return True, None
