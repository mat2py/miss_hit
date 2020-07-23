#!/usr/bin/env python3
##############################################################################
##                                                                          ##
##          MATLAB Independent, Small & Safe, High Integrity Tools          ##
##                                                                          ##
##              Copyright (C) 2019-2020, Florian Schanda                    ##
##              Copyright (C) 2019-2020, Zenuity AB                         ##
##                                                                          ##
##  This file is part of MISS_HIT.                                          ##
##                                                                          ##
##  MATLAB Independent, Small & Safe, High Integrity Tools (MISS_HIT) is    ##
##  free software: you can redistribute it and/or modify it under the       ##
##  terms of the GNU General Public License as published by the Free        ##
##  Software Foundation, either version 3 of the License, or (at your       ##
##  option) any later version.                                              ##
##                                                                          ##
##  MISS_HIT is distributed in the hope that it will be useful,             ##
##  but WITHOUT ANY WARRANTY; without even the implied warranty of          ##
##  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the           ##
##  GNU General Public License for more details.                            ##
##                                                                          ##
##  You should have received a copy of the GNU General Public License       ##
##  along with MISS_HIT. If not, see <http://www.gnu.org/licenses/>.        ##
##                                                                          ##
##############################################################################

# This is a stylechecker for (mostly) whitespace issues. It can
# rewrite the code to fix most of them.

import os
import re

from abc import ABCMeta, abstractmethod

from miss_hit import work_package
from miss_hit import command_line
from miss_hit import config
from miss_hit import g_cfg

from miss_hit.errors import (Location, Error, ICE,
                             Message_Handler, HTML_Message_Handler)
from miss_hit.m_ast import *
from miss_hit.m_lexer import MATLAB_Lexer, Token_Buffer
from miss_hit.m_parser import MATLAB_Parser


COPYRIGHT_REGEX = r"(\(c\) )?Copyright (\d\d\d\d-)?\d\d\d\d *(?P<org>.*)"


class Style_Rule(metaclass=ABCMeta):
    def __init__(self, name, autofix):
        assert isinstance(name, str)
        assert isinstance(autofix, bool)
        self.name = name
        self.autofix = autofix
        self.mandatory = False


class Style_Rule_File(Style_Rule):
    def __init__(self, name):
        super().__init__(name, False)

    @abstractmethod
    def apply(self, mh, cfg, filename, full_text, lines):
        pass


class Style_Rule_Line(Style_Rule):
    @abstractmethod
    def apply(self, mh, cfg, filename, line_no, line):
        pass


class Rule_File_Length(Style_Rule_File):
    """Maximum file length

    This is configurable with 'file_length'. It is a good idea to keep
    the length of your files under some limit since it forces your
    project into avoiding the worst spaghetti code.

    """

    parameters = {
        "file_length": {
            "type"    : int,
            "metavar" : "N",
            "help"    : ("Maximum lines in a file, %u by default." %
                         config.BASE_CONFIG["file_length"]),
        }
    }

    defaults = {
        "file_length" : config.BASE_CONFIG["file_length"],
    }

    def __init__(self):
        super().__init__("file_length")

    def apply(self, mh, cfg, filename, full_text, lines):
        if len(lines) > cfg["file_length"]:
            mh.style_issue(Location(filename,
                                    len(lines)),
                           "file exceeds %u lines" % cfg["file_length"],
                           self.autofix)


class Rule_File_EOF_Lines(Style_Rule_File):
    """Trailing newlines at end of file

    This mandatory rule makes sure there is a single trailing newline
    at the end of a file.

    """

    def __init__(self):
        super().__init__("eof_newlines")
        self.mandatory = True
        self.autofix = True

    def apply(self, mh, cfg, filename, full_text, lines):
        if len(lines) >= 2 and lines[-1] == "":
            mh.style_issue(Location(filename,
                                    len(lines)),
                           "trailing blank lines at end of file",
                           self.autofix)
        elif len(full_text) and full_text[-1] != "\n":
            mh.style_issue(Location(filename,
                                    len(lines)),
                           "file should end with a new line",
                           self.autofix)


