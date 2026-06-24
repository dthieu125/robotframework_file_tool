/**
 * CodeMirror 5 – Robot Framework syntax mode
 * Highlights: section headers, test/keyword names, variables,
 * bracket-settings, comments, keyword calls.
 */
(function (mod) {
  if (typeof exports === 'object' && typeof module === 'object')
    mod(require('codemirror'));
  else if (typeof define === 'function' && define.amd)
    define(['codemirror'], mod);
  else
    mod(CodeMirror);
})(function (CodeMirror) {
  'use strict';

  const SECTION_RE = /^\s*\*+\s*(Settings?|Variables?|Test\s*Cases?|Tasks?|Keywords?|Comments?)\s*\**\s*$/i;
  const VARIABLE_RE = /^[$@&%]\{[^}]*\}/;
  const BRACKET_SETTING_RE = /^\[[^\]]+\]/;

  CodeMirror.defineMode('robot', function () {
    return {
      startState: function () {
        return {
          section: null,   // 'tc' | 'kw' | 'set' | 'var' | null
        };
      },

      token: function (stream, state) {
        /* ── At the very start of each line, look at the whole line ── */
        if (stream.sol()) {
          const line = stream.string;

          // 1. Empty / whitespace-only line
          if (!line.trim()) {
            stream.skipToEnd();
            return null;
          }

          // 2. Section header  *** Test Cases ***
          if (SECTION_RE.test(line)) {
            stream.skipToEnd();
            const m = line.match(
              /\*+\s*(Settings?|Variables?|Test\s*Cases?|Tasks?|Keywords?)/i
            );
            if (m) {
              const sec = m[1].toLowerCase().replace(/\s+/g, '');
              if (sec.startsWith('test') || sec === 'tasks') state.section = 'tc';
              else if (sec.startsWith('keyword'))             state.section = 'kw';
              else if (sec.startsWith('setting'))             state.section = 'set';
              else if (sec.startsWith('variable'))            state.section = 'var';
              else                                            state.section = null;
            }
            return 'rf-header';
          }

          // 3. Non-indented, non-comment line in TC/KW section = name
          if (
            (state.section === 'tc' || state.section === 'kw') &&
            !line.startsWith(' ') &&
            !line.startsWith('\t') &&
            !line.startsWith('#')
          ) {
            stream.skipToEnd();
            return 'rf-name';
          }
        }

        /* ── Within-line tokenisation ────────────────────────────── */

        // Eat leading whitespace (indentation / separators)
        if (stream.eatSpace()) return null;

        // Line comment
        if (stream.peek() === '#') {
          stream.skipToEnd();
          return 'rf-comment';
        }

        // Variables:  ${VAR}  @{LIST}  &{DICT}  %{ENV}
        if (stream.match(VARIABLE_RE)) return 'rf-variable';

        // Bracket settings:  [Arguments]  [Tags]  [Documentation]  …
        if (stream.match(BRACKET_SETTING_RE)) return 'rf-setting';

        // In Settings section: first non-indented token = setting keyword
        if (state.section === 'set') {
          const line = stream.string;
          if (!line.startsWith(' ') && !line.startsWith('\t')) {
            stream.match(/\S+/);
            return 'rf-keyword';
          }
        }

        // Separator (two or more spaces used as column separator in RF)
        // Just consume and return nothing so the next token starts fresh.
        if (stream.match(/  +/)) return null;

        // Fallback – consume one character
        stream.next();
        return null;
      },
    };
  });

  CodeMirror.defineMIME('text/x-robot', 'robot');
});
