"""Round-4 validation fixture: tiny mustache-style template renderer."""
import re

_TOKEN = re.compile(r"{{\s*([a-zA-Z0-9_.]+)\s*}}")


def render(template, context):
    """Render {{ name }} tokens from a flat/nested context."""
    def lookup(match):
        key = match.group(1)
        node = context
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return ""
        return str(node)

    return _TOKEN.sub(lookup, template)


def extract_keys(template):
    """List all variable names referenced by a template."""
    return [m.group(1) for m in _TOKEN.finditer(template)]