class Rule_Line_Length(Style_Rule_Line):
    """Max characters per line

    This is configurable with 'line_length', default is 80. It is a
    good idea for readability to avoid overly long lines. This can help
    you avoid extreme levels of nesting and avoids having to scroll
    around.

    """

    parameters = {
        "line_length": {
            "type"    : int,
            "metavar" : "N",
            "help"    : ("Maximum characters per line, %u by default." %
                         config.BASE_CONFIG["line_length"]),
        }
    }

    defaults = {
        "line_length" : config.BASE_CONFIG["line_length"],
    }

    def __init__(self):
        super().__init__("line_length", False)

    def apply(self, mh, cfg, filename, line_no, line):
        if len(line) > cfg["line_length"]:
            mh.style_issue(Location(filename,
                                    line_no,
                                    cfg["line_length"],
                                    len(line),
                                    line),
                           "line exceeds %u characters" % cfg["line_length"],
                           self.autofix)


class Rule_Line_Blank_Lines(Style_Rule_Line):
    """Consecutive blank lines

    This rule allows a maximum of one blank line to separate code blocks.
    Comments are not considered blank lines.

    """

    def __init__(self):
        super().__init__("consecutive_blanks", True)
        self.mandatory = True
        self.is_blank = False

    def apply(self, mh, cfg, filename, line_no, line):
        if len(line.strip()):
            self.is_blank = False
        elif self.is_blank:
            mh.style_issue(Location(filename,
                                    line_no),
                           "more than one consecutive blank line",
                           self.autofix)
        else:
            self.is_blank = True


class Rule_Line_Tabs(Style_Rule_Line):
    """Use of tab

    This rule enforces the absence of the tabulation character
    *everywhere*. When auto-fixing, a tab-width of 4 is used by default,
    but this can be configured with the options 'tab_width'.

    Note that the fix replaces the tab everywhere, including in strings
    literals. This means
    ```
    "a<tab>b"
       "a<tab>b"
    ```
    might be fixed to
    ```
    "a        b"
       "a     b"
    ```

    Which may or may not what you had intended originally. I am not sure
    if this is a bug or a feature, but either way it would be *painful* to
    change so I am going to leave this as is.

    """

    parameters = {
        "tab_width": {
            "type"    : int,
            "metavar" : "N",
            "help"    : ("Tab-width, by default %u." %
                         config.BASE_CONFIG["tab_width"]),
        }
    }

    defaults = {
        "tab_width" : config.BASE_CONFIG["tab_width"],
    }

    def __init__(self):
        super().__init__("tabs", True)
        self.mandatory = True

    def apply(self, mh, cfg, filename, line_no, line):
        if "\t" in line:
            mh.style_issue(Location(filename,
                                    line_no,
                                    line.index("\t"),
                                    line.index("\t"),
                                    line),
                           "tab is not allowed",
                           self.autofix)


class Rule_Line_Trailing_Whitesapce(Style_Rule_Line):
    """Trailing whitespace

    This rule enforces that there is no trailing whitespace in your files.
    You *really* want to do this, even if the MATLAB default editor makes
    this really hard. The reason is that it minimises conflicts when using
    modern version control systems.

    """

    def __init__(self):
        super().__init__("trailing_whitespace", True)
        self.mandatory = True

    def apply(self, mh, cfg, filename, line_no, line):
        if line.endswith(" "):
            if len(line.strip()) == 0:
                mh.style_issue(Location(filename,
                                        line_no),
                               "whitespace on blank line",
                               self.autofix)
            else:
                mh.style_issue(Location(filename,
                                        line_no,
                                        len(line.rstrip()),
                                        len(line),
                                        line),
                               "trailing whitespace",
                               self.autofix)


