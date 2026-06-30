namespace ProofAgent.Tools;

/// <summary>An inclusive 1-based range of source lines around a center line, with flags for content elided before/after the range.</summary>
public class LineWindow
{
    public int StartLine { get; init; }

    public int EndLine { get; init; }

    public bool HasLeadingEllipsis { get; init; }

    public bool HasTrailingEllipsis { get; init; }

    public IReadOnlyList<string> Lines { get; init; } = Array.Empty<string>();
}
