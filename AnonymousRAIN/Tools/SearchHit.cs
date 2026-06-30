namespace ProofAgent.Tools;

/// <summary>One regex hit with optional line window around the match line.</summary>
public class SearchHit
{
    public SearchHit(RelativePath relativePath, int lineNumberOneBased, LineWindow? contextWindow)
    {
        RelativePath = relativePath ?? throw new ArgumentNullException(nameof(relativePath));
        LineNumberOneBased = lineNumberOneBased;
        ContextWindow = contextWindow;
    }

    public RelativePath RelativePath { get; }

    public int LineNumberOneBased { get; }

    /// <summary>Inclusive 1-based context around the match; null when context was not requested.</summary>
    public LineWindow? ContextWindow { get; }
}