def get_rules():
    rules = {
        "on_file" : [],
        "on_line" : [],
        "on_token" : [],
    }

    def rec(root):
        is_leaf = True
        for subclass in root.__subclasses__():
            rec(subclass)
            is_leaf = False

        if is_leaf:
            if issubclass(root, Style_Rule_File):
                rules["on_file"].append(root)
            elif issubclass(root, Style_Rule_Line):
                rules["on_line"].append(root)
            else:
                raise ICE("Unable to categorize %s with base %s" %
                          (root.__name__,
                           " and ".join(b.__name__
                                        for b in root.__bases__)))

    rec(Style_Rule)
    return rules


def build_library(cfg, rules):
    lib = {
        "on_file" : [],
        "on_line" : [],
        "on_token" : []
    }

    for kind in rules:
        for rule in rules[kind]:
            inst = rule()
            if inst.mandatory or config.active(cfg, inst.name):
                lib[kind].append(inst)

    return lib


##############################################################################


KEYWORDS_WITH_WS = frozenset([
    "case",
    "catch",
    "classdef",
    "elseif",
    "for",
    "function",
    "global",
    "if",
    "parfor",
    "persistent",
    "switch",
    "while",

    # These are not keywords all the time, but we treat them like it.
    "properties",
    "methods",
    "events",
])


