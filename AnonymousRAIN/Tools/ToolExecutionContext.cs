using System.Text;
using System.Text.RegularExpressions;
using ProofAgent.Coq;

namespace ProofAgent.Tools;

public class ToolExecutionContext : IToolExecutionContext
{
    #region Fields

    private const string _OldTextNotFound =
        "replace failed: old text not found, please check whether the old text matches the file";

    private const string _AmbiguousMatch =
        "replace failed: multiple matches found; increase the scope of old text to make the match unique";

    private const int _MaxOutputChars = 10000;

    private const string _Ellipsis = "...";

    private const string _NoMatchesFoundMessage = "No matches found.";

    private const string _NoLemmasInFileMessage = "No lemmas/theorems indexed in this file.";

    private const string _RunCheckResultTruncatedSuffix =
        "\n[Output too long; subsequent content omitted]";

    private static readonly string _BlockSeparator = Environment.NewLine + Environment.NewLine;

    private static readonly string _PathLineSeparator = Environment.NewLine;

    private readonly ProjectFileSystem _FileSystem;

    private readonly IReadOnlyList<IReadOnlyFileSystem> _ExtraReadableRootFileSystems;

    private readonly int _SearchHitContextLines;

    private readonly ICoqMultiErrorChecker _MultiErrorChecker;

    private readonly IRunCheckToolResultFormatter _RunCheckResultFormatter;

    private readonly LemmaDatabase _LemmaDatabase;

    #endregion Fields

    public ToolExecutionContext(
        ProjectFileSystem fileSystem,
        IReadOnlyList<IReadOnlyFileSystem> extraReadableRootFileSystems,
        int searchHitContextLines,
        ICoqMultiErrorChecker multiErrorChecker,
        IRunCheckToolResultFormatter runCheckResultFormatter,
        LemmaDatabase lemmaDatabase)
    {
        _FileSystem = fileSystem ?? throw new ArgumentNullException(nameof(fileSystem));
        _ExtraReadableRootFileSystems = extraReadableRootFileSystems
            ?? throw new ArgumentNullException(nameof(extraReadableRootFileSystems));
        _SearchHitContextLines = searchHitContextLines;
        _MultiErrorChecker = multiErrorChecker ?? throw new ArgumentNullException(nameof(multiErrorChecker));
        _RunCheckResultFormatter = runCheckResultFormatter
            ?? throw new ArgumentNullException(nameof(runCheckResultFormatter));
        _LemmaDatabase = lemmaDatabase ?? throw new ArgumentNullException(nameof(lemmaDatabase));
    }

    public void Replace(string path, string oldText, string newText)
    {
        var relativePath = _ToRelativePath(path);
        var lines = _FileSystem.ReadAllLines(relativePath).ToList();
        _ReplaceUniqueInLines(lines, oldText, newText);
        _FileSystem.WriteAllLines(relativePath, lines);
    }

    public string ReadFileRange(string path, int startLine, int endLine)
    {
        var relativePath = _ToRelativePath(path);
        var window = _FileSystem.ReadLineRange(relativePath, startLine, endLine);
        return _FormatLineWindow(window);
    }

    public string ReadExtraFileRange(string path, int startLine, int endLine)
    {
        var pathValidationError = _ValidateExtraReadableReadPath(path, out var absoluteFilePath);
        if (pathValidationError != null)
        {
            return pathValidationError;
        }

        var lineValidationError = _ValidateReadLineRange(startLine, endLine);
        if (lineValidationError != null)
        {
            return lineValidationError;
        }

        if (!_TryResolveExtraReadableRootFileSystem(absoluteFilePath!, out var fileSystem, out var relativePath))
        {
            return "path must resolve under a directory listed in extraReadableRootPaths.";
        }

        var window = fileSystem.ReadLineRange(relativePath, startLine, endLine);
        return _FormatLineWindow(window);
    }

    public string SearchByRegex(Regex regex, int offset, int maxMatches, bool showContext)
    {
        var contextLines = showContext ? _SearchHitContextLines : -1;
        var searchResult = _FileSystem.SearchByRegex(regex, offset, maxMatches, contextLines);
        return _FormatSearchResult(
            searchResult,
            offset,
            showContext,
            static hit => $"{hit.RelativePath.PosixPath}:{hit.LineNumberOneBased}",
            hit => hit.RelativePath.PosixPath + Environment.NewLine + _FormatHitContext(hit));
    }

