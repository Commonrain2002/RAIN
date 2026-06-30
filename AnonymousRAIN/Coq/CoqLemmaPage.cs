namespace ProofAgent.Coq;

public class CoqLemmaPage
{
    public CoqLemmaPage(IReadOnlyList<CoqLemma> hits, int totalLemmaCount)
    {
        Hits = hits;
        TotalLemmaCount = totalLemmaCount;
    }

    public IReadOnlyList<CoqLemma> Hits { get; }

    public int TotalLemmaCount { get; }
}