def stage_3_analysis(mh, cfg, tbuf, is_embedded):
    assert isinstance(mh, Message_Handler)
    assert isinstance(tbuf, Token_Buffer)
    assert isinstance(is_embedded, bool)

    in_copyright_notice = (config.active(cfg, "copyright_notice") and
                           (not is_embedded or
                            cfg["copyright_in_embedded_code"]))
    company_copyright_found = False
    generic_copyright_found = False
    copyright_token = None
    copyright_notice = []

    # Some state needed to fix indentation
    statement_start_token = None
    current_indent = 0
    enclosing_ast = None

    for n, token in enumerate(tbuf.tokens):
        if n - 1 >= 0:
            prev_token = tbuf.tokens[n - 1]
        else:
            prev_token = None

        if n + 1 < len(tbuf.tokens):
            next_token = tbuf.tokens[n + 1]
        else:
            next_token = None

        if (prev_token and
            prev_token.location.line == token.location.line):
            prev_in_line = prev_token
            ws_before = (token.location.col_start -
                         prev_in_line.location.col_end) - 1

        else:
            prev_in_line = None
            ws_before = None

        if (next_token and
            next_token.location.line == token.location.line):
            if next_token.kind == "NEWLINE":
                next_in_line = None
                ws_after = None
            else:
                next_in_line = next_token
                ws_after = (next_in_line.location.col_start -
                            token.location.col_end) - 1
        else:
            next_in_line = None
            ws_after = None

        # Keep track of statement starters. This is required for
        # indentation.
        if token.first_in_statement:
            # We need to take special care of comments that are the
            # first thing after an open block. Since comments are not
            # attached to the AST (and it is not practical to do so),
            # most of the time we can just indent them to "same as
            # above". But if they are the first item inside e.g. an if
            # statement, then this won't work (the previous
            # indentation level is one too low).
            if statement_start_token and \
               statement_start_token.kind == "KEYWORD" and \
               statement_start_token.value == "end":
                # The previous token was 'end'. We don't need to
                # do anything in this case, since we'll re-use the
                # indentation level of the compound statement
                enclosing_ast = None
            elif statement_start_token and \
                 statement_start_token.ast_link and \
                 statement_start_token.ast_link.causes_indentation():
                # We've got a previous AST node. We remember it,
                # and indent one level below it, but only if it is
                # a statement that would create nesting.
                enclosing_ast = statement_start_token.ast_link

            statement_start_token = token

        # Recognize justifications
        if token.kind in ("COMMENT", "CONTINUATION"):
            if "mh:ignore_style" in token.value:
                mh.register_justification(token)

        # Don't ever check anonymous tokens
        if token.anonymous:
            continue

        # Corresponds to the old CodeChecker CopyrightCheck rule
        if in_copyright_notice:
            if token.kind == "COMMENT":
                match = re.search(COPYRIGHT_REGEX, token.value)
                if match:
                    # We have a sane copyright string
                    copyright_token = token
                    generic_copyright_found = True
                    if match.group("org").strip() in cfg["copyright_entity"]:
                        company_copyright_found = True

                elif copyright_token is None:
                    # We might find something that could look like a
                    # copyright, but is not quite right
                    for org in cfg["copyright_entity"]:
                        if org.lower() in token.value.lower():
                            copyright_token = token
                            break
                    for substr in ("(c)", "copyright"):
                        if substr in token.value.lower():
                            copyright_token = token
                            break

                copyright_notice.append(token.value)

            else:
                # Once we get a non-comment token, the header has
                # ended. We then emit messages if we could not find
                # anything.
                in_copyright_notice = False

                if len(copyright_notice) == 0:
                    mh.style_issue(token.location,
                                   "file does not appear to contain any"
                                   " copyright header")
                elif company_copyright_found:
                    # Everything is fine
                    pass
                elif generic_copyright_found:
                    # If we have something basic, we only raise an
                    # issue if we're supposed to have something
                    # specific.
                    if cfg["copyright_entity"]:
                        mh.style_issue(copyright_token.location,
                                       "Copyright does not mention one of %s" %
                                       (" or ".join(cfg["copyright_entity"])))
                elif copyright_token:
                    # We found something that might be a copyright,
                    # but is not in a sane format
                    mh.style_issue(copyright_token.location,
                                   "Copyright notice not in right format")
                else:
                    # We found nothing
                    mh.style_issue(token.location,
                                   "No copyright notice found in header")

        # Corresponds to the old CodeChecker CommaWhitespace
        # rule. CommaLineEndings is now folded into the new
        # end_of_statements rule, which is much more strict and
        # complete.
        if token.kind == "COMMA":
            if config.active(cfg, "whitespace_comma"):
                token.fix.ensure_trim_before = True
                token.fix.ensure_ws_after = True

                if (next_in_line and ws_after == 0) or \
                   (prev_in_line and ws_before > 0):
                    mh.style_issue(token.location,
                                   "comma cannot be preceeded by whitespace "
                                   "and must be followed by whitespace",
                                   True)

        elif token.kind == "COLON":
            if config.active(cfg, "whitespace_colon"):
                if prev_in_line and prev_in_line.kind == "COMMA":
                    pass
                    # We don't deal with this here. If anything it's the
                    # problem of the comma whitespace rules.
                elif next_in_line and \
                     next_in_line.kind == "CONTINUATION":
                    # Special exception in the rare cases we
                    # continue a range expression
                    if prev_in_line and ws_before > 0:
                        token.fix.ensure_trim_before = True
                        mh.style_issue(token.location,
                                       "no whitespace before colon",
                                       True)
                elif (prev_in_line and ws_before > 0) or \
                     (next_in_line and ws_after > 0):
                    token.fix.ensure_trim_before = True
                    token.fix.ensure_trim_after = True
                    mh.style_issue(token.location,
                                   "no whitespace around colon"
                                   " allowed",
                                   True)

        # Corresponds to the old CodeChecker EqualSignWhitespace rule
        elif token.kind == "ASSIGNMENT":
            if config.active(cfg, "whitespace_assignment"):
                token.fix.ensure_ws_before = True
                token.fix.ensure_ws_after = True

                if prev_in_line and ws_before == 0:
                    mh.style_issue(token.location,
                                   "= must be preceeded by whitespace",
                                   True)
                elif next_in_line and ws_after == 0:
                    mh.style_issue(token.location,
                                   "= must be succeeded by whitespace",
                                   True)

        # Corresponds to the old CodeChecker ParenthesisWhitespace and
        # BracketsWhitespace rules
        elif token.kind in ("BRA", "A_BRA", "M_BRA"):
            if config.active(cfg, "whitespace_brackets") and \
               next_in_line and ws_after > 0 and \
               next_in_line.kind != "CONTINUATION":
                mh.style_issue(token.location,
                               "%s must not be followed by whitespace" %
                               token.raw_text,
                               True)
                token.fix.ensure_trim_after = True

        elif token.kind in ("KET", "A_KET", "M_KET"):
            if config.active(cfg, "whitespace_brackets") and \
               prev_in_line and ws_before > 0:
                mh.style_issue(token.location,
                               "%s must not be preceeded by whitespace" %
                               token.raw_text,
                               True)
                token.fix.ensure_trim_before = True

        # Corresponds to the old CodeChecker KeywordWhitespace rule
        elif (token.kind == "KEYWORD" and
              token.value in KEYWORDS_WITH_WS):
            if config.active(cfg, "whitespace_keywords") and \
               next_in_line and ws_after == 0:
                mh.style_issue(token.location,
                               "keyword must be succeeded by whitespace",
                               True)
                token.fix.ensure_ws_after = True

        # Corresponds to the old CodeChecker CommentWhitespace rule
        elif token.kind == "COMMENT":
            if config.active(cfg, "whitespace_comments"):
                comment_char = token.raw_text[0]
                comment_body = token.raw_text.lstrip(comment_char)
                if re.match("^%#[a-zA-Z]", token.raw_text):
                    # Stuff like %#codegen or %#ok are pragmas and should
                    # not be subject to style checks
                    pass

                elif token.raw_text.startswith("%|"):
                    # This is a miss-hit pragma, but we've not
                    # processed it. This is fine.
                    pass

                elif token.block_comment:
                    # Ignore block comments
                    pass

                elif token.raw_text.strip() in ("%s%s" % (cc, cb)
                                                for cc in tbuf.comment_char
                                                for cb in "{}"):
                    # Leave block comment indicators alone
                    pass

                elif re.match("^%# +[a-zA-Z]", token.raw_text):
                    # This looks like a pragma, but there is a spurious
                    # space
                    mh.style_issue(token.location,
                                   "MATLAB pragma must not contain whitespace "
                                   "between %# and the pragma",
                                   True)
                    token.raw_text = "%#" + token.raw_text[2:].strip()

                elif re.match("^% +#[a-zA-Z]", token.raw_text):
                    # This looks like a pragma that got "fixed" before we
                    # fixed our pragma handling
                    mh.style_issue(token.location,
                                   "MATLAB pragma must not contain whitespace "
                                   "between % and the pragma",
                                   True)
                    token.raw_text = "%#" + token.raw_text.split("#", 1)[1]

                elif comment_body and not comment_body.startswith(" "):
                    # Normal comments should contain whitespace
                    mh.style_issue(token.location,
                                   "comment body must be separated with "
                                   "whitespace from the starting %s" %
                                   comment_char,
                                   True)
                    token.raw_text = (comment_char * (len(token.raw_text) -
                                                      len(comment_body)) +
                                      " " +
                                      comment_body)

                # Make sure we have whitespace before each comment
                if prev_in_line and ws_before == 0:
                    mh.style_issue(token.location,
                                   "comment must be preceeded by whitespace",
                                   True)
                    token.fix.ensure_ws_before = True

        elif token.kind == "CONTINUATION":
            # Make sure we have whitespace before each line continuation
            if config.active(cfg, "whitespace_continuation") and \
               prev_in_line and ws_before == 0:
                mh.style_issue(token.location,
                               "continuation must be preceeded by whitespace",
                               True)
                token.fix.ensure_ws_before = True

            if config.active(cfg, "operator_after_continuation") and \
               next_token and next_token.first_in_line and \
               next_token.kind == "OPERATOR" and \
               next_token.fix.binary_operator:
                # Continuations should not start with operators unless
                # its a unary.
                mh.style_issue(next_token.location,
                               "continuations should not start with binary "
                               "operators")

            if config.active(cfg, "useless_continuation"):
                if next_token and next_token.kind in ("NEWLINE", "COMMENT"):
                    # Continuations followed immediately by a new-line
                    # or comment are not actually helpful at all.
                    mh.style_issue(token.location,
                                   "useless line continuation",
                                   True)
                    token.fix.replace_with_newline = True
                elif prev_token and prev_token.fix.statement_terminator:
                    mh.style_issue(token.location,
                                   "useless line continuation",
                                   True)
                    token.fix.delete = True

        elif token.kind == "OPERATOR":
            if not config.active(cfg, "operator_whitespace"):
                pass
            elif token.fix.unary_operator:
                if (prev_in_line and ws_before > 0) and \
                   token.value in (".'", "'"):
                    mh.style_issue(token.location,
                                   "suffix operator must not be preceeded by"
                                   " whitespace",
                                   True)
                    token.fix.ensure_trim_before = True
                elif (next_in_line and ws_after > 0) and \
                     token.value not in (".'", "'"):
                    mh.style_issue(token.location,
                                   "unary operator must not be followed by"
                                   " whitespace",
                                   True)
                    token.fix.ensure_trim_after = True
            elif token.fix.binary_operator:
                if token.value in (".^", "^"):
                    if (prev_in_line and ws_before > 0) or \
                       (next_in_line and ws_after > 0):
                        mh.style_issue(token.location,
                                       "power binary operator"
                                       " must not be surrounded by whitespace",
                                       True)
                        token.fix.ensure_trim_before = True
                        token.fix.ensure_trim_after = True
                else:
                    if (prev_in_line and ws_before == 0) or \
                       (next_in_line and ws_after == 0):
                        mh.style_issue(token.location,
                                       "non power binary operator"
                                       " must be surrounded by whitespace",
                                       True)
                        token.fix.ensure_ws_before = True
                        token.fix.ensure_ws_after = True

            if config.active(cfg, "implicit_shortcircuit") and \
               token.value in ("&", "|") and \
               token.ast_link and \
               isinstance(token.ast_link, Binary_Logical_Operation) and \
               token.ast_link.short_circuit:
                # This rule is *disabled* for now since it does not
                # work in all circumstances. Curiously, this bug is
                # shared by mlint which also mis-classifies & when
                # applied to arrays.
                #
                # To fix this we need to perform semantic analysis and
                # type inference. We're leaving this in for
                # compatibility with miss_hit.cfg files that contain
                # reference to this rules.
                #
                # mh.style_issue(token.location,
                #                "implicit short-circuit operation due to"
                #                " expression being contained in "
                #                " if/while guard",
                #                True)
                # token.fix.make_shortcircuit_explicit = True
                pass

        elif token.kind == "ANNOTATION":
            if config.active(cfg, "annotation_whitespace"):
                token.fix.ensure_ws_after = True

                if next_in_line and ws_after == 0:
                    mh.style_issue(token.location,
                                   "annotation indication must be succeeded"
                                   " by whitespace",
                                   True)

        elif token.kind == "NEWLINE":
            if n == 0 and config.active(cfg, "no_starting_newline"):
                # Files should not *start* with newline(s)
                mh.style_issue(token.location,
                               "files should not start with a newline",
                               True)
                token.fix.delete = True

        # Check some specific problems with continuations
        if token.fix.flag_continuations and \
           next_in_line and next_in_line.kind == "CONTINUATION":
            fixed = False
            token.fix.add_newline = False
            if config.active(cfg, "dangerous_continuation"):
                next_in_line.fix.replace_with_newline = True
                fixed = True
            mh.style_issue(next_in_line.location,
                           "this continuation is dangerously misleading",
                           fixed)

        # Complain about indentation
        if config.active(cfg, "indentation") and token.kind != "NEWLINE":
            if token.first_in_line and not token.block_comment:
                if token.first_in_statement:
                    if token.ast_link:
                        current_indent = token.ast_link.get_indentation()
                    elif enclosing_ast:
                        current_indent = enclosing_ast.get_indentation() + 1
                    offset = 0

                else:
                    # This is a continued line. We try to preserve
                    # the offset. We work out how much extra space
                    # this token has based on the statement
                    # starting token.
                    offset = token.location.col_start - \
                        statement_start_token.location.col_start

                    # If positive, we can just add it. If 0 or
                    # negative, then we add 1/2 tabs to continue
                    # the line, since previously it was not offset
                    # at all.
                    if offset <= 0:
                        offset = cfg["tab_width"] // 2

                correct_spaces = cfg["tab_width"] * current_indent + offset
                token.fix.correct_indent = correct_spaces

                if token.location.col_start != correct_spaces:
                    mh.style_issue(token.location,
                                   "indentation not correct, should be"
                                   " %u spaces, not %u" %
                                   (correct_spaces,
                                    token.location.col_start),
                                   True)


