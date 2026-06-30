using ProofAgent.Coq;
using ProofAgent.Tools;

namespace ProofAgent.Tests;

public class FixedCoqSentenceSplitter : ICoqSentenceSplitter
{
    private readonly IReadOnlyList<CoqSentence> _Sentences;

    public FixedCoqSentenceSplitter(IReadOnlyList<CoqSentence> sentences)
    {
        _Sentences = sentences;
    }

    public Task<IReadOnlyList<CoqSentence>> SplitAsync(
        RelativePath relativeCoqFilePath,
        CancellationToken cancellationToken)
    {
        _ = relativeCoqFilePath;
        _ = cancellationToken;
        return Task.FromResult(_Sentences);
    }
}
