from atexit import register
import functools
import string
import textwrap

from jinja2 import Template
from pathlib import Path
from typing import Any, Dict, Callable, TypeVar

from httpie.cli.constants import SEPARATOR_FILE_UPLOAD
from httpie.cli.definition import options
from httpie.cli.options import Argument, ParserSpec

from completion_flow import generate_flow

T = TypeVar('T')

EXTRAS_DIR = Path(__file__).parent.parent.parent
COMPLETION_DIR = EXTRAS_DIR / 'completion'
TEMPLATES_DIR = COMPLETION_DIR / 'templates'

COMPLETION_TEMPLATE_BASE = TEMPLATES_DIR / 'completion'
COMPLETION_SCRIPT_BASE = COMPLETION_DIR / 'completion'

COMMON_HTTP_METHODS = [
    'GET',
    'POST',
    'PUT',
    'DELETE',
    'HEAD',
    'OPTIONS',
    'PATCH',
    'TRACE',
    'CONNECT',
]

COMPLETERS = {}


def use_template(shell_type):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(spec):
            template_file = COMPLETION_TEMPLATE_BASE.with_suffix(
                f'.{shell_type}.j2'
            )
            compiletion_script_file = COMPLETION_SCRIPT_BASE.with_suffix(
                f'.{shell_type}'
            )

            jinja_template = Template(template_file.read_text())
            jinja_template.globals.update(prepare_objects(spec))
            extra_variables = func(spec)
            compiletion_script_file.write_text(
                jinja_template.render(**extra_variables)
            )

        COMPLETERS[shell_type] = wrapper
        return wrapper

    return decorator


BASE_FUNCTIONS = {}


def prepare_objects(spec: ParserSpec) -> Dict[str, Any]:
    global_objects = {
        **BASE_FUNCTIONS,
    }
    global_objects['request_items'] = find_argument_by_target_name(
        spec, 'REQUEST_ITEM'
    )
    global_objects['arguments'] = [
        argument
        for group in spec.groups
        for argument in group.arguments
        if not argument.is_hidden
        if not argument.is_positional
    ]
    global_objects['methods'] = COMMON_HTTP_METHODS
    global_objects['generate_flow'] = generate_flow

    return global_objects


def register_function(func: T) -> T:
    BASE_FUNCTIONS[func.__name__] = func
    return func


@register_function
def is_file_based_operator(operator: str) -> bool:
    return operator in {SEPARATOR_FILE_UPLOAD}


def escape_zsh(text: str) -> str:
    return text.replace(':', '\\:')


def serialize_argument_to_zsh(argument):
    # The argument format is the following:
    # $prefix'$alias$has_value[$short_desc]:$metavar$:($choice_1 $choice_2)'

    prefix = ''
    declaration = []
    has_choices = 'choices' in argument.configuration

    # The format for the argument declaration canges depending on the
    # the number of aliases. For a single $alias, we'll embed it directly
    # in the declaration string, but for multiple of them, we'll use a
    # $prefix.
    if len(argument.aliases) > 1:
        prefix = '{' + ','.join(argument.aliases) + '}'
    else:
        declaration.append(argument.aliases[0])

    if not argument.is_flag:
        declaration.append('=')

    declaration.append('[' + argument.short_help + ']')

    if 'metavar' in argument.configuration:
        metavar = argument.metavar
    elif has_choices:
        # Choices always require a metavar, so even if we don't have one
        # we can generate it from the argument aliases.
        metavar = (
            max(argument.aliases, key=len)
            .lstrip('-')
            .replace('-', '_')
            .upper()
        )
    else:
        metavar = None

    if metavar:
        # Strip out any whitespace, and escape any characters that would
        # conflict with the shell.
        metavar = escape_zsh(metavar.strip(' '))
        declaration.append(f':{metavar}:')

    if has_choices:
        declaration.append('(' + ' '.join(argument.choices) + ')')

    return prefix + f"'{''.join(declaration)}'"


def serialize_argument_to_fish(argument):
    # The argument format is defined here
    # <https://fishshell.com/docs/current/completions.html>

    declaration = [
        'complete',
        '-c',
        'http',
    ]

    try:
        short_form, long_form = argument.aliases
    except ValueError:
        short_form = None
        (long_form,) = argument.aliases

    if short_form:
        declaration.append('-s')
        declaration.append(short_form)

    declaration.append('-l')
    declaration.append(long_form)

    if 'choices' in argument.configuration:
        declaration.append('-xa')
        declaration.append('"' + ' '.join(argument.choices) + '"')
    elif 'lazy_choices' in argument.configuration:
        declaration.append('-x')

    declaration.append('-d')
    declaration.append("'" + argument.short_help.replace("'", r"\'") + "'")

    return '\t'.join(declaration)


def find_argument_by_target_name(spec: ParserSpec, name: str) -> Argument:
    for group in spec.groups:
        for argument in group.arguments:
            if argument.aliases:
                targets = argument.aliases
            else:
                targets = [argument.metavar]

            if name in targets:
                return argument

    raise ValueError(f'Could not find argument with name {name}')


@use_template('zsh')
def zsh_completer(spec: ParserSpec) -> Dict[str, Any]:
    from zsh import compile_zsh

    return {
        'escape_zsh': escape_zsh,
        'serialize_argument_to_zsh': serialize_argument_to_zsh,
        'compile_zsh': compile_zsh
    }


@use_template('fish')
def fish_completer(spec: ParserSpec) -> Dict[str, Any]:
    return {
        'serialize_argument_to_fish': serialize_argument_to_fish,
    }


def main():
    for shell_type, completer in COMPLETERS.items():
        print(f'Generating {shell_type} completer.')
        completer(options)


if __name__ == '__main__':
    main()