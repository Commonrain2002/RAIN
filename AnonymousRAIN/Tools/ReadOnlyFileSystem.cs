using System.Text.RegularExpressions;

namespace ProofAgent.Tools;

public class ReadOnlyFileSystem : IReadOnlyFileSystem
{
    #region Fields

    private readonly AbsolutePath _Root;

    #endregion Fields

    #region Properties

    public AbsolutePath Root => _Root;

    #endregion Properties

    public ReadOnlyFileSystem(string root)
        : this(new AbsolutePath(string.IsNullOrWhiteSpace(root) ? Environment.CurrentDirectory : root))
    {
    }

    public ReadOnlyFileSystem(AbsolutePath root)
    {
        _Root = root ?? throw new ArgumentNullException(nameof(root));
    }

    /// <summary>
    /// Recursively scan all .v files under root and match each line with the given regex; at most one hit per physical line.
    /// Order: path ordinal then ascending line (same as <see cref="_GetAllCoqFilesRelative"/> enumeration).
    /// Returns one page (<paramref name="offset"/> skipped, up to <paramref name="maxMatches"/> hits) and total hits in the tree.
    /// When <paramref name="contextLinesAroundMatch"/> is non-negative, each hit includes a <see cref="LineWindow"/> around the match line.
    /// </summary>
    public CoqRegexSearchResult SearchByRegex(
        Regex regex,
        int offset,
        int maxMatches,
        int contextLinesAroundMatch = -1)
    {
        _CheckSearchArguments(regex, offset, maxMatches, contextLinesAroundMatch);

        var page = new List<SearchHit>();
        var totalHitCount = 0;
        if (!_DirectoryExistsAbsolute(_Root))
        {
            return new CoqRegexSearchResult(page, totalHitCount);
        }

        foreach (var relativePath in _GetAllCoqFilesRelative())
        {
            _AccumulateRegexHitsInCoqFile(
                relativePath,
                regex,
                offset,
                maxMatches,
                contextLinesAroundMatch,
                page,
                ref totalHitCount);
        }

        return new CoqRegexSearchResult(page, totalHitCount);
    }

    /// <summary>Read an inclusive 1-based line range as a <see cref="LineWindow"/> (ellipsis flags reflect content outside the range).</summary>
    public LineWindow ReadLineRange(RelativePath relativePath, int startLine, int endLine)
    {
        var allLines = ReadAllLines(relativePath);
        _CheckReadArguments(startLine, endLine, allLines.Length);

        endLine = Math.Min(endLine, allLines.Length);
        var windowLines = new List<string>();
        for (var line = startLine; line <= endLine; line++)
        {
            windowLines.Add(allLines[line - 1]);
        }

        return new LineWindow
        {
            StartLine = startLine,
            EndLine = endLine,
            HasLeadingEllipsis = startLine > 1,
            HasTrailingEllipsis = endLine < allLines.Length,
            Lines = windowLines
        };
    }

    public bool Exists(RelativePath relativePath)
    {
        return _FileExistsAbsolute(_ResolveAllowedAbsolutePath(relativePath));
    }

    public string[] ReadAllLines(RelativePath relativePath)
    {
        return _ReadAllLinesAbsolute(_ResolveAllowedAbsolutePath(relativePath));
    }

    public bool Exists(AbsolutePath fullPath)
    {
        return _FileExistsAbsolute(_EnsureAccessAllowed(fullPath));
    }

    public bool DirectoryExists(AbsolutePath fullPath)
    {
        return _DirectoryExistsAbsolute(_EnsureAccessAllowed(fullPath));
    }

    public string ReadAllText(AbsolutePath fullPath)
    {
        return _ReadAllTextAbsolute(_EnsureAccessAllowed(fullPath));
    }

    public string ReadAllText(RelativePath relativePath)
    {
        return _ReadAllTextAbsolute(_ResolveAllowedAbsolutePath(relativePath));
    }

    /// <summary>Compute the inclusive 1-based line window around <paramref name="centerLine"/> within <paramref name="lines"/>, clamped to the file,
    /// with flags indicating whether content exists before/after the window.
    /// </summary>
    public LineWindow LinesAround(
        IReadOnlyList<string> lines,
        int centerLine,
        int linesBefore,
        int linesAfter)
    {
        _CheckLinesAroundArguments(lines, centerLine, linesBefore, linesAfter);

        var lineCount = lines.Count;
        var endLine = Math.Min(lineCount, centerLine + linesAfter);
        var startLine = Math.Max(1, centerLine - linesBefore);
        if (startLine > endLine)
        {
            startLine = Math.Max(1, endLine - linesBefore);
        }

        var windowLines = new List<string>();
        for (var line = startLine; line <= endLine; line++)
        {
            windowLines.Add(lines[line - 1]);
        }

        return new LineWindow
        {
            StartLine = startLine,
            EndLine = endLine,
            HasLeadingEllipsis = startLine > 1,
            HasTrailingEllipsis = endLine < lineCount,
            Lines = windowLines
        };
    }

    public IReadOnlyList<RelativePath> GetAllCoqFileRelativePaths()
    {
        return _GetAllCoqFilesRelative();
    }

