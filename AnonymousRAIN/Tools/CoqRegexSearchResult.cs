namespace ProofAgent.Tools;

public class CoqRegexSearchResult
{
    public CoqRegexSearchResult(IReadOnlyList<SearchHit> hits, int totalHitCount)
    {
        Hits = hits;
        TotalHitCount = totalHitCount;
    }

    public IReadOnlyList<SearchHit> Hits { get; }

    public int TotalHitCount { get; }
}
