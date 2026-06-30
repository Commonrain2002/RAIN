using System.Text.RegularExpressions;

namespace ProofAgent.Tools;

/// <summary>
/// Sandboxed read-only access to UTF-8 text files under a single root directory (not Coq-specific).
/// </summary>
public interface IReadOnlyFileSystem
{
    AbsolutePath Root { get; }

    bool DirectoryExists(AbsolutePath fullPath);

    bool Exists(RelativePath relativePath);

    string ReadAllText(RelativePath relativePath);

    LineWindow ReadLineRange(RelativePath relativePath, int startLine, int endLine);

    CoqRegexSearchResult SearchByRegex(
        Regex regex,
        int offset,
        int maxMatches,
        int contextLinesAroundMatch = -1);
}
