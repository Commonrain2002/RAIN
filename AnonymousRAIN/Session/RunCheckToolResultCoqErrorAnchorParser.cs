using System.Text.RegularExpressions;

namespace ProofAgent.Session;

public class RunCheckToolResultCoqErrorAnchorParser
{
    #region Fields

    private const string _CoqErrorMessageSectionHeading = "## Coq Error Message";

    private const string _ErrorLineAroundSectionHeading = "## Error line around";

    private static readonly Regex _FileLineCharacterRegex = new(
        @"File\s+""(?<file>[^""]*)"",\s*line\s+(?<line>\d+),\s*character\s+(?<col>\d+)\s*:",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    #endregion Fields

    public bool TryParse(string runCheckToolContent, out RunCheckToolResultCoqErrorAnchor anchor)
    {
        anchor = null!;
        if (string.IsNullOrWhiteSpace(runCheckToolContent))
        {
            return false;
        }

        if (!_TryExtractSectionBody(
                runCheckToolContent,
                _CoqErrorMessageSectionHeading,
                _ErrorLineAroundSectionHeading,
                out var coqErrorMessageSectionBody))
        {
            return false;
        }

        return _TryParseLineAndColumn(coqErrorMessageSectionBody, out anchor);
    }

    #region Private Methods

    private static bool _TryExtractSectionBody(
        string runCheckToolContent,
        string sectionHeading,
        string nextSectionHeading,
        out string sectionBody)
    {
        sectionBody = "";
        var headingIndex = runCheckToolContent.IndexOf(sectionHeading, StringComparison.Ordinal);
        if (headingIndex < 0)
        {
            return false;
        }

        var bodyStart = headingIndex + sectionHeading.Length;
        var nextIndex = runCheckToolContent.IndexOf(nextSectionHeading, bodyStart, StringComparison.Ordinal);
        if (nextIndex < 0)
        {
            return false;
        }

        sectionBody = runCheckToolContent.Substring(bodyStart, nextIndex - bodyStart).Trim();
        return sectionBody.Length > 0;
    }

    private static bool _TryParseLineAndColumn(
        string coqErrorMessageSectionBody,
        out RunCheckToolResultCoqErrorAnchor anchor)
    {
        anchor = null!;
        using var reader = new StringReader(coqErrorMessageSectionBody);
        string? line;
        while ((line = reader.ReadLine()) is not null)
        {
            var trimmed = line.Trim();
            if (trimmed.Length == 0)
            {
                continue;
            }

            var match = _FileLineCharacterRegex.Match(trimmed);
            if (!match.Success)
            {
                continue;
            }

            if (!int.TryParse(match.Groups["line"].Value, out var lineOneBased) || lineOneBased <= 0)
            {
                continue;
            }

            if (!int.TryParse(match.Groups["col"].Value, out var columnZeroBased) || columnZeroBased < 0)
            {
                continue;
            }

            anchor = new RunCheckToolResultCoqErrorAnchor(lineOneBased, columnZeroBased);
            return true;
        }

        return false;
    }

    #endregion Private Methods
}