class MH_Style_Result(work_package.Result):
    def __init__(self, wp):
        super().__init__(wp, True)


class MH_Style(command_line.MISS_HIT_Back_End):
    def __init__(self):
        super().__init__("MH Style")

    @classmethod
    def process_wp(cls, wp):
        rule_set = wp.extra_options["rule_set"]
        autofix = wp.options.fix
        fd_tree = wp.extra_options["fd_tree"]
        debug_validate_links = wp.options.debug_validate_links

        # Build rule library

        rule_lib = build_library(wp.cfg, rule_set)

        # Load file content

        content = wp.get_content()

        # Create lexer

        lexer = MATLAB_Lexer(wp.mh, content, wp.filename, wp.blockname)
        if wp.cfg["octave"]:
            lexer.set_octave_mode()
        if wp.cfg["ignore_pragmas"]:
            lexer.process_pragmas = False

        # We're dealing with an empty file here. Lets just not do anything

        if len(lexer.text.strip()) == 0:
            return MH_Style_Result(wp)

        # Stage 1 - rules around the file itself

        for rule in rule_lib["on_file"]:
            rule.apply(wp.mh, wp.cfg,
                       lexer.filename,
                       lexer.text,
                       lexer.context_line)

        # Stage 2 - rules around raw text lines

        for line_no, line in enumerate(lexer.context_line, 1):
            for rule in rule_lib["on_line"]:
                rule.apply(wp.mh, wp.cfg,
                           lexer.filename,
                           line_no,
                           line)

        # Tabs are just super annoying, and they require special
        # treatment. There is a known but obscure bug here, in that tabs
        # in strings are replaced as if they were part of normal
        # text. This is probably not intentional. For example:
        #
        # "a<tab>b"
        #    "a<tab>b"
        #
        # Will right now come out as
        #
        # "a   b"
        # "  a b"
        #
        # This is probably not correct. Fixing this is will require a very
        # different kind of lexing (which I am not in the mood for, I have
        # suffered enough to deal with ') or a 2-pass solution (which is
        # slow): first we lex and then fix up tabs inside tokens; and then
        # we do the global replacement and lex again before we proceed.

        if autofix:
            lexer.correct_tabs(wp.cfg["tab_width"])

        # Create tokenbuffer

        try:
            tbuf = Token_Buffer(lexer, wp.cfg)
        except Error:
            # If there are lex errors, we can stop here
            return MH_Style_Result(wp)

        # Create parse tree

        try:
            parser = MATLAB_Parser(wp.mh, tbuf, wp.cfg)
            parse_tree = parser.parse_file()

            # Check naming (we do this after parsing, not during,
            # since we may beed to re-write functions without end).
            parse_tree.sty_check_naming(wp.mh, wp.cfg)

            if debug_validate_links:
                tbuf.debug_validate_links()

            if fd_tree:
                fd_tree.write("-- Parse tree for %s\n" % wp.filename)
                parse_tree.pp_node(fd_tree)
                fd_tree.write("\n\n")

        except Error:
            parse_tree = None

        # Create CFG for debugging purposes

        if parse_tree and wp.options.debug_cfg:
            g_cfg.debug_cfg(parse_tree, wp.mh)

        # Stage 3 - rules around individual tokens

        stage_3_analysis(wp.mh, wp.cfg,
                         tbuf,
                         isinstance(wp, work_package.Embedded_MATLAB_WP))

        # Stage 4 - rules involving the parse tree

        # TODO

        # Possibly re-write the file, with issues fixed

        if autofix:
            if not parse_tree:
                wp.mh.error(lexer.get_file_loc(),
                            "file is not auto-fixed because it contains"
                            " parse errors",
                            fatal=False)
            else:
                # TODO: call modify()
                wp.write_modified(tbuf.replay())

        # Return results

        return MH_Style_Result(wp)


