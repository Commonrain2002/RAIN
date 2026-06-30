using ProofAgent.Tools;

namespace ProofAgent.Coq;

public interface ICoqSentenceAnalyzer
{
    Task<CoqSentence?> GetSentenceBeforeAsync(
        RelativePath relativeCoqFilePath,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken);

    Task<CoqSentence?> GetSentenceAtPositionAsync(
        RelativePath relativeCoqFilePath,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken);
}
