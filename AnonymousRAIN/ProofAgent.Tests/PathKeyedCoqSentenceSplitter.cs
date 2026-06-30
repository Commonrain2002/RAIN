using ProofAgent.Coq;
using ProofAgent.Tools;

namespace ProofAgent.Tests;

public class PathKeyedCoqSentenceSplitter : ICoqSentenceSplitter
{
    private readonly Dictionary<string, IReadOnlyList<CoqSentence>> _SentencesByPosixPath;

    public PathKeyedCoqSentenceSplitter(Dictionary<string, IReadOnlyList<CoqSentence>> sentencesByPosixPath)
    {
        _SentencesByPosixPath = sentencesByPosixPath
            ?? throw new ArgumentNullException(nameof(sentencesByPosixPath));
    }

    public Task<IReadOnlyList<CoqSentence>> SplitAsync(
        RelativePath relativeCoqFilePath,
        CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        if (_SentencesByPosixPath.TryGetValue(relativeCoqFilePath.PosixPath, out var sentences))
        {
            return Task.FromResult(sentences);
        }

        return Task.FromResult<IReadOnlyList<CoqSentence>>(Array.Empty<CoqSentence>());
    }
}