def main_handler():
    rule_set = get_rules()
    clp = command_line.create_basic_clp()

    clp["ap"].add_argument("--fix",
                           action="store_true",
                           default=False,
                           help=("Automatically fix issues where the fix"
                                 " is obvious"))

    clp["ap"].add_argument("--process-slx",
                           action="store_true",
                           default=False,
                           help=("Style-check (but not yet auto-fix) code"
                                 " inside SIMULINK models. This option is"
                                 " temporary, and will be removed in"
                                 " future once the feature is good enough"
                                 " to be enabled by default."))

    # Extra output options
    clp["output_options"].add_argument(
        "--html",
        default=None,
        help="Write report to given file as HTML")
    clp["output_options"].add_argument(
        "--no-style",
        action="store_true",
        default=False,
        help="Don't show any style message, only show warnings and errors.")

    # Debug options
    clp["debug_options"].add_argument(
        "--debug-dump-tree",
        default=None,
        metavar="FILE",
        help="Dump text-based parse tree to given file")
    clp["debug_options"].add_argument(
        "--debug-validate-links",
        action="store_true",
        default=False,
        help="Debug option to check AST links")
    clp["debug_options"].add_argument(
        "--debug-cfg",
        action="store_true",
        default=False,
        help="Build CFG for every function")

    style_option = clp["ap"].add_argument_group("rule options")

    # Add any parameters from rules
    for rule_kind in rule_set:
        for rule in rule_set[rule_kind]:
            rule_params = getattr(rule, "parameters", None)
            if not rule_params:
                continue
            for p_name in rule_params:
                style_option.add_argument("--" + p_name,
                                          **rule_params[p_name])

    style_option.add_argument("--copyright-entity",
                              metavar="STR",
                              default=[],
                              nargs="+",
                              help=("Add (company) name to check for in "
                                    "Copyright notices. Can be specified "
                                    "multiple times."))

    options = command_line.parse_args(clp)

    if options.html:
        if os.path.exists(options.html) and not os.path.isfile(options.html):
            clp["ap"].error("Cannot write to %s: it is not a file" %
                            options.html)
        mh = HTML_Message_Handler("style", options.html)
    else:
        mh = Message_Handler("style")

    mh.show_context = not options.brief
    mh.show_style   = not options.no_style
    mh.autofix      = options.fix

    extra_options = {
        "fd_tree"  : None,
        "rule_set" : rule_set,
    }

    if options.debug_dump_tree:
        extra_options["fd_tree"] = open(options.debug_dump_tree, "w")

    style_backend = MH_Style()
    command_line.execute(mh, options, extra_options,
                         style_backend,
                         options.process_slx)

    if options.debug_dump_tree:
        extra_options["fd_tree"].close()


def main():
    command_line.ice_handler(main_handler)


if __name__ == "__main__":
    main()