    public string ReadLemmasInFile(string path, int offset, int maxMatches)
    {
        var relativePath = _ToRelativePath(path);
        if (!_FileSystem.Exists(relativePath))
        {
            return $"File not found: {relativePath.PosixPath}";
        }

        var pageResult = _LemmaDatabase.GetLemmasInFile(relativePath, offset, maxMatches);
        return _FormatLemmaPageResult(relativePath, pageResult, offset);
    }

    public string SearchExtraByRegex(Regex regex, int offset, int maxMatches, bool showContext)
    {
        var contextLines = showContext ? _SearchHitContextLines : -1;
        var searchResult = _SearchExtraReadableRootsByRegex(regex, offset, maxMatches, contextLines);
        return _FormatSearchResult(
            searchResult,
            offset,
            showContext,
            static hit => $"{hit.RelativePath.ToAbsolute().FullPath}:{hit.LineNumberOneBased}",
            hit => hit.RelativePath.ToAbsolute().FullPath + Environment.NewLine + _FormatHitContext(hit));
    }

    public async Task<string> RunMultiErrorCheckAsync(CancellationToken cancellationToken)
    {
        var failures = await _MultiErrorChecker
            .RunMultiErrorCheckAsync(cancellationToken)
            .ConfigureAwait(false);
        var message = _RunCheckResultFormatter.FormatRunCheckFailures(failures);
        return _TruncateRunCheckResultIfNeeded(message);
    }

    #region Private Methods

    private RelativePath _ToRelativePath(string path)
    {
        return new RelativePath(path, _FileSystem.Root);
    }

    private static string? _ValidateExtraReadableReadPath(string path, out AbsolutePath? absoluteFilePath)
    {
        absoluteFilePath = null;
        if (string.IsNullOrWhiteSpace(path))
        {
            return "Missing required parameter: path.";
        }

        var trimmed = path.Trim();
        if (!Path.IsPathRooted(trimmed))
        {
            return "path must be an absolute file path under a directory listed in extraReadableRootPaths.";
        }

        absoluteFilePath = new AbsolutePath(trimmed);
        return null;
    }

    private static string? _ValidateReadLineRange(int startLine, int endLine)
    {
        if (startLine <= 0 || endLine <= 0)
        {
            return "startLine/endLine must be 1-based positive integers.";
        }

        if (startLine > endLine)
        {
            return "startLine must be <= endLine.";
        }

        return null;
    }

    private bool _TryResolveExtraReadableRootFileSystem(
        AbsolutePath filePath,
        out IReadOnlyFileSystem fileSystem,
        out RelativePath relativePath)
    {
        fileSystem = null!;
        relativePath = null!;
        for (var i = 0; i < _ExtraReadableRootFileSystems.Count; i++)
        {
            var candidate = _ExtraReadableRootFileSystems[i];
            if (filePath.IsUnder(candidate.Root))
            {
                fileSystem = candidate;
                relativePath = new RelativePath(filePath.FullPath, candidate.Root);
                return true;
            }
        }

        return false;
    }

    private CoqRegexSearchResult _SearchExtraReadableRootsByRegex(
        Regex regex,
        int offset,
        int maxMatches,
        int contextLinesAroundMatch)
    {
        var page = new List<SearchHit>();
        var totalAll = 0;
        foreach (var fileSystem in _ExtraReadableRootFileSystems)
        {
            if (page.Count < maxMatches)
            {
                var skipInFileSystem = Math.Max(0, offset - totalAll);
                var take = maxMatches - page.Count;
                var partial = fileSystem.SearchByRegex(regex, skipInFileSystem, take, contextLinesAroundMatch);
                foreach (var hit in partial.Hits)
                {
                    page.Add(hit);
                }

                totalAll += partial.TotalHitCount;
            }
            else
            {
                var countOnly = fileSystem.SearchByRegex(regex, 0, 1, -1);
                totalAll += countOnly.TotalHitCount;
            }
        }

        return new CoqRegexSearchResult(page, totalAll);
    }