    #region Private Methods

    private AbsolutePath _ResolveAllowedAbsolutePath(RelativePath relativePath)
    {
        if (relativePath == null)
        {
            throw new ArgumentNullException(nameof(relativePath));
        }

        return _EnsureAccessAllowed(relativePath.ToAbsolute());
    }

    protected virtual AbsolutePath _EnsureAccessAllowed(AbsolutePath fullPath)
    {
        if (fullPath == null)
        {
            throw new ArgumentNullException(nameof(fullPath));
        }

        if (fullPath.IsUnder(_Root))
        {
            return fullPath;
        }

        throw new InvalidOperationException(
            "File access denied: path must resolve under the read-only root.");
    }

    protected static void _CheckSearchArguments(Regex regex, int offset, int maxMatches, int contextLinesAroundMatch)
    {
        if (regex == null)
        {
            throw new ArgumentNullException(nameof(regex));
        }

        if (offset < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(offset), "offset must be a non-negative integer.");
        }

        if (maxMatches <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxMatches), "maxMatches must be a positive integer.");
        }

        if (contextLinesAroundMatch < -1)
        {
            throw new ArgumentOutOfRangeException(
                nameof(contextLinesAroundMatch),
                "contextLinesAroundMatch must be -1 (no snippet) or a non-negative integer.");
        }
    }

    private static void _CheckReadArguments(int startLine, int endLine, int lineCount)
    {
        if (startLine <= 0 || endLine <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(startLine), "startLine/endLine must be 1-based positive integers.");
        }

        if (startLine > endLine)
        {
            throw new ArgumentOutOfRangeException(nameof(endLine), "startLine must be <= endLine.");
        }

        if (startLine > lineCount)
        {
            throw new ArgumentOutOfRangeException(
                nameof(startLine),
                $"startLine out of range: file has 1..{lineCount} lines, requested {startLine}..{endLine}.");
        }
    }

    private static void _CheckLinesAroundArguments(
        IReadOnlyList<string> lines,
        int centerLine,
        int linesBefore,
        int linesAfter)
    {
        if (lines == null)
        {
            throw new ArgumentNullException(nameof(lines));
        }

        if (centerLine <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(centerLine), "centerLine must be a 1-based positive integer.");
        }

        if (linesBefore < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(linesBefore), "linesBefore must be non-negative.");
        }

        if (linesAfter < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(linesAfter), "linesAfter must be non-negative.");
        }
    }

    protected static bool _FileExistsAbsolute(AbsolutePath fullPath)
    {
        return File.Exists(fullPath.FullPath);
    }

    protected static bool _DirectoryExistsAbsolute(AbsolutePath fullPath)
    {
        return Directory.Exists(fullPath.FullPath);
    }

    protected static string _ReadAllTextAbsolute(AbsolutePath fullPath)
    {
        return File.ReadAllText(fullPath.FullPath);
    }

    protected static string[] _ReadAllLinesAbsolute(AbsolutePath fullPath)
    {
        return File.ReadAllLines(fullPath.FullPath);
    }

    protected static IEnumerable<string> _EnumerateFilesAbsolute(
        AbsolutePath directoryPath,
        string searchPattern,
        SearchOption searchOption)
    {
        return Directory.EnumerateFiles(directoryPath.FullPath, searchPattern, searchOption);
    }

    private IReadOnlyList<RelativePath> _GetAllCoqFilesRelative()
    {
        if (!_DirectoryExistsAbsolute(_Root))
        {
            return Array.Empty<RelativePath>();
        }

        return _EnumerateFilesAbsolute(_Root, "*.v", SearchOption.AllDirectories)
            .Select(p => Path.GetRelativePath(_Root.FullPath, p).Replace('\\', '/'))
            .OrderBy(static s => s, StringComparer.Ordinal)
            .Select(posix => new RelativePath(posix, _Root))
            .ToList();
    }

    private void _AccumulateRegexHitsInCoqFile(
        RelativePath relativePath,
        Regex regex,
        int offset,
        int maxMatches,
        int contextLinesAroundMatch,
        List<SearchHit> page,
        ref int totalHitCount)
    {
        string[] lines;
        try
        {
            lines = ReadAllLines(relativePath);
        }
        catch (IOException)
        {
            return;
        }
        catch (UnauthorizedAccessException)
        {
            return;
        }

        for (var i = 0; i < lines.Length; i++)
        {
            if (!regex.IsMatch(lines[i]))
            {
                continue;
            }

            totalHitCount++;
            if (totalHitCount <= offset)
            {
                continue;
            }

            if (page.Count < maxMatches)
            {
                var lineNumberOneBased = i + 1;
                LineWindow? contextWindow = null;
                if (contextLinesAroundMatch >= 0)
                {
                    contextWindow = LinesAround(
                        lines,
                        lineNumberOneBased,
                        contextLinesAroundMatch,
                        contextLinesAroundMatch);
                }

                page.Add(new SearchHit(relativePath, lineNumberOneBased, contextWindow));
            }
        }
    }

    #endregion Private Methods
}
