using ProofAgent.Tools;

namespace ProofAgent.Coq;

public interface ICoqSentenceSplitter
{
    Task<IReadOnlyList<CoqSentence>> SplitAsync(RelativePath relativeCoqFilePath, CancellationToken cancellationToken);
}