    private static string _TruncateRunCheckResultIfNeeded(string result)
    {
        if (result.Length <= _MaxOutputChars)
        {
            return result;
        }

        var keepLength = _MaxOutputChars - _RunCheckResultTruncatedSuffix.Length;
        if (keepLength < 0)
        {
            keepLength = 0;
        }

        return result[..keepLength] + _RunCheckResultTruncatedSuffix;
    }

    private static void _ReplaceUniqueInLines(List<string> lines, string oldText, string newText)
    {
        if (lines.Count == 0)
        {
            throw new InvalidOperationException(_OldTextNotFound);
        }

        var normalizedOldText = _NormalizeBlockSegment(oldText);
        var normalizedNewText = _NormalizeBlockSegment(newText);

        var joined = _JoinLinesNormalized(lines);
        var candidates = _EnumerateMatchStartsOrdinal(joined, normalizedOldText);
        if (candidates.Count == 0)
        {
            throw new InvalidOperationException(_OldTextNotFound);
        }

        if (candidates.Count > 1)
        {
            throw new InvalidOperationException(_AmbiguousMatch);
        }

        var replaceStart = candidates[0];
        var newJoined = joined[..replaceStart] +
                        normalizedNewText +
                        joined[(replaceStart + normalizedOldText.Length)..];
        _SetLinesFromJoinedNormalized(lines, newJoined);
    }

    private static IReadOnlyList<string> _SplitLines(string content)
    {
        return content.Replace("\r\n", "\n", StringComparison.Ordinal).Split('\n', StringSplitOptions.None);
    }

    private static string _NormalizeBlockSegment(string value)
    {
        return value.Replace("\r\n", "\n", StringComparison.Ordinal);
    }

    private static string _JoinLinesNormalized(IReadOnlyList<string> lines)
    {
        if (lines.Count == 0)
        {
            return string.Empty;
        }

        return string.Join('\n', lines.Select(static line => _NormalizeBlockSegment(line)));
    }

    private static List<int> _EnumerateMatchStartsOrdinal(string haystack, string needle)
    {
        var starts = new List<int>();
        var searchPos = 0;
        while (true)
        {
            var idx = haystack.IndexOf(needle, searchPos, StringComparison.Ordinal);
            if (idx < 0)
            {
                break;
            }

            starts.Add(idx);
            searchPos = idx + 1;
        }

        return starts;
    }

    private static void _SetLinesFromJoinedNormalized(List<string> lines, string joinedNormalized)
    {
        var rebuilt = _SplitLines(joinedNormalized);
        lines.Clear();
        foreach (var text in rebuilt)
        {
            lines.Add(text);
        }
    }

    private string _FormatLineWindow(LineWindow window)
    {
        if (window == null)
        {
            throw new ArgumentNullException(nameof(window));
        }

        var outputLines = new List<string>();
        if (window.HasLeadingEllipsis)
        {
            outputLines.Add(_Ellipsis);
        }

        for (var line = window.StartLine; line <= window.EndLine; line++)
        {
            var content = window.Lines[line - window.StartLine];
            outputLines.Add($"{line}: {content}");
        }

        if (window.HasTrailingEllipsis)
        {
            outputLines.Add(_Ellipsis);
        }

        return string.Join(Environment.NewLine, outputLines);
    }

