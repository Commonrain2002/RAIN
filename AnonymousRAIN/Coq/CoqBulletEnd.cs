namespace ProofAgent.Coq;

public class CoqBulletEnd
{
    public CoqBulletEnd(
        bool succeeded,
        string failureReason,
        int anchorSentenceIndex,
        int endLineOneBased,
        int endColumnZeroBased,
        int lastSentenceIndex)
    {
        Succeeded = succeeded;
        FailureReason = failureReason;
        AnchorSentenceIndex = anchorSentenceIndex;
        EndLineOneBased = endLineOneBased;
        EndColumnZeroBased = endColumnZeroBased;
        LastSentenceIndex = lastSentenceIndex;
    }

    public bool Succeeded { get; }

    public string FailureReason { get; }

    public int AnchorSentenceIndex { get; }

    public int EndLineOneBased { get; }

    public int EndColumnZeroBased { get; }

    public int LastSentenceIndex { get; }
}
