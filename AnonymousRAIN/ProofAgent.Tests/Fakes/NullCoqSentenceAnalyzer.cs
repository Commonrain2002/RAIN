using ProofAgent.Coq;
using ProofAgent.Tools;

namespace ProofAgent.Tests.Fakes;

/// <summary>Stub sentence analyzer for tests that only exercise capturer I/O helpers.</summary>
public class NullCoqSentenceAnalyzer : ICoqSentenceAnalyzer
{
    public Task<CoqSentence?> GetSentenceBeforeAsync(
        RelativePath relativeCoqFilePath,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken)
    {
        return Task.FromResult<CoqSentence?>(null);
    }

    public Task<CoqSentence?> GetSentenceAtPositionAsync(
        RelativePath relativeCoqFilePath,
        int lineOneBased,
        int columnZeroBased,
        CancellationToken cancellationToken)
    {
        return Task.FromResult<CoqSentence?>(null);
    }
}