    private string _FormatLemmaPageResult(RelativePath relativePath, CoqLemmaPage pageResult, int offset)
    {
        var total = pageResult.TotalLemmaCount;
        if (total == 0)
        {
            return _NoLemmasInFileMessage;
        }

        if (offset >= total)
        {
            return _FormatPastOffsetMessage(total, offset);
        }

        var hits = pageResult.Hits;
        if (hits.Count == 0)
        {
            return _FormatPastOffsetMessage(total, offset);
        }

        var build = _AppendHitsWithinCharLimit(
            hits,
            static lemma => lemma.Text.Trim(),
            _BlockSeparator);

        var footers = new List<string>();
        if (build.TruncatedByCharLimit)
        {
            footers.Add(
                $"[Output truncated at {_MaxOutputChars} characters; included {build.ShownHitCount} of {hits.Count} lemmas on this page.]");
        }

        if (total > offset + hits.Count)
        {
            footers.Add(
                $"[Showing lemmas {offset + 1}-{offset + hits.Count} of {total}; increase maxMatches; use offset to paginate.]");
        }

        var body = relativePath.PosixPath;
        if (!string.IsNullOrEmpty(build.Body))
        {
            body = body + _BlockSeparator + build.Body;
        }

        if (footers.Count == 0)
        {
            return body;
        }

        if (string.IsNullOrEmpty(build.Body))
        {
            return body + _PathLineSeparator + string.Join(Environment.NewLine, footers);
        }

        return body + Environment.NewLine + string.Join(Environment.NewLine, footers);
    }

    private static string _FormatPastOffsetMessage(int totalLemmaCount, int offset)
    {
        return string.Join(
            Environment.NewLine,
            "No lemmas on this page.",
            $"[Total lemmas in file: {totalLemmaCount}; offset {offset} is past the last lemma.]");
    }

    private string _FormatSearchResult(
        CoqRegexSearchResult searchResult,
        int offset,
        bool showContext,
        Func<SearchHit, string> formatPathLine,
        Func<SearchHit, string> formatContextBlock)
    {
        var total = searchResult.TotalHitCount;
        if (total == 0)
        {
            return _NoMatchesFoundMessage;
        }

        if (offset >= total)
        {
            return _FormatPastOffsetPageMessage(total, offset);
        }

        var hits = searchResult.Hits;
        if (hits.Count == 0)
        {
            return _FormatPastOffsetPageMessage(total, offset);
        }

        var build = showContext
            ? _AppendHitsWithinCharLimit(hits, formatContextBlock, _BlockSeparator)
            : _AppendHitsWithinCharLimit(hits, formatPathLine, _PathLineSeparator);

        var footers = new List<string>();
        if (build.TruncatedByCharLimit)
        {
            footers.Add(
                $"[Output truncated at {_MaxOutputChars} characters; included {build.ShownHitCount} of {hits.Count} hits on this page.]");
        }

        if (total > offset + hits.Count)
        {
            footers.Add(
                $"[Showing hits {offset + 1}-{offset + hits.Count} of {total}; increase maxMatches or narrow pattern; use offset to paginate.]");
        }

        if (footers.Count == 0)
        {
            return build.Body;
        }

        if (string.IsNullOrEmpty(build.Body))
        {
            return string.Join(Environment.NewLine, footers);
        }

        return build.Body + Environment.NewLine + string.Join(Environment.NewLine, footers);
    }

    private static string _FormatPastOffsetPageMessage(int totalHitCount, int offset)
    {
        return string.Join(
            Environment.NewLine,
            "No matches on this page.",
            $"[Total hits: {totalHitCount}; offset {offset} is past the last hit.]");
    }

    private string _FormatHitContext(SearchHit hit)
    {
        if (hit.ContextWindow == null)
        {
            throw new InvalidOperationException("Search hit is missing context window.");
        }

        return _FormatLineWindow(hit.ContextWindow);
    }

    private SearchOutputBuildResult _AppendHitsWithinCharLimit<T>(
        IReadOnlyList<T> hits,
        Func<T, string> formatHit,
        string separator)
    {
        var builder = new StringBuilder();
        var shown = 0;
        for (var i = 0; i < hits.Count; i++)
        {
            var piece = formatHit(hits[i]);
            var prefix = shown == 0 ? string.Empty : separator;
            if (builder.Length + prefix.Length + piece.Length > _MaxOutputChars)
            {
                break;
            }

            builder.Append(prefix);
            builder.Append(piece);
            shown++;
        }

        return new SearchOutputBuildResult
        {
            Body = builder.ToString(),
            ShownHitCount = shown,
            TruncatedByCharLimit = shown < hits.Count,
        };
    }

    private class SearchOutputBuildResult
    {
        public string Body { get; set; } = string.Empty;

        public int ShownHitCount { get; set; }

        public bool TruncatedByCharLimit { get; set; }
    }

    #endregion Private Methods
}
