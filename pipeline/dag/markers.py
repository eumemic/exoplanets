"""Generated numbers inside hand-written markdown.

A number that must follow the data is written between markers that GitHub does not display:

    <!--n:counted.total-->644<!--/n-->            the value of counted.total in the numbers file
    <!--n:counted.total|,-->644<!--/n-->          with thousands separators (1,138)
    <!--n:tiers.allsky.A|word-->two<!--/n-->       as a word (zero to twenty); |Word capitalises it
    <!--n:x.median|.3f-->0.013<!--/n-->           with a format specification

In a table row the format's bar is written \\| (<!--n:counted.total\\|,-->644<!--/n-->): GitHub splits a table row at
every bar that is not escaped, even inside a comment.

A generated block (a table) is written between <!--block:NAME--> and <!--/block-->.

fill() replaces what is between the markers and leaves the prose untouched. template() empties every marker, so the
build can tell an edit of the prose (a change of the template) from an edit of a generated value.
"""
import re

INLINE = re.compile(r"(<!--n:([A-Za-z0-9_.@-]+)(?:\\?\|([^>]*?))?-->)(.*?)(<!--/n-->)", re.S)
BLOCK = re.compile(r"(<!--block:([A-Za-z0-9_.-]+)-->\n?)(.*?)(<!--/block-->)", re.S)
WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen twenty").split()


def lookup(numbers, key):
    x = numbers
    for part in key.split("."):
        if not isinstance(x, dict) or part not in x:
            raise KeyError(f"{key} is not in the numbers file")
        x = x[part]
    return x


def render(value, fmt):
    if fmt in (None, ""):
        return str(value)
    if fmt == ",":
        return f"{value:,}"
    if fmt in ("word", "Word"):
        if not isinstance(value, int) or not 0 <= value <= 20:
            raise ValueError(f"{value!r} cannot be written as a word")
        w = WORDS[value]
        return w.capitalize() if fmt == "Word" else w
    return format(value, fmt)


def fill(text, numbers, blocks=None):
    """The text with every marker filled from numbers (and blocks: {name: text}); unknown keys are errors."""
    out = INLINE.sub(lambda m: m.group(1) + render(lookup(numbers, m.group(2)), m.group(3)) + m.group(5), text)
    if blocks is not None:
        def blk(m):
            if m.group(2) not in blocks:
                raise KeyError(f"no generated block named {m.group(2)}")
            body = blocks[m.group(2)]
            return m.group(1) + body + ("" if body.endswith("\n") else "\n") + m.group(4)
        out = BLOCK.sub(blk, out)
    return out


def template(text):
    """The text with every marker emptied: what a person writes."""
    text = INLINE.sub(lambda m: m.group(1) + m.group(5), text)
    return BLOCK.sub(lambda m: m.group(1) + m.group(4), text)


def keys(text):
    return sorted({m.group(2) for m in INLINE.finditer(text)})
