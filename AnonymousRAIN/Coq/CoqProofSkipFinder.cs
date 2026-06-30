using ProofAgent.Tools;

namespace ProofAgent.Coq;

/// <summary>Finds the first <c>Admitted.</c> or <c>Abort.</c> sentence in a .v file, ignoring comments and string literals.</summary>
public class CoqProofSkipFinder
{
    #region Fields

    private readonly ProjectFileSystem _FileSystem;

    #endregion Fields

    public CoqProofSkipFinder(ProjectFileSystem fileSystem)
    {
        _FileSystem = fileSystem ?? throw new ArgumentNullException(nameof(fileSystem));
    }

    /// <summary>
    /// Read <paramref name="relativePath"/> under the project root and find the first <c>Admitted.</c> or <c>Abort.</c>
    /// sentence outside comments/strings. Returns <c>null</c> when the file is missing or no skip is found.
    /// </summary>
    public CoqProofSkip? FindFirstProofSkip(RelativePath relativePath)
    {
        ArgumentNullException.ThrowIfNull(relativePath);

        if (!_FileSystem.Exists(relativePath))
        {
            return null;
        }

        var lines = _FileSystem.ReadAllLines(relativePath);
        var skip = _FindFirstProofSkipInLines(lines);
        if (skip == null)
        {
            return null;
        }

        return skip;
    }

    #region Private Methods

    private static CoqProofSkip? _FindFirstProofSkipInLines(IReadOnlyList<string> lines)
    {
        if (lines.Count == 0)
        {
            return null;
        }

        var joinedSource = string.Join(Environment.NewLine, lines);
        if (joinedSource.Length == 0)
        {
            return null;
        }

        return _FindFirstProofSkip(joinedSource);
    }

    private static CoqProofSkip? _FindFirstProofSkip(string joinedSource)
    {
        var commentDepth = 0;
        var insideString = false;

        for (var index = 0; index < joinedSource.Length; index++)
        {
            if (_ApplyLexicalRules(joinedSource, ref index, ref commentDepth, ref insideString))
            {
                continue;
            }

            if (joinedSource[index] == 'A' && _MatchProofSkipSentence(joinedSource, index, out var skipType))
            {
                return _CreateProofSkipAtIndex(joinedSource, index, skipType);
            }
        }

        return null;
    }

    private static bool _ApplyLexicalRules(
        string joinedSource,
        ref int index,
        ref int commentDepth,
        ref bool insideString)
    {
        var current = joinedSource[index];
        var next = index + 1 < joinedSource.Length ? joinedSource[index + 1] : '\0';

        if (insideString)
        {
            if (current == '"')
            {
                insideString = false;
            }

            return true;
        }

        if (commentDepth > 0)
        {
            if (current == '(' && next == '*')
            {
                commentDepth++;
                index++;
                return true;
            }

            if (current == '*' && next == ')')
            {
                commentDepth = Math.Max(0, commentDepth - 1);
                index++;
                return true;
            }

            return true;
        }

        if (current == '(' && next == '*')
        {
            commentDepth++;
            index++;
            return true;
        }

        if (current == '"')
        {
            insideString = true;
            return true;
        }

        return false;
    }

    private static bool _MatchProofSkipSentence(string joinedSource, int index, out CoqProofSkipType skipType)
    {
        skipType = default;
        if (index > 0 && _IsContinuationChar(joinedSource[index - 1]))
        {
            return false;
        }

        if (_TryMatchSkipToken(joinedSource, index, "Admitted.", CoqProofSkipType.Admitted, out skipType))
        {
            return true;
        }

        if (_TryMatchSkipToken(joinedSource, index, "Abort.", CoqProofSkipType.Abort, out skipType))
        {
            return true;
        }

        return false;
    }

    private static bool _TryMatchSkipToken(
        string joinedSource,
        int index,
        string token,
        CoqProofSkipType skipType,
        out CoqProofSkipType matchedSkipType)
    {
        matchedSkipType = default;
        if (index + token.Length > joinedSource.Length || !joinedSource.AsSpan(index).StartsWith(token))
        {
            return false;
        }

        var afterDot = index + token.Length < joinedSource.Length
            ? joinedSource[index + token.Length]
            : '\0';
        if (!_IsSentenceBreak(afterDot))
        {
            return false;
        }

        matchedSkipType = skipType;
        return true;
    }

    private static bool _IsContinuationChar(char character)
    {
        return char.IsLetterOrDigit(character) || character == '_' || character == '\'';
    }

    /// <summary>Coq sentence end: <c>.</c> followed by whitespace or end of file (no other heuristics).</summary>
    private static bool _IsSentenceBreak(char character)
    {
        return character == '\0'
            || character == ' '
            || character == '\t'
            || character == '\r'
            || character == '\n';
    }

    private static CoqProofSkip _CreateProofSkipAtIndex(string joinedSource, int index, CoqProofSkipType skipType)
    {
        _IndexToLineColumn(joinedSource, index, out var lineOneBased, out var columnZeroBased);
        return new CoqProofSkip(lineOneBased, columnZeroBased, skipType);
    }

    /// <summary>Map a 0-based index in <paramref name="text"/> to a 1-based line and 0-based column (same coordinates as Coq error columns).</summary>
    private static void _IndexToLineColumn(string text, int index, out int lineOneBased, out int columnZeroBased)
    {
        lineOneBased = 1;
        columnZeroBased = 0;
        if (string.IsNullOrEmpty(text) || index <= 0)
        {
            return;
        }

        index = Math.Clamp(index, 0, text.Length);
        var lineStartIndex = 0;
        for (var i = 0; i < index; i++)
        {
            if (i >= text.Length)
            {
                break;
            }

            if (text[i] == '\r' && i + 1 < text.Length && text[i + 1] == '\n')
            {
                lineOneBased++;
                lineStartIndex = i + 2;
                i++;
            }
            else if (text[i] == '\n' || text[i] == '\r')
            {
                lineOneBased++;
                lineStartIndex = i + 1;
            }
        }

        columnZeroBased = index - lineStartIndex;
    }

    #endregion Private Methods
}
